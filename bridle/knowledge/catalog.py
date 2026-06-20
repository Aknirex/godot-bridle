from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from bridle.knowledge.documents import KnowledgeChunk, KnowledgeDocument
from bridle.storage.database import migrate_database


class SQLiteKnowledgeCatalog:
    def __init__(
        self,
        db_path: Path | str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._owns_connection = connection is None
        if connection is None:
            connection = sqlite3.connect(self.db_path)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            migrate_database(connection, self.db_path)
        # Injected connections remain caller-owned and must already be configured and migrated.
        self._conn = connection

    def close(self) -> None:
        if self._owns_connection:
            self._conn.close()

    def hashes_for_project(self, project_root: Path) -> dict[str, str]:
        rows = self._conn.execute(
            "SELECT source_id, content_hash FROM knowledge_sources WHERE project_root = ?",
            (str(project_root.resolve()),),
        ).fetchall()
        return {str(row[0]): str(row[1]) for row in rows}

    def replace(self, document: KnowledgeDocument, chunks: list[KnowledgeChunk]) -> None:
        if document.project_root is None:
            raise ValueError("Indexed project document must have project_root.")
        with self._conn:
            self._conn.execute(
                "DELETE FROM knowledge_sources WHERE source_id = ?",
                (document.source_id,),
            )
            self._conn.execute(
                """INSERT INTO knowledge_sources
                (source_id, project_root, source_type, path, content_hash, chunk_count, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    document.source_id,
                    str(document.project_root.resolve()),
                    document.source_type.value,
                    str(document.path) if document.path else None,
                    document.content_hash,
                    len(chunks),
                    datetime.now(UTC).isoformat(),
                ),
            )
            self._conn.executemany(
                """INSERT INTO knowledge_chunks
                (chunk_id, source_id, content_hash, start_line, end_line, text, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        chunk.chunk_id,
                        chunk.source_id,
                        chunk.content_hash,
                        chunk.start_line,
                        chunk.end_line,
                        chunk.text,
                        json.dumps(chunk.metadata, ensure_ascii=False),
                    )
                    for chunk in chunks
                ],
            )

    def delete_sources(self, source_ids: set[str]) -> None:
        with self._conn:
            self._conn.executemany(
                "DELETE FROM knowledge_sources WHERE source_id = ?",
                [(source_id,) for source_id in source_ids],
            )

    def chunk_count(self, project_root: Path) -> int:
        row = self._conn.execute(
            """SELECT COALESCE(SUM(chunk_count), 0) FROM knowledge_sources
            WHERE project_root = ?""",
            (str(project_root.resolve()),),
        ).fetchone()
        return int(row[0])
