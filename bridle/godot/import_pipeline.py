from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from bridle.domain.assets import DownloadedAsset, GeneratedAssetRecord, GlbInspectionReport
from bridle.godot.glb_normalize import generate_material_artifacts, normalize_glb
from bridle.godot.project import generated_asset_dir, res_path_for


def prepare_godot_asset_files(
    *,
    project_root: Path,
    asset_id: str,
    provider_id: str,
    downloaded: DownloadedAsset,
    inspection: GlbInspectionReport,
) -> GeneratedAssetRecord:
    asset_dir = generated_asset_dir(project_root, asset_id)
    source_dir = asset_dir / "source"
    godot_dir = asset_dir / "godot"
    logs_dir = asset_dir / "logs"
    source_dir.mkdir(parents=True, exist_ok=True)
    godot_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    source_path = source_dir / "asset.glb"
    if downloaded.path.resolve() != source_path.resolve():
        shutil.copy2(downloaded.path, source_path)

    normalized_path = godot_dir / "asset.normalized.glb"
    repairs = normalize_glb(source_path, normalized_path, inspection)
    materials = generate_material_artifacts(normalized_path, project_root, godot_dir)
    manifest_path = asset_dir / "bridle_asset.json"
    record = GeneratedAssetRecord(
        asset_id=asset_id,
        provider_id=provider_id,
        source_url=_safe_source_reference(downloaded.source_url),
        source_path=source_path,
        godot_resource_path=res_path_for(project_root, normalized_path),
        manifest_path=manifest_path,
        sha256=downloaded.sha256,
        inspection=inspection.model_copy(update={"path": source_path}),
        normalized_path=normalized_path,
        repairs=repairs,
        materials=materials,
        provenance={"source_sha256": downloaded.sha256, "provider_id": provider_id},
    )
    write_asset_manifest(record)
    return record


def write_asset_manifest(record: GeneratedAssetRecord) -> None:
    record.manifest_path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_source_reference(source_url: str) -> str:
    if source_url.startswith("mock://"):
        return source_url
    parsed = urlsplit(source_url)
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        # Provider download URLs are frequently signed. Persist provenance, not
        # replayable credentials or signature-bearing paths/query strings.
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{parsed.hostname}{port}/<redacted>"
    return "<redacted>"
