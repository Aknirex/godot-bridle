from __future__ import annotations

import hashlib
from pathlib import Path

import httpx

from bridle.domain.assets import DownloadedAsset
from bridle.domain.errors import ProviderError
from bridle.godot.project import ensure_inside_project, sanitize_path_component


async def download_asset(
    url: str,
    *,
    project_root: Path,
    destination_dir: Path,
    filename: str,
    max_bytes: int = 250 * 1024 * 1024,
    client: httpx.AsyncClient | None = None,
    allowed_content_types: tuple[str, ...] = (
        "model/gltf-binary",
        "application/octet-stream",
        "application/gltf-buffer",
    ),
) -> DownloadedAsset:
    ensure_inside_project(project_root, destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_path_component(Path(filename).stem) + Path(filename).suffix.lower()
    destination = ensure_inside_project(project_root, destination_dir / safe_name)
    part_path = destination.with_suffix(destination.suffix + ".part")

    hasher = hashlib.sha256()
    bytes_written = 0
    own_client = client is None
    active_client = client or httpx.AsyncClient(timeout=60)
    content_type: str | None = None
    try:
        async with active_client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            normalized_content_type = (content_type or "").split(";", 1)[0].strip().lower()
            if normalized_content_type and normalized_content_type not in allowed_content_types:
                raise ProviderError("Downloaded asset has an unsupported content type.")
            content_length = response.headers.get("content-length")
            if content_length is not None and int(content_length) > max_bytes:
                raise ProviderError("Downloaded asset exceeds maximum allowed size.")

            with part_path.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    bytes_written += len(chunk)
                    if bytes_written > max_bytes:
                        raise ProviderError("Downloaded asset exceeds maximum allowed size.")
                    hasher.update(chunk)
                    file.write(chunk)
        part_path.replace(destination)
    except httpx.HTTPError as error:
        raise ProviderError("Asset download failed.") from error
    finally:
        if part_path.exists():
            part_path.unlink()
        if own_client:
            await active_client.aclose()

    return DownloadedAsset(
        source_url=url,
        path=destination,
        sha256=hasher.hexdigest(),
        content_type=content_type,
        size_bytes=bytes_written,
    )
