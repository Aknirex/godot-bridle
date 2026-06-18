from __future__ import annotations

from pathlib import Path

from bridle.domain.assets import GlbInspectionReport

GLB_MAGIC = b"glTF"


def inspect_glb(path: Path) -> GlbInspectionReport:
    warnings: list[str] = []
    errors: list[str] = []
    size = path.stat().st_size
    with path.open("rb") as file:
        header = file.read(12)

    is_glb = header.startswith(GLB_MAGIC)
    if not is_glb:
        errors.append("File does not start with GLB magic header.")
    if size < 20:
        errors.append("File is too small to be a useful GLB asset.")
    if path.suffix.lower() != ".glb":
        warnings.append("File extension is not .glb.")

    version = int.from_bytes(header[4:8], "little") if len(header) >= 8 and is_glb else None
    declared_length = (
        int.from_bytes(header[8:12], "little") if len(header) >= 12 and is_glb else None
    )
    if declared_length is not None and declared_length != size:
        warnings.append("GLB declared length does not match file size.")

    metadata = {}
    if version is not None:
        metadata["version"] = version
    if declared_length is not None:
        metadata["declared_length"] = declared_length

    return GlbInspectionReport(
        path=path,
        is_glb=is_glb,
        size_bytes=size,
        warnings=warnings,
        errors=errors,
        metadata=metadata,
    )
