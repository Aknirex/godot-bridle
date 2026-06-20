from __future__ import annotations

from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.embeddings import DeterministicEmbeddingProvider
from bridle.knowledge.service import ProjectKnowledgeService
from bridle.knowledge.vector_store import InMemoryVectorStore


def make_project(tmp_path):
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    return project


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
