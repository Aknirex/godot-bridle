from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from bridle.domain.events import JobEvent, JsonValue
from bridle.harness.job_store import SQLiteJobStore


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[JobEvent]]] = defaultdict(set)

    def subscribe(self, job_id: str) -> asyncio.Queue[JobEvent]:
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        self._subscribers[job_id].add(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[JobEvent]) -> None:
        subscribers = self._subscribers.get(job_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    async def publish(self, event: JobEvent) -> None:
        for queue in list(self._subscribers.get(event.job_id, ())):
            await queue.put(event)


class JobEventBroker:
    def __init__(self, store: SQLiteJobStore, event_bus: InMemoryEventBus | None = None) -> None:
        self.store = store
        self.event_bus = event_bus or InMemoryEventBus()

    async def emit(
        self,
        job_id: str,
        event_type: str,
        message: str,
        *,
        stage: str | None = None,
        progress: float | None = None,
        payload: dict[str, JsonValue] | None = None,
    ) -> JobEvent:
        event = self.store.append_event(
            job_id,
            event_type,
            message,
            stage=stage,
            progress=progress,
            payload=payload,
        )
        await self.event_bus.publish(event)
        return event

    async def stream_job_events(
        self,
        job_id: str,
        *,
        after_sequence: int = 0,
    ) -> AsyncIterator[JobEvent]:
        live_queue = self.event_bus.subscribe(job_id)
        last_sequence = after_sequence
        try:
            for event in self.store.replay_events(job_id, after_sequence=after_sequence):
                last_sequence = max(last_sequence, event.sequence)
                yield event

            while True:
                event = await live_queue.get()
                if event.sequence <= last_sequence:
                    continue
                last_sequence = event.sequence
                yield event
        finally:
            self.event_bus.unsubscribe(job_id, live_queue)
