from __future__ import annotations

import asyncio

from bridle.app.services import BridleAppService
from bridle.domain.jobs import JobState
from bridle.harness.character_workflow import CharacterGenerationWorkflow
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator


async def wait_for_terminal_state(
    orchestrator: AsyncTaskOrchestrator, job_id: str, timeout: float = 2.0
):
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        status = orchestrator.get_status(job_id)
        if status.state in {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED}:
            return status
        await asyncio.sleep(0.01)
    raise AssertionError("Workflow did not reach a terminal state")


async def test_mock_character_workflow_runs_full_asset_pipeline(tmp_path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    await service.start()
    try:
        ref = await service.submit_workflow(
            {
                "workflow_id": "character_gen",
                "project_path": str(project),
                "prompt": "low-poly knight",
                "provider_id": "meshy_mock",
                "poll_interval_seconds": 0,
            }
        )
        status = await wait_for_terminal_state(orchestrator, ref.job_id)

        assert status.state == JobState.SUCCEEDED
        generated = [
            event
            for event in store.replay_events(ref.job_id)
            if event.type == "asset.generated"
        ]
        assert len(generated) == 1
        asset_id = generated[0].payload["asset_id"]
        record = store.get_generated_asset(str(asset_id))
        assert record is not None
        assert record.source_path.is_file()
        assert record.manifest_path.is_file()
        assert (record.manifest_path.parent / "godot" / "preview_scene.tscn").is_file()
        assert [
            event.stage
            for event in store.replay_events(ref.job_id)
            if event.type == "stage.started"
        ] == list(CharacterGenerationWorkflow.stages)
    finally:
        await service.stop()


async def test_character_workflow_honors_cancellation(tmp_path) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    ref = await service.submit_workflow(
        {
            "workflow_id": "character_gen",
            "project_path": str(project),
            "prompt": "knight",
        }
    )
    await service.cancel_job(ref.job_id)
    await service.start()
    try:
        status = await wait_for_terminal_state(orchestrator, ref.job_id)
        assert status.state == JobState.CANCELLED
    finally:
        await service.stop()
