from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from bridle.domain.assets import DownloadedAsset, GeneratedAssetRecord
from bridle.domain.errors import ConfigError, ProviderError
from bridle.domain.jobs import JobState
from bridle.domain.providers import (
    AssetGenerationRequest,
    AssetTaskRef,
    AssetTaskResult,
    AssetTaskStatus,
    LlmChatRequest,
    LlmChatResponse,
    ProviderConfig,
)
from bridle.godot.cli import run_godot_import_check
from bridle.godot.downloader import download_asset
from bridle.godot.glb import inspect_glb
from bridle.godot.import_pipeline import prepare_godot_asset_files
from bridle.godot.project import detect_project, generated_asset_dir
from bridle.harness.task_orchestrator import JobContext


class AssetProvider(Protocol):
    config: ProviderConfig

    async def submit_text_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef: ...
    async def submit_refine(self, preview_task_id: str) -> AssetTaskRef: ...
    async def poll_task(self, task_id: str) -> AssetTaskResult: ...


class LlmProvider(Protocol):
    async def chat(self, request: LlmChatRequest) -> LlmChatResponse: ...


class CharacterGenerationRequest(BaseModel):
    project_path: Path
    prompt: str = Field(min_length=1)
    provider_id: str = "meshy_mock"
    godot_executable: Path | None = None
    poll_interval_seconds: float = Field(default=1.0, ge=0)
    poll_timeout_seconds: float = Field(default=300.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    enhance_prompt: bool = False


DownloadFunction = Callable[..., Awaitable[DownloadedAsset]]


class CharacterGenerationWorkflow:
    stages = (
        "validate_project",
        "resolve_providers",
        "submit_text_to_3d_preview",
        "poll_preview",
        "submit_refine",
        "poll_refine",
        "download_assets",
        "inspect_glb",
        "prepare_godot_files",
        "run_godot_import_check",
        "generate_sample_scene_or_script",
        "finalize_asset_record",
    )

    def __init__(
        self,
        request: CharacterGenerationRequest,
        provider: AssetProvider,
        *,
        llm_provider: LlmProvider | None = None,
        downloader: DownloadFunction = download_asset,
    ) -> None:
        self.request = request
        self.provider = provider
        self.llm_provider = llm_provider
        self.downloader = downloader
        self.asset_id = f"asset_{uuid4().hex}"

    async def run(self, context: JobContext) -> GeneratedAssetRecord:
        project_root = self.request.project_path.resolve()
        await self._stage(context, 0, "Validating Godot project")
        detect_project(project_root)

        await self._stage(context, 1, "Resolving asset provider")
        if self.request.provider_id != self.provider.config.provider_id:
            raise ConfigError("Resolved provider does not match the workflow request.")
        prompt = self.request.prompt
        if self.request.enhance_prompt:
            if self.llm_provider is None:
                raise ConfigError("Prompt enhancement requires a configured LLM provider.")
            response = await self.llm_provider.chat(
                LlmChatRequest(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Rewrite the request as a concise text-to-3D prompt. "
                                "Return only the prompt."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=200,
                )
            )
            prompt = response.content.strip() or prompt
            await context.emit(
                "prompt.enhanced",
                "Generation prompt was enhanced by the LLM provider",
                stage="resolve_providers",
            )

        await self._stage(context, 2, "Submitting Meshy preview")
        preview = await self._retry(
            context,
            "submit_text_to_3d_preview",
            lambda: self.provider.submit_text_to_3d(
                AssetGenerationRequest(prompt=prompt)
            ),
        )

        await self._stage(context, 3, "Waiting for Meshy preview", JobState.WAITING_PROVIDER)
        await self._poll_until_complete(context, preview.task_id, "poll_preview")

        await self._stage(context, 4, "Submitting Meshy refine")
        refined = await self._retry(
            context,
            "submit_refine",
            lambda: self.provider.submit_refine(preview.task_id),
        )

        await self._stage(context, 5, "Waiting for Meshy refine", JobState.WAITING_PROVIDER)
        result = await self._poll_until_complete(context, refined.task_id, "poll_refine")
        if not result.asset_urls:
            raise ProviderError("Provider completed without a downloadable GLB URL.")

        await self._stage(context, 6, "Downloading generated GLB", JobState.DOWNLOADING)
        destination = generated_asset_dir(project_root, self.asset_id) / "source"
        downloaded = await self._download(result.asset_urls[0], project_root, destination)

        await self._stage(context, 7, "Inspecting generated GLB")
        inspection = inspect_glb(downloaded.path)
        if not inspection.is_glb or inspection.errors:
            raise ProviderError("Generated asset is not a valid GLB file.")

        await self._stage(context, 8, "Preparing Godot asset files")
        record = prepare_godot_asset_files(
            project_root=project_root,
            asset_id=self.asset_id,
            provider_id=self.request.provider_id,
            downloaded=downloaded,
            inspection=inspection,
        )

        await self._stage(context, 9, "Running Godot import check", JobState.IMPORTING)
        if self.request.godot_executable is not None:
            import_result = await run_godot_import_check(
                godot_executable=self.request.godot_executable,
                project_root=project_root,
                logs_dir=record.manifest_path.parent / "logs",
            )
            if not import_result.success:
                raise ConfigError(import_result.safe_details)
        else:
            await context.emit(
                "stage.warning",
                "Godot executable was not configured; import check was skipped",
                stage="run_godot_import_check",
            )

        await self._stage(context, 10, "Generating sample Godot scene")
        self._write_sample_scene(record)

        await self._stage(context, 11, "Finalizing generated asset")
        context.store.save_generated_asset(context.job_id, project_root, record)
        await context.emit(
            "asset.generated",
            "Generated asset is ready",
            stage="finalize_asset_record",
            progress=0.99,
            payload={
                "asset_id": record.asset_id,
                "res_path": record.godot_resource_path,
                "manifest_path": str(record.manifest_path),
            },
        )
        return record

    async def _stage(
        self,
        context: JobContext,
        index: int,
        message: str,
        state: JobState = JobState.RUNNING,
    ) -> None:
        context.check_cancelled()
        progress = index / len(self.stages)
        context.set_state(state, progress=progress)
        await context.emit(
            "stage.started", message, stage=self.stages[index], progress=progress
        )

    async def _poll_until_complete(
        self, context: JobContext, task_id: str, stage: str
    ) -> AssetTaskResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.request.poll_timeout_seconds
        while loop.time() < deadline:
            context.check_cancelled()
            result = await self._retry(
                context, stage, lambda: self.provider.poll_task(task_id)
            )
            if result.status == AssetTaskStatus.SUCCEEDED:
                return result
            if result.status in {AssetTaskStatus.FAILED, AssetTaskStatus.CANCELLED}:
                raise ProviderError(f"Provider task ended with status {result.status.value}.")
            await asyncio.sleep(self.request.poll_interval_seconds)
        raise ProviderError("Provider polling timed out.")

    async def _retry(self, context: JobContext, stage: str, operation):
        for attempt in range(self.request.max_retries + 1):
            context.check_cancelled()
            try:
                return await operation()
            except ProviderError:
                if attempt >= self.request.max_retries:
                    raise
                context.set_state(JobState.RETRYING)
                await context.emit(
                    "stage.retrying",
                    f"Retrying provider operation (attempt {attempt + 2})",
                    stage=stage,
                    payload={"attempt": attempt + 2},
                )
                await asyncio.sleep(min(2**attempt, 5))
        raise AssertionError("unreachable")

    async def _download(
        self, url: str, project_root: Path, destination: Path
    ) -> DownloadedAsset:
        if url.startswith("mock://"):
            destination.mkdir(parents=True, exist_ok=True)
            path = destination / "download.glb"
            data = _minimal_glb()
            path.write_bytes(data)
            return DownloadedAsset(
                source_url=url,
                path=path,
                sha256=hashlib.sha256(data).hexdigest(),
                content_type="model/gltf-binary",
                size_bytes=len(data),
            )
        return await self.downloader(
            url,
            project_root=project_root,
            destination_dir=destination,
            filename="asset.glb",
        )

    def _write_sample_scene(self, record: GeneratedAssetRecord) -> None:
        godot_dir = record.manifest_path.parent / "godot"
        godot_dir.mkdir(parents=True, exist_ok=True)
        scene = godot_dir / "preview_scene.tscn"
        scene.write_text(
            "[gd_scene load_steps=2 format=3]\n\n"
            f'[ext_resource type="PackedScene" path="{record.godot_resource_path}" id="1"]\n\n'
            '[node name="GeneratedAssetPreview" type="Node3D"]\n'
            '[node name="Asset" parent="." instance=ExtResource("1")]\n',
            encoding="utf-8",
        )


def _minimal_glb() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (20).to_bytes(4, "little") + b"\0" * 8
