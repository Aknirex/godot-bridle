from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import gettempdir
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from bridle.app.services import BridleAppService
from bridle.domain.errors import BridleError, BridleErrorCode

PROTOCOL_VERSION = "2026-06-18"
JSONRPC_VERSION = "2.0"

JsonWriter = Callable[[dict[str, Any]], Awaitable[None]]


class JsonRpcProtocolError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class JsonRpcSidecar:
    def __init__(self, service: BridleAppService, write: JsonWriter) -> None:
        self.service = service
        self.write = write
        self._stream_tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        await self.service.start()
        await self.write(
            {
                "jsonrpc": JSONRPC_VERSION,
                "method": "sidecar.ready",
                "params": {
                    "protocol_version": PROTOCOL_VERSION,
                    "capabilities": ["request_response", "job.event"],
                },
            }
        )

    async def stop(self) -> None:
        for task in self._stream_tasks.values():
            task.cancel()
        await asyncio.gather(*self._stream_tasks.values(), return_exceptions=True)
        self._stream_tasks = {}
        await self.service.stop()

    async def handle_line(self, line: str) -> None:
        request_id: Any = None
        try:
            request = self._parse_request(line)
            request_id = request.get("id")
            result = await self._dispatch(request)
        except JsonRpcProtocolError as error:
            await self._write_error(request_id, error.code, error.message)
            return

        if request_id is not None:
            await self._write_result(request_id, result)

    def _parse_request(self, line: str) -> dict[str, Any]:
        try:
            request = json.loads(line)
        except json.JSONDecodeError as error:
            raise JsonRpcProtocolError(-32700, "Parse error") from error

        if not isinstance(request, dict):
            raise JsonRpcProtocolError(-32600, "Invalid request")
        if request.get("jsonrpc") != JSONRPC_VERSION:
            raise JsonRpcProtocolError(-32600, "Invalid JSON-RPC version")
        if not isinstance(request.get("method"), str):
            raise JsonRpcProtocolError(-32600, "Invalid method")
        params = request.get("params", {})
        if params is not None and not isinstance(params, dict):
            raise JsonRpcProtocolError(-32602, "Invalid params")
        return request

    async def _dispatch(self, request: dict[str, Any]) -> Any:
        method = request["method"]
        params = request.get("params") or {}
        try:
            if method == "health":
                return await self.service.health()
            if method == "open_project":
                path = _required_str(params, "path")
                return _to_jsonable(await self.service.open_project(path))
            if method == "list_providers":
                return await self.service.list_providers()
            if method == "test_provider":
                provider_id = _required_str(params, "provider_id")
                return _to_jsonable(await self.service.test_provider(provider_id))
            if method == "submit_workflow":
                return _to_jsonable(await self.service.submit_workflow(params))
            if method == "get_job_status":
                job_id = _required_str(params, "job_id")
                return _to_jsonable(await self.service.get_job_status(job_id))
            if method == "cancel_job":
                job_id = _required_str(params, "job_id")
                return _to_jsonable(await self.service.cancel_job(job_id))
            if method == "index_project_knowledge":
                path = _required_str(params, "project_path")
                return _to_jsonable(await self.service.index_project_knowledge(path))
            if method == "query_project_knowledge":
                path = _required_str(params, "project_path")
                question = _required_str(params, "question")
                top_k, filters = _knowledge_query_options(params)
                hits = await self.service.query_project_knowledge(
                    path,
                    question,
                    top_k=top_k,
                    filters=filters,
                )
                return [_to_jsonable(hit) for hit in hits]
            if method == "ask_project_knowledge":
                path = _required_str(params, "project_path")
                question = _required_str(params, "question")
                top_k, filters = _knowledge_query_options(params)
                return _to_jsonable(
                    await self.service.ask_project_knowledge(
                        path,
                        question,
                        top_k=top_k,
                        filters=filters,
                    )
                )
            if method == "stream_job_events":
                return await self._start_event_stream(params)
        except BridleError as error:
            code = _json_rpc_code_for(error.code)
            raise JsonRpcProtocolError(code, error.safe_details) from error

        raise JsonRpcProtocolError(-32601, f"Method not found: {method}")

    async def _start_event_stream(self, params: dict[str, Any]) -> dict[str, str]:
        job_id = _required_str(params, "job_id")
        after_sequence = int(params.get("after_sequence", 0))
        stream_id = f"stream_{uuid4().hex}"
        task = asyncio.create_task(
            self._pump_job_events(stream_id, job_id, after_sequence),
            name=f"bridle-stream-{stream_id}",
        )
        self._stream_tasks[stream_id] = task
        task.add_done_callback(lambda _: self._stream_tasks.pop(stream_id, None))
        return {"stream_id": stream_id}

    async def _pump_job_events(self, stream_id: str, job_id: str, after_sequence: int) -> None:
        async for event in self.service.events.stream_job_events(
            job_id,
            after_sequence=after_sequence,
        ):
            await self.write(
                {
                    "jsonrpc": JSONRPC_VERSION,
                    "method": "job.event",
                    "params": {
                        "stream_id": stream_id,
                        "event": _to_jsonable(event),
                    },
                }
            )

    async def _write_result(self, request_id: Any, result: Any) -> None:
        await self.write({"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result})

    async def _write_error(
        self,
        request_id: Any,
        code: int,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        error: dict[str, Any] = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        await self.write({"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error})


def _required_str(params: dict[str, Any], name: str) -> str:
    value = params.get(name)
    if not isinstance(value, str) or not value:
        raise JsonRpcProtocolError(-32602, f"Missing string param: {name}")
    return value


def _knowledge_query_options(
    params: dict[str, Any],
) -> tuple[int, dict[str, Any] | None]:
    try:
        top_k = int(params.get("top_k", 5))
    except (TypeError, ValueError) as error:
        raise JsonRpcProtocolError(-32602, "top_k must be an integer") from error
    if not 1 <= top_k <= 20:
        raise JsonRpcProtocolError(-32602, "top_k must be between 1 and 20")
    filters = params.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise JsonRpcProtocolError(-32602, "filters must be an object")
    return top_k, filters


def _json_rpc_code_for(code: BridleErrorCode) -> int:
    if code == BridleErrorCode.JOB_NOT_FOUND:
        return -32004
    if code in {BridleErrorCode.CONFIG_ERROR, BridleErrorCode.PROVIDER_CAPABILITY_ERROR}:
        return -32602
    return -32000


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


async def run_stdio_sidecar(db_path: Path | None = None) -> int:
    path = db_path or Path(gettempdir()) / "godot-bridle" / "sidecar.sqlite3"
    service = BridleAppService.create(path)
    write_lock = asyncio.Lock()

    async def write(message: dict[str, Any]) -> None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        async with write_lock:
            print(encoded, flush=True)

    sidecar = JsonRpcSidecar(service, write)
    await sidecar.start()
    try:
        while line := await asyncio.to_thread(sys.stdin.readline):
            await sidecar.handle_line(line)
    finally:
        await sidecar.stop()
    return 0
