from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

from bridle.domain.assets import GlbInspectionReport

GLB_MAGIC = b"glTF"
GLB_HEADER = struct.Struct("<4sII")
GLB_CHUNK_HEADER = struct.Struct("<II")
JSON_CHUNK_TYPE = 0x4E4F534A
BIN_CHUNK_TYPE = 0x004E4942


def inspect_glb(path: Path) -> GlbInspectionReport:
    warnings: list[str] = []
    errors: list[str] = []
    size = path.stat().st_size
    if path.suffix.lower() != ".glb":
        warnings.append("File extension is not .glb.")
    raw = path.read_bytes()
    if len(raw) < GLB_HEADER.size or not raw.startswith(GLB_MAGIC):
        return GlbInspectionReport(
            path=path,
            is_glb=False,
            size_bytes=size,
            errors=["File does not start with a complete GLB header."],
        )
    _, header_version, header_length = GLB_HEADER.unpack_from(raw)
    if header_length != size:
        warnings.append("GLB declared length does not match file size.")
    try:
        document, chunks, version, declared_length = read_glb(path)
    except ValueError as error:
        warnings.append(str(error))
        return GlbInspectionReport(
            path=path,
            is_glb=True,
            size_bytes=size,
            warnings=warnings,
            metadata={
                "version": header_version,
                "declared_length": header_length,
                "structure_valid": False,
            },
        )

    if declared_length != size:
        warnings.append("GLB declared length does not match file size.")
    if version != 2:
        errors.append(f"Unsupported GLB version {version}; Godot expects glTF 2.0.")

    meshes = document.get("meshes") or []
    accessors = document.get("accessors") or []
    materials = document.get("materials") or []
    textures = document.get("textures") or []
    images = document.get("images") or []
    skins = document.get("skins") or []
    animations = document.get("animations") or []
    primitive_count = 0
    missing_normals = 0
    missing_uvs = 0
    missing_tangents = 0
    morph_target_count = 0
    bounds: list[tuple[list[float], list[float]]] = []
    attribute_counts: dict[str, int] = {}

    for mesh in meshes:
        if not isinstance(mesh, dict):
            continue
        for primitive in mesh.get("primitives") or []:
            if not isinstance(primitive, dict):
                continue
            primitive_count += 1
            attributes = primitive.get("attributes") or {}
            for name in attributes:
                attribute_counts[name] = attribute_counts.get(name, 0) + 1
            if "POSITION" in attributes:
                if "NORMAL" not in attributes:
                    missing_normals += 1
                if "TEXCOORD_0" not in attributes:
                    missing_uvs += 1
                if "TANGENT" not in attributes:
                    missing_tangents += 1
                accessor_index = attributes.get("POSITION")
                if isinstance(accessor_index, int) and 0 <= accessor_index < len(accessors):
                    accessor = accessors[accessor_index]
                    if isinstance(accessor, dict):
                        minimum = accessor.get("min")
                        maximum = accessor.get("max")
                        if _vec3(minimum) and _vec3(maximum):
                            bounds.append((minimum, maximum))
            morph_target_count += len(primitive.get("targets") or [])

    if missing_normals:
        warnings.append(f"{missing_normals} mesh primitives are missing NORMAL attributes.")
    if missing_uvs:
        warnings.append(f"{missing_uvs} mesh primitives are missing TEXCOORD_0 attributes.")
    if missing_tangents:
        warnings.append(f"{missing_tangents} mesh primitives are missing TANGENT attributes.")

    combined_bounds = _combined_bounds(bounds)
    max_extent = None
    if combined_bounds is not None:
        minimum, maximum = combined_bounds
        max_extent = max(maximum[index] - minimum[index] for index in range(3))
        if max_extent > 100.0:
            warnings.append("Asset bounds exceed 100 units; scale normalization is recommended.")
        elif 0 < max_extent < 0.01:
            warnings.append(
                "Asset bounds are below 0.01 units; scale normalization is recommended."
            )

    material_reports = [
        _material_report(index, material, textures, images)
        for index, material in enumerate(materials)
        if isinstance(material, dict)
    ]
    metadata: dict[str, Any] = {
        "version": version,
        "structure_valid": True,
        "declared_length": declared_length,
        "chunk_count": len(chunks),
        "mesh_count": len(meshes),
        "primitive_count": primitive_count,
        "accessor_count": len(accessors),
        "material_count": len(materials),
        "texture_count": len(textures),
        "image_count": len(images),
        "skin_count": len(skins),
        "animation_count": len(animations),
        "morph_target_count": morph_target_count,
        "missing_normal_primitives": missing_normals,
        "missing_uv_primitives": missing_uvs,
        "missing_tangent_primitives": missing_tangents,
        "unit_assumption": "meters (glTF 2.0 convention)",
        "attributes": attribute_counts,
        "materials": material_reports,
    }
    if combined_bounds is not None:
        metadata["bounds_min"] = combined_bounds[0]
        metadata["bounds_max"] = combined_bounds[1]
        metadata["max_extent"] = max_extent

    return GlbInspectionReport(
        path=path,
        is_glb=True,
        size_bytes=size,
        warnings=warnings,
        errors=errors,
        metadata=metadata,
    )


def read_glb(path: Path) -> tuple[dict[str, Any], list[tuple[int, bytes]], int, int]:
    data = path.read_bytes()
    if len(data) < GLB_HEADER.size:
        raise ValueError("File is too small to contain a GLB header.")
    magic, version, declared_length = GLB_HEADER.unpack_from(data)
    if magic != GLB_MAGIC:
        raise ValueError("File does not start with GLB magic header.")
    if declared_length > len(data):
        raise ValueError("GLB declared length exceeds the available file data.")
    chunks: list[tuple[int, bytes]] = []
    offset = GLB_HEADER.size
    while offset + GLB_CHUNK_HEADER.size <= min(declared_length, len(data)):
        chunk_length, chunk_type = GLB_CHUNK_HEADER.unpack_from(data, offset)
        offset += GLB_CHUNK_HEADER.size
        end = offset + chunk_length
        if end > len(data):
            raise ValueError("GLB chunk exceeds the available file data.")
        chunks.append((chunk_type, data[offset:end]))
        offset = end
    json_chunk = next((payload for kind, payload in chunks if kind == JSON_CHUNK_TYPE), None)
    if json_chunk is None:
        raise ValueError("GLB does not contain a JSON chunk.")
    try:
        document = json.loads(json_chunk.rstrip(b" \t\r\n\0").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("GLB JSON chunk is invalid.") from error
    if not isinstance(document, dict):
        raise ValueError("GLB JSON root is not an object.")
    return document, chunks, version, declared_length


def write_glb(
    path: Path,
    document: dict[str, Any],
    chunks: list[tuple[int, bytes]],
    *,
    version: int = 2,
) -> None:
    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    output_chunks: list[tuple[int, bytes]] = [(JSON_CHUNK_TYPE, encoded)]
    output_chunks.extend((kind, payload) for kind, payload in chunks if kind != JSON_CHUNK_TYPE)
    total_length = GLB_HEADER.size + sum(
        GLB_CHUNK_HEADER.size + len(payload) for _, payload in output_chunks
    )
    with path.open("wb") as file:
        file.write(GLB_HEADER.pack(GLB_MAGIC, version, total_length))
        for chunk_type, payload in output_chunks:
            file.write(GLB_CHUNK_HEADER.pack(len(payload), chunk_type))
            file.write(payload)


def _material_report(
    index: int,
    material: dict[str, Any],
    textures: list[Any],
    images: list[Any],
) -> dict[str, Any]:
    pbr = material.get("pbrMetallicRoughness") or {}
    slots = {
        "base_color": pbr.get("baseColorTexture"),
        "metallic_roughness": pbr.get("metallicRoughnessTexture"),
        "normal": material.get("normalTexture"),
        "occlusion": material.get("occlusionTexture"),
        "emission": material.get("emissiveTexture"),
    }
    return {
        "index": index,
        "name": str(material.get("name") or f"Material_{index}"),
        "alpha_mode": str(material.get("alphaMode") or "OPAQUE"),
        "double_sided": bool(material.get("doubleSided", False)),
        "textures": {
            name: _texture_source(slot, textures, images)
            for name, slot in slots.items()
            if isinstance(slot, dict)
        },
    }


def _texture_source(slot: dict[str, Any], textures: list[Any], images: list[Any]) -> Any:
    texture_index = slot.get("index")
    if not isinstance(texture_index, int) or not 0 <= texture_index < len(textures):
        return None
    texture = textures[texture_index]
    if not isinstance(texture, dict):
        return None
    source = texture.get("source")
    if not isinstance(source, int) or not 0 <= source < len(images):
        return None
    image = images[source]
    if not isinstance(image, dict):
        return None
    return {
        "image_index": source,
        "uri": image.get("uri"),
        "mime_type": image.get("mimeType"),
        "buffer_view": image.get("bufferView"),
    }


def _vec3(value: Any) -> bool:
    return isinstance(value, list) and len(value) >= 3 and all(
        isinstance(item, int | float) for item in value[:3]
    )


def _combined_bounds(
    bounds: list[tuple[list[float], list[float]]],
) -> tuple[list[float], list[float]] | None:
    if not bounds:
        return None
    minimum = [min(pair[0][axis] for pair in bounds) for axis in range(3)]
    maximum = [max(pair[1][axis] for pair in bounds) for axis in range(3)]
    return minimum, maximum
