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
        return AssetTaskRef(
            provider_id=self.config.provider_id,
            task_id=task_id,
            status=AssetTaskStatus.SUBMITTED,
            raw=_json_object(response),
        )

    async def poll_task(self, task_id: str) -> AssetTaskResult:
        api_key = self.key_resolver.resolve_required(self.config)
        response = await self._request(
            "GET",
            f"/openapi/v2/text-to-3d/{task_id}",
            api_key=api_key,
        )
        status = _map_meshy_status(str(response.get("status", "unknown")))
        asset_urls = _extract_asset_urls(response)
        return AssetTaskResult(
            provider_id=self.config.provider_id,
            task_id=task_id,
            status=status,
            asset_urls=asset_urls,
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
        client = self._client or httpx.AsyncClient(timeout=30)
        close_client = self._client is None
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
        finally:
            if close_client:
                await client.aclose()


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

    async def poll_task(self, task_id: str) -> AssetTaskResult:
        await asyncio.sleep(0)
        return AssetTaskResult(
            provider_id=self.config.provider_id,
            task_id=task_id,
            status=AssetTaskStatus.SUCCEEDED,
            asset_urls=[f"mock://meshy/{task_id}.glb"],
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


def _json_object(value: dict[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}
