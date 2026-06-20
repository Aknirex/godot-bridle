from __future__ import annotations

from bridle.app.services import BridleAppService
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator


async def test_service_lists_default_providers(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    try:
        providers = await service.list_providers()

        assert [provider["provider_id"] for provider in providers] == [
            "deepseek",
            "openai_embedding",
            "meshy_mock",
            "meshy",
        ]
    finally:
        store.close()


async def test_service_opens_godot_project(tmp_path) -> None:
    (tmp_path / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    try:
        summary = await service.open_project(str(tmp_path))

        assert summary.project_name == "Demo"
    finally:
        store.close()


async def test_service_tests_default_mock_meshy(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    try:
        health = await service.test_provider("meshy_mock")

        assert health.status == "ok"
    finally:
        store.close()


async def test_service_tests_deepseek_as_missing_key_by_default(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    try:
        health = await service.test_provider("deepseek")

        assert health.status == "missing_key"
    finally:
        store.close()


async def test_service_tests_embedding_provider_as_missing_key_by_default(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    try:
        health = await service.test_provider("openai_embedding")

        assert health.status == "missing_key"
    finally:
        store.close()
