from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class GodotAddon(BaseModel):
    addon_id: str
    name: str
    plugin_file: Path
    enabled: bool = False


class ProjectSummary(BaseModel):
    root_path: Path
    godot_project_file: Path
    project_name: str | None = None
    godot_version: str | None = None
    addons: list[GodotAddon] = Field(default_factory=list)
    installed_addons_count: int = 0
    enabled_addons_count: int = 0
    gdscript_files_count: int = 0
    scene_files_count: int = 0
    resource_files_count: int = 0
    generated_assets_dir: str = "res://bridle/generated"
    warnings: list[str] = Field(default_factory=list)
