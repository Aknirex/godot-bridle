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
    (tmp_path / "project.godot").write_text(
        'config/name="Demo"\nconfig/features=PackedStringArray("4.3", "GL Compatibility")\n',
        encoding="utf-8",
    )
    (tmp_path / "player.gd").write_text("extends Node\n", encoding="utf-8")
    (tmp_path / "main.tscn").write_text("[gd_scene]\n", encoding="utf-8")
    (tmp_path / "thing.tres").write_text("[gd_resource]\n", encoding="utf-8")

    summary = detect_project(tmp_path)

    assert summary.project_name == "Demo"
    assert summary.godot_version == "4.3"
    assert summary.gdscript_files_count == 1
    assert summary.scene_files_count == 1
    assert summary.resource_files_count == 1


def test_detect_project_lists_installed_and_enabled_addons(tmp_path) -> None:
    (tmp_path / "project.godot").write_text(
        '[application]\nconfig/features=PackedStringArray("4.4")\n'
        '[editor_plugins]\nenabled=PackedStringArray("res://addons/active/plugin.cfg")\n',
        encoding="utf-8",
    )
    active = tmp_path / "addons" / "active"
    inactive = tmp_path / "addons" / "inactive"
    active.mkdir(parents=True)
    inactive.mkdir(parents=True)
    (active / "plugin.cfg").write_text('[plugin]\nname="Active Plugin"\n', encoding="utf-8")
    (inactive / "plugin.cfg").write_text('[plugin]\nname="Inactive Plugin"\n', encoding="utf-8")

    summary = detect_project(tmp_path)

    assert summary.installed_addons_count == 2
    assert summary.enabled_addons_count == 1
    assert [(addon.name, addon.enabled) for addon in summary.addons] == [
        ("Active Plugin", True),
        ("Inactive Plugin", False),
    ]


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
