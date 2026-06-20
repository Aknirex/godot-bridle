from __future__ import annotations

import asyncio
from pathlib import Path

from bridle.domain.events import JsonValue
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.chunking import chunk_document
from bridle.knowledge.documents import KnowledgeIndexSummary, RetrievalHit
from bridle.knowledge.embeddings import EmbeddingProvider
from bridle.knowledge.scanner import scan_godot_project
from bridle.knowledge.vector_store import VectorStore


class ProjectKnowledgeService:
    def __init__(
        self,
        catalog: SQLiteKnowledgeCatalog,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        self.catalog = catalog
        self.embeddings = embeddings
        self.vector_store = vector_store
        self._index_lock = asyncio.Lock()

    async def index_project(self, project_root: Path) -> KnowledgeIndexSummary:
        root = project_root.resolve()
        async with self._index_lock:
            documents, warnings = await asyncio.to_thread(scan_godot_project, root)
            existing = self.catalog.hashes_for_project(root)
            current_ids = {document.source_id for document in documents}
            deleted = set(existing) - current_ids
            changed = [
                document
                for document in documents
                if existing.get(document.source_id) != document.content_hash
            ]
            chunks_by_source = {
                document.source_id: chunk_document(document) for document in changed
            }
            chunks = [chunk for source in chunks_by_source.values() for chunk in source]
            embeddings = await self.embeddings.embed([chunk.text for chunk in chunks])

            updated_source_ids = {
                document.source_id
                for document in changed
                if document.source_id in existing
            }
            await self.vector_store.delete_sources(deleted | updated_source_ids)
            await self.vector_store.upsert(chunks, embeddings)
            self.catalog.delete_sources(deleted)
            for document in changed:
                self.catalog.replace(document, chunks_by_source[document.source_id])

            return KnowledgeIndexSummary(
                project_root=root,
                documents_scanned=len(documents),
                documents_added=sum(item.source_id not in existing for item in changed),
                documents_updated=sum(item.source_id in existing for item in changed),
                documents_unchanged=len(documents) - len(changed),
                documents_deleted=len(deleted),
                chunks_written=len(chunks),
                files_skipped=len(warnings),
                warnings=warnings,
            )

    async def query_project(
        self,
        question: str,
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
    ) -> list[RetrievalHit]:
        if not question.strip():
            raise ValueError("Knowledge query must not be empty.")
        embedding = (await self.embeddings.embed([question]))[0]
        return await self.vector_store.query(embedding, top_k=top_k, filters=filters)
