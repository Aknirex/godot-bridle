from __future__ import annotations

import httpx
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


async def test_mock_meshy_supports_image_retexture_and_rig() -> None:
    provider = MockMeshyProvider(
        ProviderConfig(provider_id="meshy", kind=ProviderKind.ASSET)
    )

    image = await provider.submit_image_to_3d(
        AssetGenerationRequest(image_url="https://assets.test/hero.png")
    )
    texture = await provider.submit_retexture(
        AssetGenerationRequest(source_task_id=image.task_id)
    )
    rig = await provider.submit_auto_rig(
        AssetGenerationRequest(source_task_id=texture.task_id)
    )

    assert image.task_type == "image_to_3d"
    assert texture.task_type == "retexture"
    assert rig.task_type == "auto_rig"
    assert (await provider.poll_task(rig)).status == AssetTaskStatus.SUCCEEDED


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


async def test_meshy_http_contract_covers_all_asset_capabilities() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "status": "SUCCEEDED",
                    "progress": 100,
                    "model_urls": {"glb": "https://cdn.test/model.glb"},
                },
            )
        if request.method == "DELETE":
            return httpx.Response(200, json={"result": "cancelled"})
        return httpx.Response(200, json={"result": f"task-{len(requests)}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MeshyProvider(
            ProviderConfig(
                provider_id="meshy",
                kind=ProviderKind.ASSET,
                base_url="https://api.meshy.test",
                api_key_env="MESHY_API_KEY",
            ),
            key_resolver=KeyResolver({"MESHY_API_KEY": "protected-test-key"}),
            client=client,
        )
        preview = await provider.submit_text_to_3d(
            AssetGenerationRequest(prompt="knight")
        )
        refine = await provider.submit_refine(preview.task_id)
        image = await provider.submit_image_to_3d(
            AssetGenerationRequest(image_url="https://image.test/reference.png")
        )
        retexture = await provider.submit_retexture(
            AssetGenerationRequest(source_task_id=image.task_id)
        )
        rig = await provider.submit_auto_rig(
            AssetGenerationRequest(source_task_id=retexture.task_id)
        )
        result = await provider.poll_task(rig)
        await provider.cancel_task(rig)

    assert preview.poll_path == "/openapi/v2/text-to-3d/task-1"
    assert refine.task_type == "text_to_3d_refine"
    assert image.poll_path == "/openapi/v1/image-to-3d/task-3"
    assert retexture.poll_path == "/openapi/v1/retexture/task-4"
    assert rig.poll_path == "/openapi/v1/rigging/task-5"
    assert result.asset_urls == ["https://cdn.test/model.glb"]
    assert requests[-1].method == "DELETE"
    assert requests[-1].headers["authorization"] == "Bearer protected-test-key"
