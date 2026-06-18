from __future__ import annotations

from pathlib import Path

from bridle.domain.errors import ConfigError
from bridle.domain.projects import ProjectSummary


def detect_project(root_path: Path) -> ProjectSummary:
    root = root_path.resolve()
    project_file = root / "project.godot"
    if not project_file.is_file():
        raise ConfigError(f"Godot project file project.godot not found under {root}")

    warnings: list[str] = []
    project_name = _read_project_name(project_file)
    if project_name is None:
        warnings.append("Project name was not found in project.godot.")

    return ProjectSummary(
        root_path=root,
        godot_project_file=project_file,
        project_name=project_name,
        gdscript_files_count=_count_files(root, "*.gd"),
        scene_files_count=_count_files(root, "*.tscn"),
        resource_files_count=_count_files(root, "*.tres") + _count_files(root, "*.res"),
        warnings=warnings,
    )


def ensure_inside_project(root_path: Path, target_path: Path) -> Path:
    root = root_path.resolve()
    target = target_path.resolve()
    if target != root and root not in target.parents:
        raise ConfigError(f"Path escapes Godot project root: {target}")
    return target


def res_path_for(root_path: Path, target_path: Path) -> str:
    target = ensure_inside_project(root_path, target_path)
    relative = target.relative_to(root_path.resolve()).as_posix()
    return f"res://{relative}"


def generated_asset_dir(root_path: Path, asset_id: str) -> Path:
    safe_asset_id = sanitize_path_component(asset_id)
    return root_path.resolve() / "bridle" / "generated" / safe_asset_id


def sanitize_path_component(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    sanitized = sanitized.strip("._")
    if not sanitized:
        raise ConfigError("Path component became empty after sanitization.")
    return sanitized[:96]


def _read_project_name(project_file: Path) -> str | None:
    for line in project_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("config/name="):
            return stripped.split("=", 1)[1].strip().strip('"')
    return None


def _count_files(root: Path, pattern: str) -> int:
    return sum(1 for path in root.rglob(pattern) if path.is_file())
