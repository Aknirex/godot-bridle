from __future__ import annotations

import json
import shutil
from pathlib import Path

from bridle.domain.assets import DownloadedAsset, GeneratedAssetRecord, GlbInspectionReport
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

    manifest_path = asset_dir / "bridle_asset.json"
    record = GeneratedAssetRecord(
        asset_id=asset_id,
        provider_id=provider_id,
        source_url=downloaded.source_url,
        source_path=source_path,
        godot_resource_path=res_path_for(project_root, source_path),
        manifest_path=manifest_path,
        sha256=downloaded.sha256,
        inspection=inspection.model_copy(update={"path": source_path}),
    )
    manifest_path.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record
