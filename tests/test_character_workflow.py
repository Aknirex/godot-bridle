from __future__ import annotations

import asyncio
from pathlib import Path

from bridle.app.services import BridleAppService
from bridle.domain.assets import GodotImportResult
from bridle.domain.jobs import JobState
from bridle.harness.character_workflow import CharacterGenerationWorkflow
from bridle.harness.event_bus import JobEventBroker
from bridle.harness.job_store import SQLiteJobStore
from bridle.harness.task_orchestrator import AsyncTaskOrchestrator
from bridle.knowledge.documents import KnowledgeAnswer, KnowledgeCitation


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
        assert (record.manifest_path.parent / "godot" / "validate_import.gd").is_file()
        assert [
            event.stage
            for event in store.replay_events(ref.job_id)
            if event.type == "stage.started"
        ] == list(CharacterGenerationWorkflow.stages)
    finally:
        await service.stop()


async def test_mock_image_character_workflow_can_auto_rig(tmp_path) -> None:
    project = tmp_path / "image-game"
    project.mkdir()
    (project / "project.godot").write_text('config/name="Image Demo"\n', encoding="utf-8")
    store = SQLiteJobStore(tmp_path / "image-bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    await service.start()
    try:
        ref = await service.submit_workflow(
            {
                "workflow_id": "character_gen",
                "project_path": str(project),
                "prompt": "hero reference",
                "input_type": "image",
                "image_url": "https://assets.test/hero.png",
                "provider_id": "meshy_mock",
                "auto_rig": True,
                "poll_interval_seconds": 0,
            }
        )
        status = await wait_for_terminal_state(orchestrator, ref.job_id)
        generated = next(
            event
            for event in store.replay_events(ref.job_id)
            if event.type == "asset.generated"
        )
        record = store.get_generated_asset(str(generated.payload["asset_id"]))

        assert status.state == JobState.SUCCEEDED
        assert record is not None
        assert record.rigging["requested"] is True
        assert record.provenance["input_type"] == "image"
    finally:
        await service.stop()


async def test_mock_retexture_and_standalone_auto_rig_workflows(tmp_path) -> None:
    project = tmp_path / "asset-operations"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")
    store = SQLiteJobStore(tmp_path / "asset-operations.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    await service.start()
    try:
        for input_type in ("retexture", "auto_rig"):
            ref = await service.submit_workflow(
                {
                    "workflow_id": "character_gen",
                    "project_path": str(project),
                    "prompt": f"mock {input_type}",
                    "input_type": input_type,
                    "source_task_id": "existing_meshy_task",
                    "provider_id": "meshy_mock",
                    "poll_interval_seconds": 0,
                }
            )
            status = await wait_for_terminal_state(orchestrator, ref.job_id)
            generated = next(
                event
                for event in store.replay_events(ref.job_id)
                if event.type == "asset.generated"
            )
            record = store.get_generated_asset(str(generated.payload["asset_id"]))

            assert status.state == JobState.SUCCEEDED
            assert record is not None
            assert record.provenance["input_type"] == input_type
            assert record.rigging["requested"] is (input_type == "auto_rig")
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


async def test_import_failure_emits_cited_diagnosis_without_changing_error(
    tmp_path, monkeypatch
) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text('[application]\nconfig/name="Demo"\n')
    stderr_path = tmp_path / "stderr.log"
    stdout_path = tmp_path / "stdout.log"
    stderr_path.write_text("invalid mesh resource", encoding="utf-8")
    stdout_path.write_text("", encoding="utf-8")

    async def failed_import_check(**kwargs):
        return GodotImportResult(
            success=False,
            exit_code=3,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            safe_details="Godot import check failed with exit code 3.",
        )

    async def diagnose(project_root, import_result):
        return KnowledgeAnswer(
            question="diagnose",
            answer="Check the imported mesh path. [S1]",
            citations=[
                KnowledgeCitation(
                    label="S1",
                    chunk_id="chunk-log",
                    source_id="source-log",
                    citation="res://bridle/generated/asset/logs/godot_import_stderr.log:1-1",
                    score=0.9,
                )
            ],
            latency_ms=4,
        )

    monkeypatch.setattr(
        "bridle.harness.character_workflow.run_godot_import_check",
        failed_import_check,
    )
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    monkeypatch.setattr(service, "_diagnose_import_failure", diagnose)
    await service.start()
    try:
        ref = await service.submit_workflow(
            {
                "workflow_id": "character_gen",
                "project_path": str(project),
                "prompt": "low-poly knight",
                "provider_id": "meshy_mock",
                "godot_executable": str(Path("unused")),
                "poll_interval_seconds": 0,
            }
        )
        status = await wait_for_terminal_state(orchestrator, ref.job_id)
        history = store.replay_events(ref.job_id)
        diagnosis = next(
            event for event in history if event.type == "knowledge.diagnosis.completed"
        )

        assert status.state == JobState.FAILED
        assert status.error_code == "config_error"
        assert status.safe_details == "Godot import check failed with exit code 3."
        assert diagnosis.payload["suggestion"] == "Check the imported mesh path. [S1]"
        assert diagnosis.payload["citations"][0]["label"] == "S1"
        assert [event.type for event in history].index("knowledge.diagnosis.completed") < [
            event.type for event in history
        ].index("job.failed")
    finally:
        await service.stop()


async def test_diagnosis_failure_keeps_original_import_failure(tmp_path, monkeypatch) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")

    async def failed_import_check(**kwargs):
        log = tmp_path / "import.log"
        log.write_text("broken import", encoding="utf-8")
        return GodotImportResult(
            success=False,
            exit_code=7,
            stdout_path=log,
            stderr_path=log,
            safe_details="original import failure",
        )

    async def broken_diagnosis(project_root, import_result):
        raise RuntimeError("diagnosis backend failed")

    monkeypatch.setattr(
        "bridle.harness.character_workflow.run_godot_import_check",
        failed_import_check,
    )
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    monkeypatch.setattr(service, "_diagnose_import_failure", broken_diagnosis)
    await service.start()
    try:
        ref = await service.submit_workflow(
            {
                "workflow_id": "character_gen",
                "project_path": str(project),
                "prompt": "knight",
                "provider_id": "meshy_mock",
                "godot_executable": "unused",
                "poll_interval_seconds": 0,
            }
        )
        status = await wait_for_terminal_state(orchestrator, ref.job_id)
        history = store.replay_events(ref.job_id)

        assert status.error_code == "config_error"
        assert status.safe_details == "original import failure"
        assert any(event.type == "knowledge.diagnosis.failed" for event in history)
    finally:
        await service.stop()


async def test_diagnosis_timeout_does_not_delay_original_failure(tmp_path, monkeypatch) -> None:
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("[application]\n", encoding="utf-8")

    async def failed_import_check(**kwargs):
        log = tmp_path / "timeout-import.log"
        log.write_text("broken import", encoding="utf-8")
        return GodotImportResult(
            success=False,
            exit_code=9,
            stdout_path=log,
            stderr_path=log,
            safe_details="timed diagnosis original failure",
        )

    async def slow_diagnosis(project_root, import_result):
        await asyncio.sleep(1)
        raise AssertionError("unreachable")

    monkeypatch.setattr(
        "bridle.harness.character_workflow.run_godot_import_check",
        failed_import_check,
    )
    store = SQLiteJobStore(tmp_path / "bridle.sqlite3")
    events = JobEventBroker(store)
    orchestrator = AsyncTaskOrchestrator(store, events)
    service = BridleAppService(store, events, orchestrator)
    monkeypatch.setattr(service, "_diagnose_import_failure", slow_diagnosis)
    await service.start()
    try:
        ref = await service.submit_workflow(
            {
                "workflow_id": "character_gen",
                "project_path": str(project),
                "prompt": "knight",
                "provider_id": "meshy_mock",
                "godot_executable": "unused",
                "poll_interval_seconds": 0,
                "diagnosis_timeout_seconds": 0.01,
            }
        )
        status = await wait_for_terminal_state(orchestrator, ref.job_id)

        assert status.safe_details == "timed diagnosis original failure"
        assert any(
            event.type == "knowledge.diagnosis.failed"
            for event in store.replay_events(ref.job_id)
        )
    finally:
        await service.stop()
