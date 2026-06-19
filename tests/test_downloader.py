from __future__ import annotations

import httpx
import pytest

from bridle.domain.errors import ProviderError
from bridle.godot.downloader import download_asset


async def test_downloader_rejects_unexpected_content_type(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"not a model",
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="content type"):
            await download_asset(
                "https://example.test/asset.glb",
                project_root=tmp_path,
                destination_dir=tmp_path / "generated",
                filename="asset.glb",
                client=client,
            )

    assert not (tmp_path / "generated" / "asset.glb").exists()
