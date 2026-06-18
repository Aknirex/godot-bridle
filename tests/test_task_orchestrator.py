from __future__ import annotations

import asyncio

from bridle.domain.jobs import JobState
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator, JobContext


async def wait_for_state(
    orchestrator: AsyncTaskOrchestrator,
    job_id: str,
    state: JobState,
    *,
    timeout: float = 1.0,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if orchestrator.get_status(job_id).state == state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Job {job_id} did not reach {state.value}")


async def test_orchestrator_runs_job_in_background_and_persists_events(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    orchestrator = None
    try:
        broker = JobEventBroker(store)
        orchestrator = AsyncTaskOrchestrator(store, broker)
        await orchestrator.start()

        async def handler(context: JobContext) -> None:
            await asyncio.sleep(0.01)
            await context.emit("job.progress", "Halfway", progress=0.5)

        ref = await orchestrator.submit("character_gen", handler)

        assert orchestrator.get_status(ref.job_id).state in {JobState.QUEUED, JobState.RUNNING}
        await wait_for_state(orchestrator, ref.job_id, JobState.SUCCEEDED)

        event_types = [event.type for event in store.replay_events(ref.job_id)]
        assert event_types == [
            "job.created",
            "job.queued",
            "job.started",
            "job.progress",
            "job.succeeded",
        ]
    finally:
        if orchestrator is not None:
            await orchestrator.stop()
        store.close()


async def test_orchestrator_can_cancel_before_worker_starts(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    orchestrator = None
    try:
        broker = JobEventBroker(store)
        orchestrator = AsyncTaskOrchestrator(store, broker)

        async def handler(context: JobContext) -> None:
            await context.emit("job.progress", "Should not run")

        ref = await orchestrator.submit("character_gen", handler)
        orchestrator.cancel_job(ref.job_id)
        await orchestrator.start()
        await wait_for_state(orchestrator, ref.job_id, JobState.CANCELLED)

        event_types = [event.type for event in store.replay_events(ref.job_id)]
        assert event_types[-1] == "job.cancelled"
    finally:
        if orchestrator is not None:
            await orchestrator.stop()
        store.close()
