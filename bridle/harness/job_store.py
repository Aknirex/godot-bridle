from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from bridle.domain.assets import GeneratedAssetRecord
from bridle.domain.errors import JobNotFoundError
from bridle.domain.events import JobEvent, JsonValue
from bridle.domain.jobs import JobState, JobStatus


def utc_now() -> datetime:
    return datetime.now(UTC)


class SQLiteJobStore:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self) -> None:
        self._conn.close()

    def migrate(self) -> None:
        self._conn.executescript(
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
            """
        )
        self._conn.commit()

    def create_job(self, workflow_id: str, job_id: str | None = None) -> JobStatus:
        now = utc_now()
        status = JobStatus(
            job_id=job_id or f"job_{uuid4().hex}",
            workflow_id=workflow_id,
            state=JobState.CREATED,
            progress=0.0,
            created_at=now,
            updated_at=now,
        )
        self._conn.execute(
            """
            INSERT INTO jobs (
                job_id, workflow_id, state, progress, created_at, updated_at,
                error_code, safe_details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                status.job_id,
                status.workflow_id,
                status.state.value,
                status.progress,
                status.created_at.isoformat(),
                status.updated_at.isoformat(),
                status.error_code,
                status.safe_details,
            ),
        )
        self._conn.commit()
        return status

    def get_job(self, job_id: str) -> JobStatus:
        row = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(job_id)
        return _status_from_row(row)

    def update_job(
        self,
        job_id: str,
        state: JobState,
        *,
        progress: float | None = None,
        error_code: str | None = None,
        safe_details: str | None = None,
    ) -> JobStatus:
        current = self.get_job(job_id)
        updated = current.model_copy(
            update={
                "state": state,
                "progress": progress if progress is not None else current.progress,
                "updated_at": utc_now(),
                "error_code": error_code,
                "safe_details": safe_details,
            }
        )
        self._conn.execute(
            """
            UPDATE jobs
            SET state = ?, progress = ?, updated_at = ?, error_code = ?, safe_details = ?
            WHERE job_id = ?
            """,
            (
                updated.state.value,
                updated.progress,
                updated.updated_at.isoformat(),
                updated.error_code,
                updated.safe_details,
                job_id,
            ),
        )
        self._conn.commit()
        return updated

    def append_event(
        self,
        job_id: str,
        event_type: str,
        message: str,
        *,
        stage: str | None = None,
        progress: float | None = None,
        payload: dict[str, JsonValue] | None = None,
    ) -> JobEvent:
        self.get_job(job_id)
        sequence = self._next_sequence(job_id)
        event = JobEvent(
            id=f"evt_{uuid4().hex}",
            job_id=job_id,
            sequence=sequence,
            type=event_type,
            stage=stage,
            message=message,
            progress=progress,
            payload=payload or {},
            created_at=utc_now(),
        )
        self._conn.execute(
            """
            INSERT INTO job_events (
                id, job_id, sequence, type, stage, message, progress, payload_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.job_id,
                event.sequence,
                event.type,
                event.stage,
                event.message,
                event.progress,
                json.dumps(event.payload, ensure_ascii=False),
                event.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return event

    def replay_events(self, job_id: str, after_sequence: int = 0) -> list[JobEvent]:
        self.get_job(job_id)
        rows: Iterable[sqlite3.Row] = self._conn.execute(
            """
            SELECT * FROM job_events
            WHERE job_id = ? AND sequence > ?
            ORDER BY sequence ASC
            """,
            (job_id, after_sequence),
        ).fetchall()
        return [_event_from_row(row) for row in rows]

    def save_generated_asset(
        self,
        job_id: str,
        project_root: Path,
        record: GeneratedAssetRecord,
    ) -> GeneratedAssetRecord:
        self.get_job(job_id)
        now = utc_now().isoformat()
        self._conn.execute(
            """
            INSERT INTO generated_assets (
                asset_id, job_id, project_root, provider_id, res_path, status,
                record_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'ready', ?, ?, ?)
            ON CONFLICT(asset_id) DO UPDATE SET
                record_json = excluded.record_json,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                record.asset_id,
                job_id,
                str(project_root.resolve()),
                record.provider_id,
                record.godot_resource_path,
                record.model_dump_json(),
                now,
                now,
            ),
        )
        self._conn.commit()
        return record

    def get_generated_asset(self, asset_id: str) -> GeneratedAssetRecord | None:
        row = self._conn.execute(
            "SELECT record_json FROM generated_assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if row is None:
            return None
        return GeneratedAssetRecord.model_validate_json(row["record_json"])

    def _next_sequence(self, job_id: str) -> int:
        row = self._conn.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
            FROM job_events
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        return int(row["next_sequence"])


def _status_from_row(row: sqlite3.Row) -> JobStatus:
    return JobStatus(
        job_id=row["job_id"],
        workflow_id=row["workflow_id"],
        state=JobState(row["state"]),
        progress=row["progress"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        error_code=row["error_code"],
        safe_details=row["safe_details"],
    )


def _event_from_row(row: sqlite3.Row) -> JobEvent:
    return JobEvent(
        id=row["id"],
        job_id=row["job_id"],
        sequence=row["sequence"],
        type=row["type"],
        stage=row["stage"],
        message=row["message"],
        progress=row["progress"],
        payload=json.loads(row["payload_json"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )
