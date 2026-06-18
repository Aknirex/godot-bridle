from __future__ import annotations

import pytest

from bridle.domain.errors import ConfigError
from bridle.godot.project import (
    detect_project,
    ensure_inside_project,
    generated_asset_dir,
    res_path_for,
    sanitize_path_component,
)


def test_detect_project_reads_name_and_counts_files(tmp_path) -> None:
    (tmp_path / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (tmp_path / "thing.tres").write_text("[gd_resource]\n", encoding="utf-8")

    summary = detect_project(tmp_path)

    assert summary.project_name == "Demo"
    assert summary.gdscript_files_count == 1
    assert summary.scene_files_count == 1
    assert summary.resource_files_count == 1


def test_detect_project_requires_project_file(tmp_path) -> None:
    with pytest.raises(ConfigError, match="project.godot"):
        detect_project(tmp_path)


def test_project_path_helpers_prevent_escape(tmp_path) -> None:
    inside = tmp_path / "bridle" / "generated" / "asset" / "source.glb"

    assert res_path_for(tmp_path, inside) == "res://bridle/generated/asset/source.glb"
    with pytest.raises(ConfigError, match="escapes"):
        ensure_inside_project(tmp_path, tmp_path.parent / "outside.glb")


def test_generated_asset_dir_sanitizes_asset_id(tmp_path) -> None:
    path = generated_asset_dir(tmp_path, "../knight hero!")

    assert path == tmp_path.resolve() / "bridle" / "generated" / "knight_hero"


def test_sanitize_path_component_rejects_empty_values() -> None:
    with pytest.raises(ConfigError):
        sanitize_path_component("...")
