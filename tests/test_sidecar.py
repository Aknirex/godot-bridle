from __future__ import annotations

import asyncio
from typing import Any

from bridle.app.services import BridleAppService
from bridle.app.sidecar import JsonRpcSidecar
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator


async def make_sidecar(tmp_path):
    written: list[dict[str, Any]] = []

    async def write(message: dict[str, Any]) -> None:
        written.append(message)

    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    sidecar = JsonRpcSidecar(service, write)
    await sidecar.start()
    return sidecar, written


async def wait_for_message(
    written: list[dict[str, Any]],
    predicate,
    *,
    timeout: float = 1.0,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        for message in written:
            if predicate(message):
                return message
        await asyncio.sleep(0.01)
    raise AssertionError("Timed out waiting for sidecar message")


async def test_sidecar_sends_ready_notification(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        assert written[0]["method"] == "sidecar.ready"
        assert written[0]["params"]["protocol_version"] == "2026-06-18"
    finally:
        await sidecar.stop()


async def test_sidecar_health_request(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line('{"jsonrpc":"2.0","id":1,"method":"health","params":{}}')

        response = written[-1]
        assert response["id"] == 1
        assert response["result"]["status"] == "ok"
    finally:
        await sidecar.stop()


async def test_sidecar_submit_workflow_and_stream_events(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":1,"method":"submit_workflow",'
            '"params":{"workflow_id":"mock.sleep","duration_ms":1}}'
        )
        job_id = written[-1]["result"]["job_id"]

        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":2,"method":"stream_job_events",'
            f'"params":{{"job_id":"{job_id}","after_sequence":0}}}}'
        )

        created = await wait_for_message(
            written,
            lambda message: message.get("method") == "job.event"
            and message["params"]["event"]["type"] == "job.created",
        )
        succeeded = await wait_for_message(
            written,
            lambda message: message.get("method") == "job.event"
            and message["params"]["event"]["type"] == "job.succeeded",
        )

        assert created["params"]["event"]["sequence"] == 1
        assert succeeded["params"]["event"]["progress"] == 1.0
    finally:
        await sidecar.stop()


async def test_sidecar_reports_parse_error_for_invalid_json(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line("{not-json")

        response = written[-1]
        assert response["error"]["code"] == -32700
        assert response["error"]["message"] == "Parse error"
    finally:
        await sidecar.stop()
