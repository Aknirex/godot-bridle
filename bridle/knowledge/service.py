from __future__ import annotations

import asyncio
import re
from pathlib import Path
from time import perf_counter
from typing import Protocol

from bridle.domain.events import JsonValue
from bridle.domain.providers import LlmChatRequest, LlmChatResponse
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.chunking import chunk_document
from bridle.knowledge.documents import (
    KnowledgeAnswer,
    KnowledgeCitation,
    KnowledgeIndexSummary,
    RetrievalHit,
)
from bridle.knowledge.embeddings import EmbeddingProvider
from bridle.knowledge.scanner import scan_godot_project
from bridle.knowledge.vector_store import VectorStore


class KnowledgeAnswerProvider(Protocol):
    async def chat(self, request: LlmChatRequest) -> LlmChatResponse: ...


class ProjectKnowledgeService:
    def __init__(
        self,
        catalog: SQLiteKnowledgeCatalog,
        embeddings: EmbeddingProvider,
        vector_store: VectorStore,
        *,
        index_identity: str | None = None,
        answer_provider: KnowledgeAnswerProvider | None = None,
    ) -> None:
        self.catalog = catalog
        self.embeddings = embeddings
        self.vector_store = vector_store
        self.index_identity = index_identity
        self.answer_provider = answer_provider
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
                if existing.get(document.source_id)
                != _indexed_content_hash(document.content_hash, self.index_identity)
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
                self.catalog.replace(
                    document,
                    chunks_by_source[document.source_id],
                    index_identity=self.index_identity,
                )

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

    async def ask_project(
        self,
        question: str,
        *,
        top_k: int = 5,
        filters: dict[str, JsonValue] | None = None,
        max_context_chars: int = 12_000,
    ) -> KnowledgeAnswer:
        if self.answer_provider is None:
            raise ValueError("Knowledge answer provider is not configured.")
        if max_context_chars < 1:
            raise ValueError("Knowledge context limit must be positive.")

        started = perf_counter()
        hits = await self.query_project(question, top_k=top_k, filters=filters)
        if not hits:
            return KnowledgeAnswer(
                question=question,
                answer="Insufficient project evidence to answer this question.",
                latency_ms=_elapsed_ms(started),
                warnings=["No relevant project sources were found."],
            )

        prompt, included_hits = _answer_prompt(question, hits, max_context_chars)
        if not included_hits:
            return KnowledgeAnswer(
                question=question,
                answer="Insufficient project evidence to answer this question.",
                retrieval_hits=hits,
                latency_ms=_elapsed_ms(started),
                warnings=["The context limit could not include a project source."],
            )
        response = await self.answer_provider.chat(
            LlmChatRequest(
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
        )
        referenced = {int(value) for value in re.findall(r"\[S(\d+)\]", response.content)}
        valid = [index for index in sorted(referenced) if 1 <= index <= len(included_hits)]
        warnings: list[str] = []
        if referenced - set(valid):
            warnings.append("The model returned one or more invalid source references.")
        if not valid:
            return KnowledgeAnswer(
                question=question,
                answer="Insufficient cited evidence to answer this question.",
                retrieval_hits=hits,
                latency_ms=_elapsed_ms(started),
                warnings=warnings + ["The generated answer contained no valid citations."],
            )

        citations = [
            KnowledgeCitation(
                label=f"S{index}",
                chunk_id=included_hits[index - 1].chunk_id,
                source_id=included_hits[index - 1].source_id,
                citation=included_hits[index - 1].citation,
                score=included_hits[index - 1].score,
            )
            for index in valid
        ]
        return KnowledgeAnswer(
            question=question,
            answer=response.content.strip(),
            citations=citations,
            retrieval_hits=hits,
            latency_ms=_elapsed_ms(started),
            warnings=warnings,
        )


def _indexed_content_hash(content_hash: str, index_identity: str | None) -> str:
    if index_identity is None:
        return content_hash
    return f"{index_identity}:{content_hash}"


def _answer_prompt(
    question: str,
    hits: list[RetrievalHit],
    max_context_chars: int,
) -> tuple[str, list[RetrievalHit]]:
    instructions = (
        "Answer only from the project sources below. Cite every project-specific claim with "
        "[S1], [S2], etc. If the sources are insufficient, say so.\n\n"
        f"Question: {question}\n\nSources:\n"
    )
    sections: list[str] = []
    included: list[RetrievalHit] = []
    remaining = max_context_chars
    for hit in hits:
        label = len(included) + 1
        header = f"[S{label}] {hit.citation}\n"
        available = remaining - len(header)
        if available <= 0:
            break
        text = hit.text[:available]
        sections.append(f"{header}{text}")
        included.append(hit)
        remaining -= len(header) + len(text)
        if remaining <= 0:
            break
    return instructions + "\n\n".join(sections), included


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
