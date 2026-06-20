from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from bridle.domain.events import JsonValue
from bridle.harness.job_store import SQLiteJobStore


class BenchmarkRecorder:
    def __init__(self, store: SQLiteJobStore) -> None:
        self.store = store

    @contextmanager
    def measure(
        self,
        metric_name: str,
        *,
        job_id: str | None = None,
        stage: str | None = None,
        provider_id: str | None = None,
        metadata: dict[str, JsonValue] | None = None,
    ) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.store.record_benchmark(
                metric_name,
                job_id=job_id,
                stage=stage,
                provider_id=provider_id,
                duration_ms=round((perf_counter() - started) * 1000),
                unit="ms",
                metadata=metadata,
            )
