from __future__ import annotations

import hashlib
import re
from pathlib import Path
from uuid import uuid4

from bridle.domain.errors import ConfigError
from bridle.godot.project import detect_project
from bridle.knowledge.documents import KnowledgeDocument, KnowledgeSourceType

INDEXABLE_SUFFIXES = frozenset({".gd", ".tscn", ".tres", ".md", ".json"})
EXCLUDED_DIRECTORIES = frozenset({".git", ".godot", ".import", "node_modules", "target"})
DEFAULT_MAX_FILE_BYTES = 1_000_000
PROJECT_IDENTITY_PATH = Path("bridle") / ".project_id"
PROJECT_ID_PATTERN = re.compile(r"project_[0-9a-f]{32}")


def scan_godot_project(
    project_root: Path, *, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
) -> tuple[list[KnowledgeDocument], list[str]]:
    root = detect_project(project_root).root_path
    project_id = _project_identity(root)
    documents: list[KnowledgeDocument] = []
    warnings: list[str] = []
    candidates = [root / "project.godot"]
    candidates.extend(
        path
        for path in root.rglob("*")
        if path.suffix.lower() in INDEXABLE_SUFFIXES and path.name != "project.godot"
    )
    for path in sorted(candidates):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if path.is_symlink():
            warnings.append(f"Skipped symbolic link: {relative.as_posix()}")
            continue
        try:
            size = path.stat().st_size
        except OSError:
            warnings.append(f"Could not inspect file: {relative.as_posix()}")
            continue
        if size > max_file_bytes:
            warnings.append(f"Skipped oversized file: {relative.as_posix()}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            warnings.append(f"Could not read UTF-8 file: {relative.as_posix()}")
            continue
        res_path = f"res://{relative.as_posix()}"
        documents.append(
            KnowledgeDocument(
                source_id=_source_id(project_id, relative),
                source_type=KnowledgeSourceType.GODOT_PROJECT,
                project_root=root,
                path=path,
                title=relative.name,
                content=content,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                metadata={
                    "project_id": project_id,
                    "res_path": res_path,
                    "suffix": path.suffix.lower(),
                },
            )
        )
    if not documents:
        raise ConfigError("Godot project did not contain any indexable text files.")
    return documents, warnings


def _source_id(project_id: str, relative: Path) -> str:
    identity = f"{project_id}::{relative.as_posix()}".encode()
    return f"source_{hashlib.sha256(identity).hexdigest()}"


def _project_identity(root: Path) -> str:
    identity_path = root / PROJECT_IDENTITY_PATH
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    if root not in identity_path.parent.resolve().parents:
        raise ConfigError("Bridle project identity path escapes the Godot project root.")
    if not identity_path.exists():
        project_id = f"project_{uuid4().hex}"
        try:
            with identity_path.open("x", encoding="ascii") as identity_file:
                identity_file.write(project_id + "\n")
        except FileExistsError:
            pass
    try:
        project_id = identity_path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError) as error:
        raise ConfigError("Could not read Bridle project identity.") from error
    if PROJECT_ID_PATTERN.fullmatch(project_id) is None:
        raise ConfigError("Bridle project identity is invalid.")
    return project_id
