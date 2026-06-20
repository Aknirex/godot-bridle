from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

Migration = tuple[int, str]

MIGRATIONS: Sequence[Migration] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            state TEXT NOT NULL,
            progress REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_code TEXT,
            safe_details TEXT
        );
        CREATE TABLE IF NOT EXISTS job_events (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            type TEXT NOT NULL,
            stage TEXT,
            message TEXT NOT NULL,
            progress REAL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE,
            UNIQUE(job_id, sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_job_events_job_sequence
            ON job_events(job_id, sequence);
        CREATE TABLE IF NOT EXISTS generated_assets (
            asset_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            project_root TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            res_path TEXT NOT NULL,
            status TEXT NOT NULL,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_generated_assets_project
            ON generated_assets(project_root);
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            root_path TEXT NOT NULL UNIQUE,
            project_name TEXT,
            godot_version TEXT,
            generated_assets_dir TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS provider_configs (
            provider_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            backend TEXT,
            model TEXT,
            base_url TEXT,
            api_key_env TEXT,
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            default_for_json TEXT NOT NULL DEFAULT '[]',
            key_source TEXT NOT NULL DEFAULT 'none',
            last_health_status TEXT,
            last_health_message TEXT,
            last_checked_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS benchmark_samples (
            id TEXT PRIMARY KEY,
            job_id TEXT,
            metric_name TEXT NOT NULL,
            stage TEXT,
            provider_id TEXT,
            duration_ms INTEGER,
            value REAL,
            unit TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_benchmark_job ON benchmark_samples(job_id);
        CREATE INDEX IF NOT EXISTS idx_benchmark_metric ON benchmark_samples(metric_name);
        """,
    ),
)


def migrate_database(connection: sqlite3.Connection, db_path: Path) -> list[int]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    applied = {
        int(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")
    }
    pending = [(version, sql) for version, sql in MIGRATIONS if version not in applied]
    if not pending:
        return []

    user_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name != 'schema_migrations'"
        )
    }
    if db_path.exists() and db_path.stat().st_size > 0 and user_tables:
        backup_path = db_path.with_suffix(f"{db_path.suffix}.bak-v{max(applied, default=0)}")
        if not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()

    completed: list[int] = []
    for version, sql in pending:
        applied_at = datetime.now(UTC).isoformat().replace("'", "''")
        try:
            connection.executescript(
                f"BEGIN IMMEDIATE;\n{sql}\n"
                f"INSERT INTO schema_migrations(version, applied_at) "
                f"VALUES ({version}, '{applied_at}');\nCOMMIT;"
            )
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            raise
        completed.append(version)
    return completed
