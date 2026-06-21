from __future__ import annotations

from bridle.app.services import BridleAppService
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator
from bridle.knowledge.catalog import SQLiteKnowledgeCatalog
from bridle.knowledge.indexer import index_godot_project


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


async def test_service_reports_persisted_knowledge_index_status(tmp_path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('[application]\nconfig/name="Demo"\n')
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    catalog = SQLiteKnowledgeCatalog(store.db_path, connection=store.connection)
    try:
        empty = await service.get_project_knowledge_status(str(project))
        index_godot_project(project, catalog)
        indexed = await service.get_project_knowledge_status(str(project))

        assert not empty.indexed
        assert indexed.indexed
        assert indexed.documents_indexed == 1
        assert indexed.chunks_indexed == 1
        assert indexed.last_indexed_at is not None
    finally:
        store.close()


async def test_service_persists_and_reloads_provider_config(tmp_path) -> None:
    db_path = tmp_path / "bridle.sqlite3"
    store = SQLiteJobStore(db_path)
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    saved = await service.save_provider_config(
        {
            "provider_id": "claude_custom",
            "kind": "llm",
            "backend": "litellm",
            "model": "anthropic/user-selected-model",
            "api_key_env": "ANTHROPIC_API_KEY",
            "capabilities": ["llm.chat", "llm.stream"],
            "default_for": [],
        }
    )
    store.close()

    reopened = SQLiteJobStore(db_path)
    reopened_events = JobEventBroker(reopened)
    reloaded = BridleAppService(
        reopened,
        reopened_events,
        AsyncTaskOrchestrator(reopened, reopened_events),
    )
    try:
        providers = await reloaded.list_providers()

        assert saved.provider_id == "claude_custom"
        assert any(provider["provider_id"] == "claude_custom" for provider in providers)
    finally:
        reopened.close()


async def test_service_rejects_plaintext_provider_secret(tmp_path) -> None:
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    service = BridleAppService(store, events, AsyncTaskOrchestrator(store, events))
    try:
        try:
            await service.save_provider_config(
                {
                    "provider_id": "unsafe",
                    "kind": "llm",
                    "api_key": "sk-plaintext",
                }
            )
        except Exception as error:
            assert getattr(error, "safe_details", "") == (
                "Provider config must not contain plaintext secrets. Use api_key_env instead."
            )
        else:
            raise AssertionError("Expected plaintext provider secret to be rejected")
    finally:
        store.close()
