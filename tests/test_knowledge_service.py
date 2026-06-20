from __future__ import annotations

from bridle.domain.providers import LlmChatResponse
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.documents import KnowledgeChunk, KnowledgeSourceType
from bridle.knowledge.embeddings import DeterministicEmbeddingProvider
from bridle.knowledge.service import ProjectKnowledgeService
from bridle.knowledge.vector_store import InMemoryVectorStore


def make_project(tmp_path):
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    return project


class FailOnceVectorStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self._fail_next_upsert = True

    async def upsert(self, chunks, embeddings) -> None:
        if self._fail_next_upsert:
            self._fail_next_upsert = False
            raise RuntimeError("simulated vector store failure")
        await super().upsert(chunks, embeddings)


class FakeAnswerProvider:
    def __init__(self, content: str) -> None:
        self.content = content
        self.requests = []

    async def chat(self, request):
        self.requests.append(request)
        return LlmChatResponse(content=self.content)


async def make_answer_service(tmp_path, answer: str):
    embeddings = DeterministicEmbeddingProvider()
    vector_store = InMemoryVectorStore()
    item = KnowledgeChunk(
        chunk_id="player-move",
        source_id="player",
        source_type=KnowledgeSourceType.GODOT_PROJECT,
        text="The player movement speed is 10.",
        content_hash="hash-player",
        start_line=1,
        end_line=2,
        metadata={"res_path": "res://player.gd"},
    )
    await vector_store.upsert([item], await embeddings.embed([item.text]))
    provider = FakeAnswerProvider(answer)
    service = ProjectKnowledgeService(
        SQLiteKnowledgeCatalog(tmp_path / "answer.sqlite3"),
        embeddings,
        vector_store,
        answer_provider=provider,
    )
    return service, provider


async def test_knowledge_service_indexes_incrementally_and_queries_with_citations(tmp_path) -> None:
    project = make_project(tmp_path)
    script = project / "player.gd"
    script.write_text("func move():\n    var speed = 10\n", encoding="utf-8")
    catalog = SQLiteKnowledgeCatalog(tmp_path / "knowledge.sqlite3")
    service = ProjectKnowledgeService(
        catalog,
        DeterministicEmbeddingProvider(),
        InMemoryVectorStore(),
    )
    try:
        first = await service.index_project(project)
        second = await service.index_project(project)
        hits = await service.query_project("player movement speed", top_k=2)

        assert first.documents_added == 2
        assert second.documents_unchanged == 2
        assert second.chunks_written == 0
        assert hits[0].citation.startswith("res://player.gd:")

        script.unlink()
        deleted = await service.index_project(project)
        remaining = await service.query_project("player movement speed", top_k=5)
        assert deleted.documents_deleted == 1
        assert all(hit.metadata["res_path"] != "res://player.gd" for hit in remaining)
    finally:
        catalog.close()


async def test_vector_failure_leaves_catalog_retryable(tmp_path, monkeypatch) -> None:
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("bridle.knowledge.service.asyncio.to_thread", run_inline)
    project = make_project(tmp_path)
    catalog = SQLiteKnowledgeCatalog(tmp_path / "knowledge.sqlite3")
    service = ProjectKnowledgeService(
        catalog,
        DeterministicEmbeddingProvider(),
        FailOnceVectorStore(),
    )
    try:
        try:
            await service.index_project(project)
        except RuntimeError as error:
            assert str(error) == "simulated vector store failure"
        else:
            raise AssertionError("Expected vector store failure")

        assert catalog.hashes_for_project(project) == {}

        summary = await service.index_project(project)
        assert summary.documents_added == 1
        assert len(catalog.hashes_for_project(project)) == 1
    finally:
        catalog.close()


async def test_embedding_identity_change_forces_reindex(tmp_path, monkeypatch) -> None:
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("bridle.knowledge.service.asyncio.to_thread", run_inline)
    project = make_project(tmp_path)
    catalog = SQLiteKnowledgeCatalog(tmp_path / "knowledge.sqlite3")
    try:
        first = ProjectKnowledgeService(
            catalog,
            DeterministicEmbeddingProvider(dimensions=8),
            InMemoryVectorStore(),
            index_identity="model-a",
        )
        second = ProjectKnowledgeService(
            catalog,
            DeterministicEmbeddingProvider(dimensions=16),
            InMemoryVectorStore(),
            index_identity="model-b",
        )

        initial = await first.index_project(project)
        rebuilt = await second.index_project(project)

        assert initial.documents_added == 1
        assert rebuilt.documents_updated == 1
        assert rebuilt.documents_unchanged == 0
    finally:
        catalog.close()


async def test_ask_project_returns_only_model_referenced_citations(tmp_path) -> None:
    service, provider = await make_answer_service(tmp_path, "Speed is 10. [S1]")
    try:
        answer = await service.ask_project("What is the player speed?")

        assert answer.answer == "Speed is 10. [S1]"
        assert [citation.citation for citation in answer.citations] == [
            "res://player.gd:1-2"
        ]
        assert answer.retrieval_hits[0].chunk_id == "player-move"
        assert "[S1] res://player.gd:1-2" in provider.requests[0].messages[0].content
    finally:
        service.catalog.close()


async def test_ask_project_rejects_uncited_generated_answer(tmp_path) -> None:
    service, _ = await make_answer_service(tmp_path, "Speed is probably 10.")
    try:
        answer = await service.ask_project("What is the player speed?")

        assert answer.answer == "Insufficient cited evidence to answer this question."
        assert answer.citations == []
        assert "no valid citations" in answer.warnings[-1]
    finally:
        service.catalog.close()


async def test_ask_project_does_not_call_llm_without_evidence(tmp_path) -> None:
    provider = FakeAnswerProvider("Invented answer [S1]")
    catalog = SQLiteKnowledgeCatalog(tmp_path / "empty.sqlite3")
    service = ProjectKnowledgeService(
        catalog,
        DeterministicEmbeddingProvider(),
        InMemoryVectorStore(),
        answer_provider=provider,
    )
    try:
        answer = await service.ask_project("What is missing?")

        assert answer.answer == "Insufficient project evidence to answer this question."
        assert provider.requests == []
    finally:
        catalog.close()


async def test_ask_project_does_not_call_llm_when_context_cannot_fit_source(tmp_path) -> None:
    service, provider = await make_answer_service(tmp_path, "Invented answer [S1]")
    try:
        answer = await service.ask_project("What is the player speed?", max_context_chars=1)

        assert answer.answer == "Insufficient project evidence to answer this question."
        assert provider.requests == []
        assert "context limit" in answer.warnings[0]
    finally:
        service.catalog.close()
