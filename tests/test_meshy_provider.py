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
