from __future__ import annotations

import asyncio

from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore


async def anext_with_timeout(iterator, timeout: float = 1.0):
    return await asyncio.wait_for(anext(iterator), timeout=timeout)


async def test_stream_replays_events_emitted_before_subscription(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    try:
        broker = JobEventBroker(store)
        job = store.create_job("character_gen", job_id="job_test")
        await broker.emit(job.job_id, "job.created", "Created")
        await broker.emit(job.job_id, "job.queued", "Queued")

        stream = broker.stream_job_events(job.job_id)
        first = await anext_with_timeout(stream)
        second = await anext_with_timeout(stream)

        assert [first.type, second.type] == ["job.created", "job.queued"]
    finally:
        await stream.aclose()
        store.close()


async def test_stream_switches_from_replay_to_live_events_without_duplicates(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    stream = None
    try:
        broker = JobEventBroker(store)
        job = store.create_job("character_gen", job_id="job_test")
        await broker.emit(job.job_id, "job.created", "Created")

        stream = broker.stream_job_events(job.job_id)
        replayed = await anext_with_timeout(stream)
        await broker.emit(job.job_id, "job.started", "Started")
        live = await anext_with_timeout(stream)

        assert replayed.type == "job.created"
        assert live.type == "job.started"
        assert live.sequence == 2
    finally:
        if stream is not None:
            await stream.aclose()
        store.close()
