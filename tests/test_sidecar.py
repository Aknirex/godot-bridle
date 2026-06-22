from __future__ import annotations

import asyncio
from typing import Any

from bridle.app.services import BridleAppService
from bridle.app.sidecar import JsonRpcSidecar
from bridle.domain.providers import LlmChatResponse
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.embeddings import DeterministicEmbeddingProvider
from bridle.knowledge.service import ProjectKnowledgeService
from bridle.knowledge.vector_store import InMemoryVectorStore


class FakeKnowledgeAnswerProvider:
    async def chat(self, request):
        return LlmChatResponse(content="Player speed is 10. [S1]")


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
        assert written[0]["params"]["protocol_version"] == "2026-06-22"
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


async def test_sidecar_opens_project(tmp_path) -> None:
    (tmp_path / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    sidecar, written = await make_sidecar(tmp_path / "db")
    try:
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":1,"method":"open_project",'
            f'"params":{{"path":"{tmp_path.as_posix()}"}}}}'
        )

        assert written[-1]["result"]["project_name"] == "Demo"
    finally:
        await sidecar.stop()


async def test_sidecar_lists_and_tests_providers(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":1,"method":"list_providers","params":{}}'
        )
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":2,"method":"test_provider",'
            '"params":{"provider_id":"meshy_mock"}}'
        )
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":3,"method":"test_provider",'
            '"params":{"provider_id":"openai_embedding"}}'
        )

        assert written[-3]["result"][0]["provider_id"] == "deepseek"
        assert written[-2]["result"]["status"] == "ok"
        assert written[-1]["result"]["status"] == "missing_key"
    finally:
        await sidecar.stop()


async def test_sidecar_saves_provider_metadata_without_plaintext_key(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":4,"method":"save_provider_config",'
            '"params":{"provider_id":"openai_custom","kind":"llm",'
            '"backend":"litellm","model":"openai/user-selected-model",'
            '"api_key_env":"OPENAI_API_KEY","capabilities":["llm.chat"]}}'
        )
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":5,"method":"save_provider_config",'
            '"params":{"provider_id":"unsafe","kind":"llm","api_key":"secret"}}'
        )

        assert written[-2]["result"]["provider_id"] == "openai_custom"
        assert written[-1]["error"]["code"] == -32602
        assert "plaintext secrets" in written[-1]["error"]["message"]
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


async def test_sidecar_indexes_and_queries_project_knowledge(tmp_path, monkeypatch) -> None:
    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr("bridle.knowledge.service.asyncio.to_thread", run_inline)
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    (project / "player.gd").write_text(
        "func move():\n    var speed = 10\n",
        encoding="utf-8",
    )
    sidecar, written = await make_sidecar(tmp_path / "state")
    knowledge = ProjectKnowledgeService(
        SQLiteKnowledgeCatalog(tmp_path / "knowledge.sqlite3"),
        DeterministicEmbeddingProvider(),
        InMemoryVectorStore(),
        answer_provider=FakeKnowledgeAnswerProvider(),
    )
    sidecar.service._knowledge_services[project.resolve()] = knowledge  # noqa: SLF001
    try:
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":1,"method":"index_project_knowledge",'
            f'"params":{{"project_path":"{project.as_posix()}"}}}}'
        )
        job_id = written[-1]["result"]["job_id"]
        deadline = asyncio.get_running_loop().time() + 2
        while asyncio.get_running_loop().time() < deadline:
            status = await sidecar.service.get_job_status(job_id)
            if status.state.value == "succeeded":
                break
            await asyncio.sleep(0.01)
        else:
            raise AssertionError("Knowledge indexing did not complete")
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":2,"method":"query_project_knowledge",'
            f'"params":{{"project_path":"{project.as_posix()}",'
            '"question":"player movement speed","top_k":2}}'
        )

        assert written[-1]["result"][0]["citation"].startswith("res://player.gd:")
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":3,"method":"ask_project_knowledge",'
            f'"params":{{"project_path":"{project.as_posix()}",'
            '"question":"What is the player speed?","top_k":2}}'
        )

        assert written[-1]["result"]["answer"] == "Player speed is 10. [S1]"
        assert written[-1]["result"]["citations"][0]["citation"].startswith(
            "res://player.gd:"
        )
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


async def test_sidecar_preserves_request_id_for_method_error(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line('{"jsonrpc":"2.0","id":7,"method":"unknown"}')

        assert written[-1]["id"] == 7
        assert written[-1]["error"]["code"] == -32601
    finally:
        await sidecar.stop()


async def test_sidecar_rejects_out_of_range_knowledge_top_k(tmp_path) -> None:
    sidecar, written = await make_sidecar(tmp_path)
    try:
        await sidecar.handle_line(
            '{"jsonrpc":"2.0","id":8,"method":"query_project_knowledge",'
            '"params":{"project_path":"unused","question":"test","top_k":21}}'
        )

        assert written[-1]["id"] == 8
        assert written[-1]["error"] == {
            "code": -32602,
            "message": "top_k must be between 1 and 20",
        }
    finally:
        await sidecar.stop()
