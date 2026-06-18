from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from bridle.domain.errors import BridleError
from bridle.domain.jobs import JobRef, JobState, JobStatus
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore

JobHandler = Callable[["JobContext"], Awaitable[None]]


@dataclass(frozen=True)
class JobContext:
    job_id: str
    workflow_id: str
    events: JobEventBroker
    store: SQLiteJobStore

    async def emit(
        self,
        event_type: str,
        message: str,
        *,
        stage: str | None = None,
        progress: float | None = None,
    ) -> None:
        await self.events.emit(
            self.job_id,
            event_type,
            message,
            stage=stage,
            progress=progress,
        )


@dataclass(frozen=True)
class QueuedJob:
    job_id: str
    workflow_id: str
    handler: JobHandler


class AsyncTaskOrchestrator:
    def __init__(
        self,
        store: SQLiteJobStore,
        events: JobEventBroker,
        *,
        queue_size: int | None = None,
        worker_count: int = 1,
    ) -> None:
        self.store = store
        self.events = events
        maxsize = queue_size if queue_size is not None else max(4, os.cpu_count() or 1)
        self._queue: asyncio.Queue[QueuedJob] = asyncio.Queue(maxsize=maxsize)
        self._worker_count = worker_count
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._workers:
            return
        self._workers = [
            asyncio.create_task(self._worker_loop(), name=f"bridle-worker-{index}")
            for index in range(self._worker_count)
        ]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    async def submit(self, workflow_id: str, handler: JobHandler) -> JobRef:
        job = self.store.create_job(workflow_id)
        await self.events.emit(job.job_id, "job.created", "Job created", progress=0.0)
        self.store.update_job(job.job_id, JobState.QUEUED, progress=0.0)
        await self.events.emit(job.job_id, "job.queued", "Job queued", progress=0.0)
        await self._queue.put(
            QueuedJob(job_id=job.job_id, workflow_id=workflow_id, handler=handler)
        )
        return JobRef(job_id=job.job_id)

    def get_status(self, job_id: str) -> JobStatus:
        return self.store.get_job(job_id)

    def cancel_job(self, job_id: str) -> JobStatus:
        return self.store.update_job(job_id, JobState.CANCEL_REQUESTED)

    async def _worker_loop(self) -> None:
        while True:
            queued = await self._queue.get()
            try:
                await self._run_job(queued)
            finally:
                self._queue.task_done()

    async def _run_job(self, queued: QueuedJob) -> None:
        current = self.store.get_job(queued.job_id)
        if current.state == JobState.CANCEL_REQUESTED:
            self.store.update_job(queued.job_id, JobState.CANCELLED)
            await self.events.emit(queued.job_id, "job.cancelled", "Job cancelled")
            return

        self.store.update_job(queued.job_id, JobState.RUNNING)
        await self.events.emit(queued.job_id, "job.started", "Job started")
        context = JobContext(
            job_id=queued.job_id,
            workflow_id=queued.workflow_id,
            events=self.events,
            store=self.store,
        )
        try:
            await queued.handler(context)
        except BridleError as error:
            self.store.update_job(
                queued.job_id,
                JobState.FAILED,
                error_code=error.code.value,
                safe_details=error.safe_details,
            )
            await self.events.emit(
                queued.job_id,
                "job.failed",
                "Job failed",
                payload={"error_code": error.code.value, "safe_details": error.safe_details},
            )
            return
        except Exception:
            safe_details = "An unexpected error occurred."
            self.store.update_job(
                queued.job_id,
                JobState.FAILED,
                error_code="internal_error",
                safe_details=safe_details,
            )
            await self.events.emit(
                queued.job_id,
                "job.failed",
                "Job failed",
                payload={"error_code": "internal_error", "safe_details": safe_details},
            )
            return

        latest = self.store.get_job(queued.job_id)
        if latest.state == JobState.CANCEL_REQUESTED:
            self.store.update_job(queued.job_id, JobState.CANCELLED)
            await self.events.emit(queued.job_id, "job.cancelled", "Job cancelled")
            return

        self.store.update_job(queued.job_id, JobState.SUCCEEDED, progress=1.0)
        await self.events.emit(queued.job_id, "job.succeeded", "Job succeeded", progress=1.0)
