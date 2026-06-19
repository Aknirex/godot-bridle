from __future__ import annotations

import os

import pytest

from bridle.config.key_resolver import KeyResolver
from bridle.domain.providers import (
    AssetGenerationRequest,
    ProviderConfig,
    ProviderKind,
)
from bridle.providers.asset_meshy import MeshyProvider


@pytest.mark.external_api
@pytest.mark.skipif("MESHY_API_KEY" not in os.environ, reason="Meshy BYOK is not set")
async def test_meshy_real_submit_preview() -> None:
    provider = MeshyProvider(
        ProviderConfig(
            provider_id="meshy",
            kind=ProviderKind.ASSET,
            backend="meshy",
            api_key_env="MESHY_API_KEY",
        ),
        KeyResolver(),
    )
    try:
        task = await provider.submit_text_to_3d(
            AssetGenerationRequest(prompt="a simple low-poly gray cube")
        )
        assert task.task_id
    finally:
        await provider.close()
