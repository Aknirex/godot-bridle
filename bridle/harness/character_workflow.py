from __future__ import annotations

import asyncio
import hashlib
import json
import struct
from collections.abc import Awaitable, Callable
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from bridle.domain.assets import DownloadedAsset, GeneratedAssetRecord, GodotImportResult
from bridle.domain.capabilities import ProviderCapability
from bridle.domain.errors import ConfigError, JobCancelledError, ProviderError
from bridle.domain.jobs import JobState
from bridle.domain.providers import (
    AssetGenerationRequest,
    AssetTaskRef,
    AssetTaskResult,
    AssetTaskStatus,
    LlmChatRequest,
)
from bridle.godot.cli import run_godot_import_check
from bridle.godot.downloader import download_asset
from bridle.godot.glb import inspect_glb
from bridle.godot.import_pipeline import prepare_godot_asset_files, write_asset_manifest
from bridle.godot.project import detect_project, generated_asset_dir, res_path_for
from bridle.harness.task_orchestrator import JobContext
from bridle.knowledge.documents import KnowledgeAnswer
from bridle.providers.base import AssetProvider, LLMProvider


class CharacterInputType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    RETEXTURE = "retexture"
    AUTO_RIG = "auto_rig"


class CharacterGenerationRequest(BaseModel):
    project_path: Path
    prompt: str = Field(min_length=1)
    input_type: CharacterInputType = CharacterInputType.TEXT
    image_url: str | None = None
    source_task_id: str | None = None
    model_url: str | None = None
    provider_id: str = "meshy_mock"
    required_capabilities: list[ProviderCapability] = Field(default_factory=list)
    godot_executable: Path | None = None
    poll_interval_seconds: float = Field(default=1.0, ge=0)
    poll_timeout_seconds: float = Field(default=300.0, gt=0)
    max_retries: int = Field(default=2, ge=0, le=5)
    enhance_prompt: bool = False
    enable_pbr: bool = True
    texture_prompt: str | None = None
    texture_image_url: str | None = None
    auto_rig: bool = False
    diagnosis_timeout_seconds: float = Field(default=10.0, gt=0, le=60)


DownloadFunction = Callable[..., Awaitable[DownloadedAsset]]
ImportDiagnoser = Callable[[Path, GodotImportResult], Awaitable[KnowledgeAnswer]]


class CharacterGenerationWorkflow:
    stages = (
        "validate_project",
        "resolve_providers",
        "submit_generation",
        "poll_generation",
        "submit_texture",
        "poll_texture",
        "submit_auto_rig",
        "poll_auto_rig",
        "download_assets",
        "inspect_glb",
        "prepare_godot_files",
        "generate_sample_scene_or_script",
        "run_godot_import_check",
        "finalize_asset_record",
    )

    def __init__(
        self,
        request: CharacterGenerationRequest,
        provider: AssetProvider,
        *,
        llm_provider: LLMProvider | None = None,
        downloader: DownloadFunction = download_asset,
        import_diagnoser: ImportDiagnoser | None = None,
    ) -> None:
        self.request = request
        self.provider = provider
        self.llm_provider = llm_provider
        self.downloader = downloader
        self.import_diagnoser = import_diagnoser
        self.asset_id = f"asset_{uuid4().hex}"

    async def run(self, context: JobContext) -> GeneratedAssetRecord:
        project_root = self.request.project_path.resolve()
        await self._stage(context, 0, "Validating Godot project")
        detect_project(project_root)

        await self._stage(context, 1, "Resolving asset provider")
        if self.request.provider_id != self.provider.config.provider_id:
            raise ConfigError("Resolved provider does not match the workflow request.")
        self._validate_capabilities()
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

        generation_request = AssetGenerationRequest(
            prompt=prompt,
            image_url=self.request.image_url,
            source_task_id=self.request.source_task_id,
            model_url=self.request.model_url,
            provider_options=self._provider_options(),
        )
        await self._stage(context, 2, "Submitting character generation")
        if self.request.input_type == CharacterInputType.IMAGE:
            generation = await self._retry(
                context,
                "submit_generation",
                lambda: self.provider.submit_image_to_3d(generation_request),
            )
        elif self.request.input_type == CharacterInputType.RETEXTURE:
            generation = await self._retry(
                context,
                "submit_generation",
                lambda: self.provider.submit_retexture(generation_request),
            )
        elif self.request.input_type == CharacterInputType.AUTO_RIG:
            generation = await self._retry(
                context,
                "submit_generation",
                lambda: self.provider.submit_auto_rig(generation_request),
            )
        else:
            generation = await self._retry(
                context,
                "submit_generation",
                lambda: self.provider.submit_text_to_3d(generation_request),
            )

        await self._stage(
            context, 3, "Waiting for character generation", JobState.WAITING_PROVIDER
        )
        generated = await self._poll_until_complete(
            context, generation, "poll_generation"
        )

        if self.request.input_type == CharacterInputType.TEXT:
            await self._stage(context, 4, "Submitting texture refinement")
            textured_ref = await self._retry(
                context,
                "submit_texture",
                lambda: self.provider.submit_refine(
                    generation.task_id,
                    generation_request,
                ),
            )
            await self._stage(
                context, 5, "Waiting for texture refinement", JobState.WAITING_PROVIDER
            )
            result = await self._poll_until_complete(
                context, textured_ref, "poll_texture"
            )
        else:
            await self._skip_stage(context, 4, "Image generation already includes texturing")
            await self._skip_stage(context, 5, "No separate texture task was required")
            result = generated

        if self.request.auto_rig and self.request.input_type != CharacterInputType.AUTO_RIG:
            await self._stage(context, 6, "Submitting auto-rig task")
            rig_ref = await self._retry(
                context,
                "submit_auto_rig",
                lambda: self.provider.submit_auto_rig(
                    AssetGenerationRequest(source_task_id=result.task_id)
                ),
            )
            await self._stage(
                context, 7, "Waiting for auto-rig", JobState.WAITING_PROVIDER
            )
            rigged = await self._poll_until_complete(context, rig_ref, "poll_auto_rig")
            if rigged.asset_urls:
                result = rigged
        else:
            await self._skip_stage(context, 6, "Auto-rig was not requested")
            await self._skip_stage(context, 7, "No rig task was required")
        if not result.asset_urls:
            raise ProviderError("Provider completed without a downloadable GLB URL.")

        await self._stage(context, 8, "Downloading generated GLB", JobState.DOWNLOADING)
        destination = generated_asset_dir(project_root, self.asset_id) / "source"
        downloaded = await self._download(result.asset_urls[0], project_root, destination)

        await self._stage(context, 9, "Inspecting generated GLB")
        inspection = inspect_glb(downloaded.path)
        if not inspection.is_glb or inspection.errors:
            raise ProviderError("Generated asset is not a valid GLB file.")

        await self._stage(context, 10, "Preparing Godot asset files")
        record = prepare_godot_asset_files(
            project_root=project_root,
            asset_id=self.asset_id,
            provider_id=self.request.provider_id,
            downloaded=downloaded,
            inspection=inspection,
        )

        await self._stage(context, 11, "Generating sample Godot scene and validator")
        self._write_sample_scene(record)
        validation_script = self._write_validation_script(record)

        await self._stage(context, 12, "Running Godot import check", JobState.IMPORTING)
        if self.request.godot_executable is not None:
            import_result = await run_godot_import_check(
                godot_executable=self.request.godot_executable,
                project_root=project_root,
                logs_dir=record.manifest_path.parent / "logs",
                extra_args=["--script", str(validation_script)],
            )
            if not import_result.success:
                await self._diagnose_import_failure(context, project_root, import_result)
                raise ConfigError(import_result.safe_details)
            record = record.model_copy(update={"godot_validation": import_result})
        else:
            await context.emit(
                "stage.warning",
                "Godot executable was not configured; import check was skipped",
                stage="run_godot_import_check",
            )

        await self._stage(context, 13, "Finalizing generated asset")
        record = record.model_copy(
            update={
                "rigging": {
                    "requested": (
                        self.request.auto_rig
                        or self.request.input_type == CharacterInputType.AUTO_RIG
                    ),
                    "task_type": result.task_type,
                },
                "provenance": {
                    **record.provenance,
                    "provider_task_id": result.task_id,
                    "input_type": self.request.input_type.value,
                    "texture_slots": sorted(result.texture_urls),
                },
            }
        )
        write_asset_manifest(record)
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

    async def _diagnose_import_failure(
        self,
        context: JobContext,
        project_root: Path,
        import_result: GodotImportResult,
    ) -> None:
        if self.import_diagnoser is None:
            return
        try:
            diagnosis = await asyncio.wait_for(
                self.import_diagnoser(project_root, import_result),
                timeout=self.request.diagnosis_timeout_seconds,
            )
        except Exception:
            await context.emit(
                "knowledge.diagnosis.failed",
                "Knowledge diagnosis was unavailable; the original import error is unchanged",
                stage="run_godot_import_check",
                payload={"exit_code": import_result.exit_code},
            )
            return

        await context.emit(
            "knowledge.diagnosis.completed",
            "Knowledge diagnosis completed for the Godot import failure",
            stage="run_godot_import_check",
            payload={
                "exit_code": import_result.exit_code,
                "suggestion": diagnosis.answer,
                "citations": [
                    citation.model_dump(mode="json") for citation in diagnosis.citations
                ],
                "latency_ms": diagnosis.latency_ms,
                "warnings": diagnosis.warnings,
            },
        )

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
        self, context: JobContext, task: AssetTaskRef, stage: str
    ) -> AssetTaskResult:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.request.poll_timeout_seconds
        while loop.time() < deadline:
            try:
                context.check_cancelled()
            except JobCancelledError:
                try:
                    await self.provider.cancel_task(task)
                except ProviderError:
                    await context.emit(
                        "provider.cancel.failed",
                        "Provider task cancellation could not be confirmed",
                        stage=stage,
                    )
                raise
            result = await self._retry(
                context, stage, lambda: self.provider.poll_task(task)
            )
            if result.status == AssetTaskStatus.SUCCEEDED:
                return result
            if result.status in {AssetTaskStatus.FAILED, AssetTaskStatus.CANCELLED}:
                raise ProviderError(f"Provider task ended with status {result.status.value}.")
            await asyncio.sleep(self.request.poll_interval_seconds)
        raise ProviderError("Provider polling timed out.")

    async def _skip_stage(self, context: JobContext, index: int, message: str) -> None:
        progress = index / len(self.stages)
        context.set_state(JobState.RUNNING, progress=progress)
        await context.emit(
            "stage.started",
            message,
            stage=self.stages[index],
            progress=progress,
        )
        await context.emit(
            "stage.skipped",
            message,
            stage=self.stages[index],
            progress=progress,
        )

    def _provider_options(self) -> dict:
        options: dict = {"enable_pbr": self.request.enable_pbr}
        if self.request.texture_prompt:
            options["texture_prompt"] = self.request.texture_prompt
        if self.request.texture_image_url:
            options["texture_image_url"] = self.request.texture_image_url
        return options

    def _validate_capabilities(self) -> None:
        required_by_input = {
            CharacterInputType.TEXT: ProviderCapability.MODEL3D_TEXT_TO_3D,
            CharacterInputType.IMAGE: ProviderCapability.MODEL3D_IMAGE_TO_3D,
            CharacterInputType.RETEXTURE: ProviderCapability.TEXTURE_RETEXTURE,
            CharacterInputType.AUTO_RIG: ProviderCapability.RIGGING_AUTO_RIG,
        }
        required = required_by_input[self.request.input_type]
        if required not in self.provider.config.capabilities:
            raise ConfigError(
                f"Provider {self.provider.config.provider_id!r} does not support "
                f"{required.value}."
            )
        missing_explicit = [
            capability
            for capability in self.request.required_capabilities
            if capability not in self.provider.config.capabilities
        ]
        if missing_explicit:
            names = ", ".join(capability.value for capability in missing_explicit)
            raise ConfigError(
                f"Provider {self.provider.config.provider_id!r} is missing requested "
                f"capabilities: {names}."
            )
        if self.request.input_type in {
            CharacterInputType.RETEXTURE,
            CharacterInputType.AUTO_RIG,
        } and not (self.request.source_task_id or self.request.model_url):
            raise ConfigError(
                f"{self.request.input_type.value} requires source_task_id or model_url."
            )
        if (
            self.request.auto_rig
            and ProviderCapability.RIGGING_AUTO_RIG
            not in self.provider.config.capabilities
        ):
            raise ConfigError(
                f"Provider {self.provider.config.provider_id!r} does not support auto-rig."
            )

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

    def _write_validation_script(self, record: GeneratedAssetRecord) -> Path:
        godot_dir = record.manifest_path.parent / "godot"
        script = godot_dir / "validate_import.gd"
        preview_path = record.godot_resource_path.rsplit("/", 1)[0] + "/preview_scene.tscn"
        material_paths = [
            res_path_for(self.request.project_path.resolve(), artifact.tres_path)
            for artifact in record.materials
            if artifact.tres_path is not None
        ]
        expects_skeleton = int(record.inspection.metadata.get("skin_count") or 0) > 0
        expects_animation = int(record.inspection.metadata.get("animation_count") or 0) > 0
        script.write_text(
            "extends SceneTree\n\n"
            "func _initialize() -> void:\n"
            f"\tvar asset = load({json.dumps(record.godot_resource_path)})\n"
            "\tif asset == null:\n\t\tpush_error(\"Generated GLB failed to load\")\n"
            "\t\tquit(2)\n\t\treturn\n"
            f"\tvar preview = load({json.dumps(preview_path)})\n"
            "\tif preview == null:\n\t\tpush_error(\"Preview scene failed to load\")\n"
            "\t\tquit(3)\n\t\treturn\n"
            f"\tfor material_path in {json.dumps(material_paths)}:\n"
            "\t\tif load(material_path) == null:\n"
            "\t\t\tpush_error(\"Generated material failed to load: \" + material_path)\n"
            "\t\t\tquit(4)\n\t\t\treturn\n"
            "\tvar instance = asset.instantiate() if asset is PackedScene else null\n"
            "\tif instance != null:\n\t\troot.add_child(instance)\n"
            f"\tif {str(expects_skeleton).lower()} and not "
            "_contains_class(instance, \"Skeleton3D\"):\n"
            "\t\tpush_error(\"Expected skeleton was not imported\")\n\t\tquit(5)\n\t\treturn\n"
            f"\tif {str(expects_animation).lower()} and not "
            "_contains_class(instance, \"AnimationPlayer\"):\n"
            "\t\tpush_error(\"Expected animation was not imported\")\n\t\tquit(6)\n\t\treturn\n"
            "\tquit(0)\n\n"
            "func _contains_class(node: Node, expected_class: String) -> bool:\n"
            "\tif node == null:\n\t\treturn false\n"
            "\tif node.is_class(expected_class):\n\t\treturn true\n"
            "\tfor child in node.get_children():\n"
            "\t\tif _contains_class(child, expected_class):\n\t\t\treturn true\n"
            "\treturn false\n",
            encoding="utf-8",
        )
        return script


def _minimal_glb() -> bytes:
    document = json.dumps(
        {"asset": {"version": "2.0"}, "scenes": [{"nodes": []}], "scene": 0},
        separators=(",", ":"),
    ).encode("utf-8")
    document += b" " * ((4 - len(document) % 4) % 4)
    total = 12 + 8 + len(document)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(document), 0x4E4F534A)
        + document
    )
