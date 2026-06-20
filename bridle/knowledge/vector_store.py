from __future__ import annotations

import math
from typing import Protocol

from bridle.domain.events import JsonValue
from bridle.knowledge.documents import KnowledgeChunk, RetrievalHit


class VectorStore(Protocol):
    async def upsert(
        self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> None: ...

    async def delete_sources(self, source_ids: set[str]) -> None: ...

    async def query(
        self,
        embedding: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
    ) -> list[RetrievalHit]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[KnowledgeChunk, list[float]]] = {}

    async def upsert(
        self, chunks: list[KnowledgeChunk], embeddings: list[list[float]]
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings must have the same length.")
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            self._items[chunk.chunk_id] = (chunk, embedding)

    async def delete_sources(self, source_ids: set[str]) -> None:
        self._items = {
            chunk_id: item
            for chunk_id, item in self._items.items()
            if item[0].source_id not in source_ids
        }

    async def query(
        self,
        embedding: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
    ) -> list[RetrievalHit]:
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        matches: list[RetrievalHit] = []
        for chunk, candidate in self._items.values():
            if filters and any(chunk.metadata.get(key) != value for key, value in filters.items()):
                continue
            matches.append(
                RetrievalHit(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    source_type=chunk.source_type,
                    text=chunk.text,
                    score=_cosine_similarity(embedding, candidate),
                    citation=_citation(chunk),
                    metadata=chunk.metadata,
                )
            )
        return sorted(matches, key=lambda hit: (-hit.score, hit.chunk_id))[:top_k]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("Embedding dimensions do not match.")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _citation(chunk: KnowledgeChunk) -> str:
    source = str(
        chunk.metadata.get("res_path")
        or chunk.metadata.get("file_path")
        or chunk.source_id
    )
    if chunk.start_line is None:
        return source
    end = chunk.end_line if chunk.end_line is not None else chunk.start_line
    return f"{source}:{chunk.start_line}-{end}"
