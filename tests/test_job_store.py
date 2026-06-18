from __future__ import annotations

from bridle.domain.jobs import JobState
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
