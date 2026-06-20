from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CacheHit:
    value: Any
    key_hash: str
    created_at: float
    expires_at: float | None


class ExactCache:
    """Persistent exact-match cache keyed by canonical JSON and SHA-256."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cache_entries (
                key_hash TEXT PRIMARY KEY,
                key_json TEXT NOT NULL,
                value_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL
            )
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    @staticmethod
    def hash_key(key: Any) -> tuple[str, str]:
        encoded = json.dumps(
            key, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest(), encoded

    def get(self, key: Any) -> CacheHit | None:
        key_hash, _ = self.hash_key(key)
        row = self._connection.execute(
            "SELECT * FROM cache_entries WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        if row is None:
            return None
        expires_at = float(row[4]) if row[4] is not None else None
        if expires_at is not None and expires_at <= time.time():
            self.delete(key)
            return None
        return CacheHit(
            value=json.loads(row[2]),
            key_hash=key_hash,
            created_at=float(row[3]),
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
                key_hash, key_json, value_json, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(key_hash) DO UPDATE SET
                key_json = excluded.key_json,
                value_json = excluded.value_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (
                key_hash,
                key_json,
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                created_at,
                expires_at,
            ),
        )
        self._connection.commit()
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
