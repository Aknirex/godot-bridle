from __future__ import annotations

import hashlib
import json

from bridle.domain.assets import DownloadedAsset
from bridle.godot.glb import inspect_glb
from bridle.godot.import_pipeline import prepare_godot_asset_files


def glb_bytes() -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + (20).to_bytes(4, "little") + b"\0" * 8


def test_prepare_godot_asset_files_writes_manifest_inside_project(tmp_path) -> None:
    (tmp_path / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    source = tmp_path / "download.glb"
    data = glb_bytes()
    source.write_bytes(data)
    downloaded = DownloadedAsset(
        source_url="mock://meshy/task.glb",
        path=source,
        sha256=hashlib.sha256(data).hexdigest(),
        content_type="model/gltf-binary",
        size_bytes=len(data),
    )

    record = prepare_godot_asset_files(
        project_root=tmp_path,
        asset_id="asset_knight",
        provider_id="meshy_mock",
        downloaded=downloaded,
        inspection=inspect_glb(source),
    )

    manifest = json.loads(record.manifest_path.read_text(encoding="utf-8"))
    assert record.godot_resource_path == (
        "res://bridle/generated/asset_knight/godot/asset.normalized.glb"
    )
    assert record.normalized_path is not None
    assert record.normalized_path.is_file()
    assert record.source_path.is_file()
    assert manifest["asset_id"] == "asset_knight"
    assert manifest["sha256"] == downloaded.sha256


def test_manifest_redacts_signed_download_url(tmp_path) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    source = tmp_path / "signed.glb"
    data = glb_bytes()
    source.write_bytes(data)
    secret = "super-secret-signature"
    downloaded = DownloadedAsset(
        source_url=f"https://cdn.example/private/model.glb?signature={secret}",
        path=source,
        sha256=hashlib.sha256(data).hexdigest(),
        content_type="model/gltf-binary",
        size_bytes=len(data),
    )

    record = prepare_godot_asset_files(
        project_root=tmp_path,
        asset_id="asset_signed",
        provider_id="meshy",
        downloaded=downloaded,
        inspection=inspect_glb(source),
    )
    manifest_text = record.manifest_path.read_text(encoding="utf-8")

    assert secret not in manifest_text
    assert "private/model.glb" not in manifest_text
    assert record.source_url == "https://cdn.example/<redacted>"
