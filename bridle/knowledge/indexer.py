from __future__ import annotations

from pathlib import Path

from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.chunking import chunk_document
from bridle.knowledge.documents import KnowledgeIndexSummary
from bridle.knowledge.scanner import scan_godot_project


def index_godot_project(
    project_root: Path, catalog: SQLiteKnowledgeCatalog
) -> KnowledgeIndexSummary:
    root = project_root.resolve()
    documents, warnings = scan_godot_project(root)
    existing = catalog.hashes_for_project(root)
    current_ids = {document.source_id for document in documents}
    deleted = set(existing) - current_ids
    catalog.delete_sources(deleted)
    summary = KnowledgeIndexSummary(
        project_root=root,
        documents_scanned=len(documents),
        documents_deleted=len(deleted),
        files_skipped=len(warnings),
        warnings=warnings,
    )
    for document in documents:
        previous_hash = existing.get(document.source_id)
        if previous_hash == document.content_hash:
            summary.documents_unchanged += 1
            continue
        chunks = chunk_document(document)
        catalog.replace(document, chunks)
        summary.chunks_written += len(chunks)
        if previous_hash is None:
            summary.documents_added += 1
        else:
            summary.documents_updated += 1
    return summary
