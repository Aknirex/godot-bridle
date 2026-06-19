from __future__ import annotations

import hashlib

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
