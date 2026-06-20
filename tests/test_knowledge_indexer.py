from __future__ import annotations

import shutil

from bridle.harness.job_store import SQLiteJobStore
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.chunking import chunk_document
from bridle.knowledge.indexer import index_godot_project
from bridle.knowledge.scanner import scan_godot_project


def make_project(tmp_path):
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    return project


def test_scanner_excludes_engine_data_and_reports_skipped_files(tmp_path) -> None:
    project = make_project(tmp_path)
    (project / "player.gd").write_text("func move():\n    pass\n", encoding="utf-8")
    engine = project / ".godot"
    engine.mkdir()
    (engine / "cache.gd").write_text("secret cache", encoding="utf-8")
    (project / "large.md").write_text("x" * 100, encoding="utf-8")

    documents, warnings = scan_godot_project(project, max_file_bytes=50)

    paths = {document.metadata["res_path"] for document in documents}
    assert paths == {"res://project.godot", "res://player.gd"}
    assert warnings == ["Skipped oversized file: large.md"]


def test_gdscript_chunking_preserves_function_line_ranges(tmp_path) -> None:
    project = make_project(tmp_path)
    script = project / "player.gd"
    script.write_text(
        "class_name Player\nvar speed = 1\n\nfunc move():\n    pass\n",
        encoding="utf-8",
    )
    documents, _ = scan_godot_project(project)
    document = next(item for item in documents if item.path == script)

    chunks = chunk_document(document)

    assert [chunk.start_line for chunk in chunks] == [1, 4]
    assert chunks[1].text.startswith("func move()")
    assert chunks[1].metadata["res_path"] == "res://player.gd"


def test_source_ids_remain_stable_when_project_moves(tmp_path) -> None:
    project = make_project(tmp_path)
    (project / "player.gd").write_text("func move():\n    pass\n", encoding="utf-8")
    before, _ = scan_godot_project(project)
    before_ids = {item.metadata["res_path"]: item.source_id for item in before}

    moved = tmp_path / "moved-game"
    shutil.move(project, moved)
    after, _ = scan_godot_project(moved)
    after_ids = {item.metadata["res_path"]: item.source_id for item in after}

    assert after_ids == before_ids
    assert (moved / "bridle" / ".project_id").is_file()


def test_knowledge_catalog_uses_wal_journal_mode(tmp_path) -> None:
    catalog = SQLiteKnowledgeCatalog(tmp_path / "knowledge.sqlite3")
    try:
        mode = catalog._conn.execute("PRAGMA journal_mode").fetchone()[0]  # noqa: SLF001
        assert mode == "wal"
    finally:
        catalog.close()


def test_knowledge_catalog_does_not_close_injected_connection(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    catalog = SQLiteKnowledgeCatalog(
        store.db_path,
        connection=store.connection,
    )
    try:
        catalog.close()

        assert store.connection.execute("SELECT 1").fetchone()[0] == 1
    finally:
        store.close()


def test_indexer_adds_skips_updates_and_deletes_incrementally(tmp_path) -> None:
    project = make_project(tmp_path)
    script = project / "player.gd"
    script.write_text("func move():\n    pass\n", encoding="utf-8")
    catalog = SQLiteKnowledgeCatalog(tmp_path / "knowledge.sqlite3")
    try:
        first = index_godot_project(project, catalog)
        assert first.documents_added == 2
        assert first.chunks_written == 2

        second = index_godot_project(project, catalog)
        assert second.documents_unchanged == 2
        assert second.chunks_written == 0

        script.write_text("func jump():\n    pass\n", encoding="utf-8")
        third = index_godot_project(project, catalog)
        assert third.documents_updated == 1
        assert third.documents_unchanged == 1

        script.unlink()
        fourth = index_godot_project(project, catalog)
        assert fourth.documents_deleted == 1
        assert catalog.chunk_count(project) == 1
    finally:
        catalog.close()
