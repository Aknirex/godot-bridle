from __future__ import annotations

import pytest

from bridle.config.key_resolver import KeyResolver
from bridle.domain.errors import AuthError
from bridle.domain.providers import (
    AssetGenerationRequest,
    AssetTaskStatus,
    ProviderConfig,
    ProviderKind,
)
from bridle.providers.asset_meshy import MeshyProvider, MockMeshyProvider


class RecordingAsyncClient:
    def __init__(self) -> None:
        self.close_count = 0

    async def aclose(self) -> None:
        self.close_count += 1


async def test_mock_meshy_provider_completes_text_to_3d_flow() -> None:
    provider = MockMeshyProvider(
        ProviderConfig(provider_id="meshy", kind=ProviderKind.ASSET)
    )

    task = await provider.submit_text_to_3d(AssetGenerationRequest(prompt="low poly knight"))
    result = await provider.poll_task(task.task_id)

    assert task.provider_id == "meshy"
    assert result.status == AssetTaskStatus.SUCCEEDED
    assert result.asset_urls == [f"mock://meshy/{task.task_id}.glb"]


async def test_meshy_provider_requires_key_before_submit() -> None:
    provider = MeshyProvider(
        ProviderConfig(
            provider_id="meshy",
            kind=ProviderKind.ASSET,
            api_key_env="MESHY_API_KEY",
        ),
        key_resolver=KeyResolver({}),
    )

    with pytest.raises(AuthError):
        await provider.submit_text_to_3d(AssetGenerationRequest(prompt="low poly knight"))


async def test_meshy_provider_maps_key_health_without_network() -> None:
    provider = MeshyProvider(
        ProviderConfig(
            provider_id="meshy",
            kind=ProviderKind.ASSET,
            api_key_env="MESHY_API_KEY",
        ),
        key_resolver=KeyResolver({}),
    )

    health = await provider.test_connection()

    assert health.status == "missing_key"


async def test_meshy_provider_reuses_owned_client_until_closed() -> None:
    provider = MeshyProvider(
        ProviderConfig(provider_id="meshy", kind=ProviderKind.ASSET),
    )

    first = provider._ensure_client()
    second = provider._ensure_client()

    assert first is second
    await provider.close()
    assert provider._owned_client is None


async def test_meshy_provider_does_not_close_injected_client() -> None:
    client = RecordingAsyncClient()
    provider = MeshyProvider(
        ProviderConfig(provider_id="meshy", kind=ProviderKind.ASSET),
        client=client,  # type: ignore[arg-type]
    )

    assert provider._ensure_client() is client
    await provider.close()
    assert client.close_count == 0
