from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from bridle.domain.events import JsonValue


class DownloadedAsset(BaseModel):
    source_url: str
    path: Path
    sha256: str
    content_type: str | None = None
    size_bytes: int


class GlbInspectionReport(BaseModel):
    path: Path
    is_glb: bool
    size_bytes: int
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class GodotImportResult(BaseModel):
    success: bool
    exit_code: int
    stdout_path: Path
    stderr_path: Path
    safe_details: str = ""


class GeneratedAssetRecord(BaseModel):
    asset_id: str
    provider_id: str
    source_url: str | None = None
    source_path: Path
    godot_resource_path: str
    manifest_path: Path
    sha256: str
    inspection: GlbInspectionReport
