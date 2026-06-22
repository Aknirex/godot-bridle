from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bridle.providers.base import EmbeddingProvider


@dataclass(frozen=True)
class CacheHit:
    value: Any
    key_hash: str
    created_at: float
    expires_at: float | None


class ExactCache:
    """Persistent exact-match cache with TTL and bounded LRU eviction."""

    def __init__(self, path: Path | str, *, max_entries: int = 1_000) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.path = Path(path)
        self.max_entries = max_entries
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                key_hash TEXT PRIMARY KEY,
                key_json TEXT NOT NULL,
                value_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                accessed_at REAL NOT NULL DEFAULT 0
            )
            """
        )
        columns = {
            row[1] for row in self._connection.execute("PRAGMA table_info(cache_entries)")
        }
        if "accessed_at" not in columns:
            self._connection.execute(
                "ALTER TABLE cache_entries ADD COLUMN accessed_at REAL NOT NULL DEFAULT 0"
            )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def hash_key(key: Any) -> tuple[str, str]:
        encoded = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), encoded

    def get(self, key: Any) -> CacheHit | None:
        key_hash, _ = self.hash_key(key)
        row = self._connection.execute(
            "SELECT key_hash, value_json, created_at, expires_at "
            "FROM cache_entries WHERE key_hash = ?",
            (key_hash,),
        ).fetchone()
        if row is None:
            return None
        expires_at = float(row[3]) if row[3] is not None else None
        if expires_at is not None and expires_at <= time.time():
            self.delete(key)
            return None
        self._connection.execute(
            "UPDATE cache_entries SET accessed_at = ? WHERE key_hash = ?",
            (time.time(), key_hash),
        )
        self._connection.commit()
        return CacheHit(
            value=json.loads(row[1]),
            key_hash=key_hash,
            created_at=float(row[2]),
            expires_at=expires_at,
        )

    def set(self, key: Any, value: Any, *, ttl_seconds: float | None = None) -> str:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        key_hash, key_json = self.hash_key(key)
        created_at = time.time()
        expires_at = created_at + ttl_seconds if ttl_seconds is not None else None
        self._connection.execute(
            """
            INSERT INTO cache_entries (
                key_hash, key_json, value_json, created_at, expires_at, accessed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key_hash) DO UPDATE SET
                key_json = excluded.key_json,
                value_json = excluded.value_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                accessed_at = excluded.accessed_at
            """,
            (
                key_hash,
                key_json,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                created_at,
                expires_at,
                created_at,
            ),
        )
        self._connection.commit()
        self._evict_lru()
        return key_hash

    def delete(self, key: Any) -> bool:
        key_hash, _ = self.hash_key(key)
        cursor = self._connection.execute(
            "DELETE FROM cache_entries WHERE key_hash = ?", (key_hash,)
        )
        self._connection.commit()
        return cursor.rowcount > 0

    def clear_expired(self) -> int:
        cursor = self._connection.execute(
            "DELETE FROM cache_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (time.time(),),
        )
        self._connection.commit()
        return cursor.rowcount

    def __len__(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) FROM cache_entries").fetchone()
        return int(row[0])

    def _evict_lru(self) -> int:
        overflow = len(self) - self.max_entries
        if overflow <= 0:
            return 0
        cursor = self._connection.execute(
            """
            DELETE FROM cache_entries WHERE key_hash IN (
                SELECT key_hash FROM cache_entries
                ORDER BY accessed_at ASC, created_at ASC LIMIT ?
            )
            """,
            (overflow,),
        )
        self._connection.commit()
        return cursor.rowcount


@dataclass(frozen=True)
class SemanticCacheHit:
    value: Any
    score: float
    key_hash: str


class SemanticCache:
    """Persistent cosine cache isolated by embedding model identity."""

    def __init__(
        self,
        path: Path | str,
        embeddings: EmbeddingProvider,
        *,
        threshold: float = 0.94,
        max_entries: int = 500,
    ) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold must be between zero and one")
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embeddings = embeddings
        self.threshold = threshold
        self.max_entries = max_entries
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_cache_entries (
                key_hash TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                prompt TEXT NOT NULL,
                vector BLOB NOT NULL,
                dimensions INTEGER NOT NULL,
                value_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL,
                expires_at REAL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_semantic_cache_namespace "
            "ON semantic_cache_entries(namespace)"
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    async def get(self, namespace: str, prompt: str) -> SemanticCacheHit | None:
        self.clear_expired()
        vector = (await self.embeddings.embed([prompt]))[0]
        best: tuple[str, str, float] | None = None
        rows = self._connection.execute(
            "SELECT key_hash, vector, dimensions, value_json "
            "FROM semantic_cache_entries WHERE namespace = ?",
            (self._isolated_namespace(namespace),),
        )
        for key_hash, blob, dimensions, value_json in rows:
            score = _cosine(vector, _unpack_vector(blob, int(dimensions)))
            if score >= self.threshold and (best is None or score > best[2]):
                best = (str(key_hash), str(value_json), score)
        if best is None:
            return None
        self._connection.execute(
            "UPDATE semantic_cache_entries SET accessed_at = ? WHERE key_hash = ?",
            (time.time(), best[0]),
        )
        self._connection.commit()
        return SemanticCacheHit(json.loads(best[1]), best[2], best[0])

    async def set(
        self,
        namespace: str,
        prompt: str,
        value: Any,
        *,
        ttl_seconds: float | None = None,
    ) -> str:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        isolated = self._isolated_namespace(namespace)
        key_hash, _ = ExactCache.hash_key({"namespace": isolated, "prompt": prompt})
        vector = (await self.embeddings.embed([prompt]))[0]
        now = time.time()
        self._connection.execute(
            """
            INSERT INTO semantic_cache_entries (
                key_hash, namespace, prompt, vector, dimensions, value_json,
                created_at, accessed_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key_hash) DO UPDATE SET
                vector = excluded.vector,
                dimensions = excluded.dimensions,
                value_json = excluded.value_json,
                created_at = excluded.created_at,
                accessed_at = excluded.accessed_at,
                expires_at = excluded.expires_at
            """,
            (
                key_hash,
                isolated,
                prompt,
                _pack_vector(vector),
                len(vector),
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                now,
                now,
                now + ttl_seconds if ttl_seconds is not None else None,
            ),
        )
        self._connection.commit()
        self._evict_lru()
        return key_hash

    def clear_expired(self) -> int:
        cursor = self._connection.execute(
            "DELETE FROM semantic_cache_entries "
            "WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (time.time(),),
        )
        self._connection.commit()
        return cursor.rowcount

    def _isolated_namespace(self, namespace: str) -> str:
        return f"{self.embeddings.index_identity}:{namespace}"

    def _evict_lru(self) -> int:
        count = int(
            self._connection.execute(
                "SELECT COUNT(*) FROM semantic_cache_entries"
            ).fetchone()[0]
        )
        overflow = count - self.max_entries
        if overflow <= 0:
            return 0
        cursor = self._connection.execute(
            """
            DELETE FROM semantic_cache_entries WHERE key_hash IN (
                SELECT key_hash FROM semantic_cache_entries
                ORDER BY accessed_at ASC, created_at ASC LIMIT ?
            )
            """,
            (overflow,),
        )
        self._connection.commit()
        return cursor.rowcount


def _pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack_vector(blob: bytes, dimensions: int) -> list[float]:
    return list(struct.unpack(f"<{dimensions}f", blob))


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return -1.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
