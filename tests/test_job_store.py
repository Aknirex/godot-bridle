from __future__ import annotations

import hashlib
import sqlite3

from bridle.domain.assets import DownloadedAsset
from bridle.domain.jobs import JobState
from bridle.godot.glb import inspect_glb
from bridle.godot.import_pipeline import prepare_godot_asset_files
from bridle.harness.job_store import SQLiteJobStore


def test_job_store_appends_sequenced_events_and_replays_history(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        job = store.create_job("character_gen", job_id="job_test")
        created = store.append_event(job.job_id, "job.created", "Created")
        queued = store.append_event(job.job_id, "job.queued", "Queued")

        replayed = store.replay_events(job.job_id)

        assert [event.sequence for event in replayed] == [1, 2]
        assert [event.id for event in replayed] == [created.id, queued.id]
    finally:
        store.close()


def test_job_store_replays_after_sequence(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        job = store.create_job("character_gen", job_id="job_test")
        store.append_event(job.job_id, "job.created", "Created")
        queued = store.append_event(job.job_id, "job.queued", "Queued")

        replayed = store.replay_events(job.job_id, after_sequence=1)

        assert [event.id for event in replayed] == [queued.id]
    finally:
        store.close()


def test_job_store_persists_status_updates(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        job = store.create_job("character_gen", job_id="job_test")

        updated = store.update_job(job.job_id, JobState.RUNNING, progress=0.25)
        loaded = store.get_job(job.job_id)

        assert updated.state == JobState.RUNNING
        assert loaded.state == JobState.RUNNING
        assert loaded.progress == 0.25
    finally:
        store.close()


def test_job_store_recovers_interrupted_jobs_to_diagnostic_terminal_states(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        running = store.create_job("character_gen", job_id="job_running")
        cancelling = store.create_job("character_gen", job_id="job_cancelling")
        succeeded = store.create_job("character_gen", job_id="job_succeeded")
        store.update_job(running.job_id, JobState.WAITING_PROVIDER, progress=0.25)
        store.update_job(cancelling.job_id, JobState.CANCEL_REQUESTED)
        store.update_job(succeeded.job_id, JobState.SUCCEEDED, progress=1.0)

        recovered = store.recover_interrupted_jobs()

        assert {job.job_id for job in recovered} == {running.job_id, cancelling.job_id}
        interrupted = store.get_job(running.job_id)
        assert interrupted.state == JobState.FAILED
        assert interrupted.error_code == "sidecar_interrupted"
        assert store.replay_events(running.job_id)[-1].type == "job.failed"
        assert store.get_job(cancelling.job_id).state == JobState.CANCELLED
        assert store.replay_events(cancelling.job_id)[-1].type == "job.cancelled"
        assert store.get_job(succeeded.job_id).state == JobState.SUCCEEDED
    finally:
        store.close()


def test_job_store_persists_generated_asset_record(tmp_path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    source = project / "source.glb"
    data = b"glTF" + (2).to_bytes(4, "little") + (20).to_bytes(4, "little") + b"\0" * 8
    source.write_bytes(data)
    downloaded = DownloadedAsset(
        source_url="mock://asset.glb",
        path=source,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=len(data),
    )
    record = prepare_godot_asset_files(
        project_root=project,
        asset_id="asset_test",
        provider_id="mock",
        downloaded=downloaded,
        inspection=inspect_glb(source),
    )
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        job = store.create_job("character_gen", job_id="job_test")
        store.save_generated_asset(job.job_id, project, record)
        loaded = store.get_generated_asset(record.asset_id)
        assert loaded is not None
        assert loaded.sha256 == record.sha256
    finally:
        store.close()


def test_migrations_upgrade_legacy_database_and_are_idempotent(tmp_path) -> None:
    db_path = tmp_path / "bridle.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE jobs (job_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL, "
        "state TEXT NOT NULL, progress REAL, created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL, error_code TEXT, safe_details TEXT)"
    )
    connection.commit()
    connection.close()

    store = SQLiteJobStore(db_path)
    store.close()
    reopened = SQLiteJobStore(db_path)
    try:
        versions = reopened._conn.execute(  # noqa: SLF001 - verifies persisted schema state
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        tables = {
            row[0]
            for row in reopened._conn.execute(  # noqa: SLF001
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert [row[0] for row in versions] == [1, 2, 3, 4]
        assert {"projects", "provider_configs", "benchmark_samples"} <= tables
        assert db_path.with_suffix(".sqlite3.bak-v0").exists()
    finally:
        reopened.close()


def test_job_store_persists_project_provider_and_benchmark(tmp_path) -> None:
    from bridle.app.services import default_provider_configs
    from bridle.godot.project import detect_project

    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text(
        'config/name="Demo"\nconfig/features=PackedStringArray("4.3")\n',
        encoding="utf-8",
    )
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        store.save_project(detect_project(project))
        store.save_provider_config(default_provider_configs()[0])
        sample_id = store.record_benchmark("test.duration", duration_ms=12, unit="ms")

        project_row = store._conn.execute("SELECT * FROM projects").fetchone()  # noqa: SLF001
        provider_row = store._conn.execute(  # noqa: SLF001
            "SELECT * FROM provider_configs"
        ).fetchone()
        sample_row = store._conn.execute(  # noqa: SLF001
            "SELECT * FROM benchmark_samples WHERE id = ?", (sample_id,)
        ).fetchone()
        assert project_row["godot_version"] == "4.3"
        assert provider_row["api_key_env"] == "DEEPSEEK_API_KEY"
        assert store.list_provider_configs()[0].provider_id == "deepseek"
        assert sample_row["duration_ms"] == 12
    finally:
        store.close()
