from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError, ProviderError
from bridle.domain.providers import (
    AssetGenerationRequest,
    AssetTaskRef,
    AssetTaskResult,
    AssetTaskStatus,
    ProviderConfig,
    ProviderHealth,
    ProviderHealthStatus,
)

DEFAULT_MESHY_BASE_URL = "https://api.meshy.ai"


class MeshyProvider:
    def __init__(
        self,
        config: ProviderConfig,
        key_resolver: KeyResolver | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.key_resolver = key_resolver or KeyResolver()
        self._client = client
        self._owned_client: httpx.AsyncClient | None = None
        self._task_paths: dict[str, tuple[str, str]] = {}

    async def __aenter__(self) -> MeshyProvider:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def test_connection(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            self.key_resolver.resolve_required(self.config)
        except AuthError as error:
            return ProviderHealth(
                provider_id=self.config.provider_id,
                status=ProviderHealthStatus.MISSING_KEY,
                safe_details=error.safe_details,
            )
        return ProviderHealth(
            provider_id=self.config.provider_id,
            status=ProviderHealthStatus.OK,
            latency_ms=int((time.perf_counter() - start) * 1000),
            safe_details=f"Key source: {self.key_resolver.describe_source(self.config)}",
        )

    async def submit_text_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef:
        api_key = self.key_resolver.resolve_required(self.config)
        payload = {
            "mode": "preview",
            "prompt": request.prompt,
            "art_style": request.provider_options.get("art_style", "realistic"),
        }
        response = await self._request(
            "POST",
            "/openapi/v2/text-to-3d",
            api_key=api_key,
            json=payload,
        )
        task_id = str(response.get("result") or response.get("id") or response.get("task_id") or "")
        if not task_id:
            raise ProviderError("Meshy response did not include a task id.")
        poll_path = f"/openapi/v2/text-to-3d/{task_id}"
        self._task_paths[task_id] = ("text_to_3d", poll_path)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=task_id,
            status=AssetTaskStatus.SUBMITTED,
            task_type="text_to_3d",
            poll_path=poll_path,
            raw=_json_object(response),
        )

    async def submit_image_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef:
        if not request.image_url:
            raise ProviderError("Meshy Image-to-3D requires image_url.")
        payload: dict[str, Any] = {"image_url": request.image_url}
        payload.update(_allowed_options(request.provider_options))
        return await self._submit_task(
            "/openapi/v1/image-to-3d",
            payload,
            task_type="image_to_3d",
        )

    async def submit_retexture(self, request: AssetGenerationRequest) -> AssetTaskRef:
        if not request.source_task_id and not request.model_url:
            raise ProviderError("Meshy Retexture requires source_task_id or model_url.")
        payload: dict[str, Any] = {}
        if request.source_task_id:
            payload["input_task_id"] = request.source_task_id
        if request.model_url:
            payload["model_url"] = request.model_url
        payload.update(_allowed_options(request.provider_options))
        return await self._submit_task(
            "/openapi/v1/retexture",
            payload,
            task_type="retexture",
        )

    async def submit_auto_rig(self, request: AssetGenerationRequest) -> AssetTaskRef:
        if not request.source_task_id and not request.model_url:
            raise ProviderError("Meshy Auto-Rig requires source_task_id or model_url.")
        payload: dict[str, Any] = {}
        if request.source_task_id:
            payload["input_task_id"] = request.source_task_id
        if request.model_url:
            payload["model_url"] = request.model_url
        payload.update(_allowed_options(request.provider_options))
        return await self._submit_task(
            "/openapi/v1/rigging",
            payload,
            task_type="auto_rig",
        )

    async def poll_task(self, task: AssetTaskRef | str) -> AssetTaskResult:
        task_id = task.task_id if isinstance(task, AssetTaskRef) else task
        if isinstance(task, AssetTaskRef) and task.poll_path:
            task_type = task.task_type
            poll_path = task.poll_path
        else:
            task_type, poll_path = self._task_paths.get(
                task_id,
                ("text_to_3d", f"/openapi/v2/text-to-3d/{task_id}"),
            )
        api_key = self.key_resolver.resolve_required(self.config)
        response = await self._request(
            "GET",
            poll_path,
            api_key=api_key,
        )
        status = _map_meshy_status(str(response.get("status", "unknown")))
        asset_urls = _extract_asset_urls(response)
        return AssetTaskResult(
            provider_id=self.config.provider_id,
            task_id=task_id,
            status=status,
            task_type=task_type,
            progress=_progress(response),
            asset_urls=asset_urls,
            texture_urls=_extract_texture_urls(response),
            raw=_json_object(response),
        )

    async def cancel_task(self, task: AssetTaskRef | str) -> None:
        task_id = task.task_id if isinstance(task, AssetTaskRef) else task
        if isinstance(task, AssetTaskRef) and task.poll_path:
            poll_path = task.poll_path
        else:
            _, poll_path = self._task_paths.get(
                task_id,
                ("text_to_3d", f"/openapi/v2/text-to-3d/{task_id}"),
            )
        api_key = self.key_resolver.resolve_required(self.config)
        await self._request("DELETE", poll_path, api_key=api_key)

    async def submit_refine(
        self,
        preview_task_id: str,
        request: AssetGenerationRequest | None = None,
    ) -> AssetTaskRef:
        api_key = self.key_resolver.resolve_required(self.config)
        payload: dict[str, Any] = {"mode": "refine", "preview_task_id": preview_task_id}
        if request is not None:
            payload.update(_allowed_options(request.provider_options))
        response = await self._request(
            "POST",
            "/openapi/v2/text-to-3d",
            api_key=api_key,
            json=payload,
        )
        task_id = str(response.get("result") or response.get("id") or "")
        if not task_id:
            raise ProviderError("Meshy refine response did not include a task id.")
        poll_path = f"/openapi/v2/text-to-3d/{task_id}"
        self._task_paths[task_id] = ("text_to_3d_refine", poll_path)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=task_id,
            task_type="text_to_3d_refine",
            poll_path=poll_path,
        )

    async def _submit_task(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        task_type: str,
    ) -> AssetTaskRef:
        api_key = self.key_resolver.resolve_required(self.config)
        response = await self._request("POST", path, api_key=api_key, json=payload)
        task_id = str(response.get("result") or response.get("id") or "")
        if not task_id:
            raise ProviderError(f"Meshy {task_type} response did not include a task id.")
        poll_path = f"{path}/{task_id}"
        self._task_paths[task_id] = (task_type, poll_path)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=task_id,
            task_type=task_type,
            poll_path=poll_path,
            raw=_json_object(response),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        api_key: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_url = self.config.base_url or DEFAULT_MESHY_BASE_URL
        client = self._ensure_client()
        try:
            response = await client.request(
                method,
                f"{base_url.rstrip('/')}{path}",
                headers={"Authorization": f"Bearer {api_key}"},
                json=json,
            )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ProviderError("Meshy response was not a JSON object.")
            return data
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status in {401, 403}:
                raise AuthError("Meshy authentication failed.") from error
            raise ProviderError(f"Meshy request failed with HTTP {status}.") from error
        except httpx.HTTPError as error:
            raise ProviderError("Meshy request failed.") from error

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._owned_client is None:
            self._owned_client = httpx.AsyncClient(timeout=30)
        return self._owned_client


class MockMeshyProvider:
    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    async def test_connection(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.config.provider_id,
            status=ProviderHealthStatus.OK,
            safe_details="Mock Meshy provider is available.",
        )

    async def submit_text_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef:
        await asyncio.sleep(0)
        task_id = f"mock_meshy_{abs(hash(request.prompt))}"
        return AssetTaskRef(provider_id=self.config.provider_id, task_id=task_id)

    async def submit_image_to_3d(self, request: AssetGenerationRequest) -> AssetTaskRef:
        if not request.image_url:
            raise ProviderError("Mock Image-to-3D requires image_url.")
        await asyncio.sleep(0)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=f"mock_image_{abs(hash(request.image_url))}",
            task_type="image_to_3d",
        )

    async def submit_retexture(self, request: AssetGenerationRequest) -> AssetTaskRef:
        await asyncio.sleep(0)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=f"mock_retexture_{abs(hash(request.source_task_id or request.model_url))}",
            task_type="retexture",
        )

    async def submit_auto_rig(self, request: AssetGenerationRequest) -> AssetTaskRef:
        await asyncio.sleep(0)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=f"mock_rig_{abs(hash(request.source_task_id or request.model_url))}",
            task_type="auto_rig",
        )

    async def poll_task(self, task: AssetTaskRef | str) -> AssetTaskResult:
        await asyncio.sleep(0)
        task_id = task.task_id if isinstance(task, AssetTaskRef) else task
        task_type = task.task_type if isinstance(task, AssetTaskRef) else "text_to_3d"
        return AssetTaskResult(
            provider_id=self.config.provider_id,
            task_id=task_id,
            status=AssetTaskStatus.SUCCEEDED,
            task_type=task_type,
            progress=1.0,
            asset_urls=[f"mock://meshy/{task_id}.glb"],
        )

    async def cancel_task(self, task: AssetTaskRef | str) -> None:
        await asyncio.sleep(0)

    async def submit_refine(
        self,
        preview_task_id: str,
        request: AssetGenerationRequest | None = None,
    ) -> AssetTaskRef:
        await asyncio.sleep(0)
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=f"{preview_task_id}_refined",
            task_type="text_to_3d_refine",
        )


def _map_meshy_status(status: str) -> AssetTaskStatus:
    normalized = status.lower()
    if normalized in {"pending", "in_progress", "processing", "running"}:
        return AssetTaskStatus.RUNNING
    if normalized in {"succeeded", "success", "completed"}:
        return AssetTaskStatus.SUCCEEDED
    if normalized in {"failed", "error"}:
        return AssetTaskStatus.FAILED
    if normalized in {"cancelled", "canceled"}:
        return AssetTaskStatus.CANCELLED
    return AssetTaskStatus.UNKNOWN


def _extract_asset_urls(response: dict[str, Any]) -> list[str]:
    model_urls = response.get("model_urls")
    if isinstance(model_urls, dict):
        return [str(value) for value in model_urls.values() if isinstance(value, str)]
    result = response.get("result")
    if isinstance(result, dict):
        return _extract_asset_urls(result)
    if isinstance(response.get("asset_url"), str):
        return [str(response["asset_url"])]
    return []


def _extract_texture_urls(response: dict[str, Any]) -> dict[str, str]:
    value = response.get("texture_urls")
    if isinstance(value, dict):
        return {str(key): str(url) for key, url in value.items() if isinstance(url, str)}
    result = response.get("result")
    return _extract_texture_urls(result) if isinstance(result, dict) else {}


def _progress(response: dict[str, Any]) -> float | None:
    value = response.get("progress")
    if not isinstance(value, int | float):
        return None
    return max(0.0, min(1.0, float(value) / 100.0))


def _allowed_options(options: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "ai_model",
        "topology",
        "target_polycount",
        "decimation_mode",
        "should_texture",
        "enable_pbr",
        "hd_texture",
        "texture_prompt",
        "texture_image_url",
        "text_style_prompt",
        "image_style_url",
        "enable_original_uv",
        "remove_lighting",
        "is_a_t_pose",
        "rig_preset",
    }
    return {key: value for key, value in options.items() if key in allowed}


def _json_object(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}
