from __future__ import annotations

import asyncio
from pathlib import Path

from bridle import __version__
from bridle.domain.jobs import JobRef, JobStatus
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator, JobContext


class BridleAppService:
    def __init__(
        self,
        store: SQLiteJobStore,
        events: JobEventBroker,
        orchestrator: AsyncTaskOrchestrator,
    ) -> None:
        self.store = store
        self.events = events
        self.orchestrator = orchestrator

    @classmethod
    def create(cls, db_path: Path) -> BridleAppService:
        store = SQLiteJobStore(db_path)
        events = JobEventBroker(store)
        orchestrator = AsyncTaskOrchestrator(store, events)
        return cls(store=store, events=events, orchestrator=orchestrator)

    async def start(self) -> None:
        await self.orchestrator.start()

    async def stop(self) -> None:
        await self.orchestrator.stop()
        self.store.close()

    async def health(self) -> dict[str, str]:
        return {
            "name": "godot-bridle",
            "version": __version__,
            "status": "ok",
        }

    async def submit_workflow(self, params: dict) -> JobRef:
        workflow_id = str(params.get("workflow_id", "mock.sleep"))
        duration_ms = int(params.get("duration_ms", 10))

        async def handler(context: JobContext) -> None:
            await context.emit("job.progress", "Workflow started", progress=0.1)
            await asyncio.sleep(max(duration_ms, 0) / 1000)
            await context.emit("job.progress", "Workflow finished", progress=0.9)

        return await self.orchestrator.submit(workflow_id, handler)

    async def get_job_status(self, job_id: str) -> JobStatus:
        return self.orchestrator.get_status(job_id)

    async def cancel_job(self, job_id: str) -> JobStatus:
        return self.orchestrator.cancel_job(job_id)
