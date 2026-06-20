from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from bridle.domain.events import JsonValue
from bridle.knowledge.documents import KnowledgeChunk, KnowledgeSourceType, RetrievalHit
from bridle.knowledge.vector_store import _citation


class ChromaVectorStore:
    def __init__(
        self,
        storage_dir: Path,
        project_root: Path,
        *,
        embedding_identity: str = "default",
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                import chromadb
            except ImportError as error:
                raise RuntimeError(
                    "Chroma support requires the 'knowledge' optional dependency."
                ) from error
            storage_dir.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(storage_dir))
        project_hash = hashlib.sha256(str(project_root.resolve()).encode()).hexdigest()[:24]
        embedding_hash = hashlib.sha256(embedding_identity.encode()).hexdigest()[:12]
        self._collection = client.get_or_create_collection(
            name=f"bridle_{project_hash}_{embedding_hash}",
            metadata={"hnsw:space": "cosine"},
        )

    async def upsert(
        self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings must have the same length.")
        if not chunks:
            return
        await asyncio.to_thread(
            self._collection.upsert,
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk.text for chunk in chunks],
            metadatas=[_chroma_metadata(chunk) for chunk in chunks],
        )

    async def delete_sources(self, source_ids: set[str]) -> None:
        if not source_ids:
            return
        await asyncio.to_thread(
            self._collection.delete,
            where={"source_id": {"$in": sorted(source_ids)}},
        )

    async def query(
        self,
        embedding: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
    ) -> list[RetrievalHit]:
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        where = _chroma_where(filters or {})
        result = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[RetrievalHit] = []
        for chunk_id, text, raw_metadata, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            metadata = dict(raw_metadata)
            original = json.loads(metadata.pop("_bridle_metadata", "{}"))
            chunk = KnowledgeChunk(
                chunk_id=chunk_id,
                source_id=metadata["source_id"],
                source_type=KnowledgeSourceType(metadata["source_type"]),
                text=text,
                content_hash=metadata["content_hash"],
                start_line=metadata.get("start_line"),
                end_line=metadata.get("end_line"),
                metadata=original,
            )
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    source_type=chunk.source_type,
                    text=chunk.text,
                    score=max(-1.0, min(1.0, 1.0 - float(distance))),
                    citation=_citation(chunk),
                    metadata=chunk.metadata,
                )
            )
        return hits


def _chroma_metadata(chunk: KnowledgeChunk) -> dict[str, str | int | float | bool]:
    metadata = _scalar_metadata(chunk.metadata)
    metadata.update(
        {
            "source_id": chunk.source_id,
            "source_type": chunk.source_type.value,
            "content_hash": chunk.content_hash,
            "_bridle_metadata": json.dumps(chunk.metadata, ensure_ascii=False),
        }
    )
    if chunk.start_line is not None:
        metadata["start_line"] = chunk.start_line
    if chunk.end_line is not None:
        metadata["end_line"] = chunk.end_line
    return metadata


def _scalar_metadata(values: dict[str, JsonValue]) -> dict[str, str | int | float | bool]:
    return {
        key: value
        for key, value in values.items()
        if isinstance(value, (str, int, float, bool)) and value is not None
    }


def _chroma_where(values: dict[str, JsonValue]) -> dict[str, Any] | None:
    filters = _scalar_metadata(values)
    if not filters:
        return None
    clauses = [{key: value} for key, value in filters.items()]
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}
