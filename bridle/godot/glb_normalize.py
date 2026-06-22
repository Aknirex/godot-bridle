from __future__ import annotations

import base64
import copy
import math
import shutil
import struct
from pathlib import Path
from urllib.parse import unquote_to_bytes

from bridle.domain.assets import AssetRepairAction, GlbInspectionReport, MaterialArtifact
from bridle.godot.glb import BIN_CHUNK_TYPE, read_glb, write_glb
from bridle.godot.project import res_path_for


def normalize_glb(
    source: Path,
    output: Path,
    inspection: GlbInspectionReport,
    *,
    target_extent_m: float = 2.0,
) -> list[AssetRepairAction]:
    if target_extent_m <= 0:
        raise ValueError("target_extent_m must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        document, chunks, version, _ = read_glb(source)
    except ValueError as error:
        shutil.copy2(source, output)
        return [
            AssetRepairAction(
                action="normalize_structure",
                applied=False,
                safe_details=f"Normalization skipped: {error}",
                output_path=output,
            )
        ]
    actions: list[AssetRepairAction] = []
    max_extent = inspection.metadata.get("max_extent")
    should_scale = isinstance(max_extent, int | float) and (
        float(max_extent) > 100.0 or 0 < float(max_extent) < 0.01
    )
    if should_scale:
        scale = target_extent_m / float(max_extent)
        normalized = copy.deepcopy(document)
        roots = _scene_roots(normalized)
        nodes = normalized.get("nodes") or []
        for node_index in roots:
            if not 0 <= node_index < len(nodes) or not isinstance(nodes[node_index], dict):
                continue
            existing = nodes[node_index].get("scale") or [1.0, 1.0, 1.0]
            if len(existing) >= 3:
                nodes[node_index]["scale"] = [float(value) * scale for value in existing[:3]]
        write_glb(output, normalized, chunks, version=version)
        actions.append(
            AssetRepairAction(
                action="normalize_root_scale",
                applied=True,
                safe_details=(
                    f"Applied root scale {scale:.8g}; geometry, skins and animation data "
                    "were not rewritten."
                ),
                output_path=output,
            )
        )
    else:
        shutil.copy2(source, output)
        actions.append(
            AssetRepairAction(
                action="normalize_root_scale",
                applied=False,
                safe_details="Bounds did not require safe root-scale normalization.",
                output_path=output,
            )
        )

    missing_normals = int(inspection.metadata.get("missing_normal_primitives") or 0)
    missing_uvs = int(inspection.metadata.get("missing_uv_primitives") or 0)
    constrained = any(
        int(inspection.metadata.get(name) or 0) > 0
        for name in ("skin_count", "animation_count", "morph_target_count")
    )
    if missing_normals:
        if constrained:
            actions.append(
                AssetRepairAction(
                    action="recalculate_normals",
                    applied=False,
                    safe_details=(
                        "Automatic vertex data rewrite was refused because the asset contains "
                        "skins, animations, or morph targets."
                    ),
                )
            )
        else:
            repaired, details = _recalculate_missing_normals(output)
            actions.append(
                AssetRepairAction(
                    action="recalculate_normals",
                    applied=repaired > 0,
                    safe_details=details,
                    output_path=output if repaired else None,
                )
            )
    if constrained:
        actions.append(
            AssetRepairAction(
                action="recalculate_reversed_normals",
                applied=False,
                safe_details=(
                    "Reversed-normal repair was refused for a rigged, animated, or morph asset."
                ),
            )
        )
    else:
        repaired, details = _recalculate_reversed_normals(output)
        actions.append(
            AssetRepairAction(
                action="recalculate_reversed_normals",
                applied=repaired > 0,
                safe_details=details,
                output_path=output if repaired else None,
            )
        )
    if missing_uvs:
        if constrained:
            actions.append(
                AssetRepairAction(
                    action="generate_uv_xatlas",
                    applied=False,
                    safe_details=(
                        "UV topology rewrite was refused for a rigged, animated, or morph asset."
                    ),
                )
            )
        else:
            repaired, details = _generate_missing_uvs_xatlas(output)
            actions.append(
                AssetRepairAction(
                    action="generate_uv_xatlas",
                    applied=repaired > 0,
                    safe_details=details,
                    output_path=output if repaired else None,
                )
            )
    return actions


def _recalculate_missing_normals(path: Path) -> tuple[int, str]:
    """Append float VEC3 normal accessors without changing positions or topology."""
    try:
        document, chunks, version, _ = read_glb(path)
    except ValueError as error:
        return 0, f"Normal generation skipped: {error}"
    binary_index = next(
        (index for index, (kind, _) in enumerate(chunks) if kind == BIN_CHUNK_TYPE),
        None,
    )
    if binary_index is None:
        return 0, "Normal generation skipped: GLB has no binary geometry chunk."
    binary = bytearray(chunks[binary_index][1])
    accessors = document.setdefault("accessors", [])
    views = document.setdefault("bufferViews", [])
    repaired = 0
    skipped: list[str] = []
    for mesh_index, mesh in enumerate(document.get("meshes") or []):
        if not isinstance(mesh, dict):
            continue
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            if not isinstance(primitive, dict):
                continue
            attributes = primitive.get("attributes") or {}
            if "POSITION" not in attributes or "NORMAL" in attributes:
                continue
            label = f"mesh {mesh_index} primitive {primitive_index}"
            if int(primitive.get("mode", 4)) != 4:
                skipped.append(f"{label} is not TRIANGLES")
                continue
            try:
                positions = _read_vec3_accessor(
                    document, bytes(binary), int(attributes["POSITION"])
                )
                index_accessor = primitive.get("indices")
                indices = (
                    _read_index_accessor(document, bytes(binary), int(index_accessor))
                    if isinstance(index_accessor, int)
                    else list(range(len(positions)))
                )
                normals = _vertex_normals(positions, indices)
            except (
                IndexError,
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
                struct.error,
            ) as error:
                skipped.append(f"{label}: {error}")
                continue
            while len(binary) % 4:
                binary.append(0)
            byte_offset = len(binary)
            payload = b"".join(struct.pack("<3f", *normal) for normal in normals)
            binary.extend(payload)
            views.append(
                {
                    "buffer": 0,
                    "byteOffset": byte_offset,
                    "byteLength": len(payload),
                    "target": 34962,
                }
            )
            accessors.append(
                {
                    "bufferView": len(views) - 1,
                    "componentType": 5126,
                    "count": len(normals),
                    "type": "VEC3",
                }
            )
            attributes["NORMAL"] = len(accessors) - 1
            primitive["attributes"] = attributes
            repaired += 1
    if repaired:
        buffers = document.setdefault("buffers", [{}])
        if not buffers:
            buffers.append({})
        buffers[0]["byteLength"] = len(binary)
        chunks[binary_index] = (BIN_CHUNK_TYPE, bytes(binary))
        write_glb(path, document, chunks, version=version)
    details = f"Generated area-weighted vertex normals for {repaired} static primitives."
    if skipped:
        details += " Skipped: " + "; ".join(skipped)
    return repaired, details


def _read_vec3_accessor(document: dict, binary: bytes, index: int) -> list[list[float]]:
    accessor, view, offset, stride = _accessor_layout(document, index, 12)
    if int(accessor.get("componentType", 0)) != 5126 or accessor.get("type") != "VEC3":
        raise ValueError("POSITION accessor must be float VEC3")
    return [
        list(struct.unpack_from("<3f", binary, offset + row * stride))
        for row in range(int(accessor["count"]))
    ]


def _read_index_accessor(document: dict, binary: bytes, index: int) -> list[int]:
    accessors = document.get("accessors") or []
    accessor = accessors[index]
    formats = {5121: ("<B", 1), 5123: ("<H", 2), 5125: ("<I", 4)}
    component_type = int(accessor.get("componentType", 0))
    if component_type not in formats or accessor.get("type") != "SCALAR":
        raise ValueError("indices accessor must be unsigned SCALAR")
    format_string, width = formats[component_type]
    accessor, _, offset, stride = _accessor_layout(document, index, width)
    return [
        int(struct.unpack_from(format_string, binary, offset + row * stride)[0])
        for row in range(int(accessor["count"]))
    ]


def _accessor_layout(
    document: dict, index: int, element_width: int
) -> tuple[dict, dict, int, int]:
    accessors = document.get("accessors") or []
    views = document.get("bufferViews") or []
    if not 0 <= index < len(accessors) or not isinstance(accessors[index], dict):
        raise ValueError("accessor index is invalid")
    accessor = accessors[index]
    view_index = accessor.get("bufferView")
    if not isinstance(view_index, int) or not 0 <= view_index < len(views):
        raise ValueError("sparse or missing bufferView is unsupported")
    view = views[view_index]
    if not isinstance(view, dict) or int(view.get("buffer", 0)) != 0:
        raise ValueError("only the primary GLB buffer is supported")
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    stride = int(view.get("byteStride", element_width))
    return accessor, view, offset, stride


def _vertex_normals(positions: list[list[float]], indices: list[int]) -> list[list[float]]:
    if not positions or len(indices) % 3:
        raise ValueError("triangle index count is invalid")
    normals = [[0.0, 0.0, 0.0] for _ in positions]
    for offset in range(0, len(indices), 3):
        a, b, c = indices[offset : offset + 3]
        if min(a, b, c) < 0 or max(a, b, c) >= len(positions):
            raise ValueError("triangle index is out of bounds")
        ab = [positions[b][axis] - positions[a][axis] for axis in range(3)]
        ac = [positions[c][axis] - positions[a][axis] for axis in range(3)]
        face = [
            ab[1] * ac[2] - ab[2] * ac[1],
            ab[2] * ac[0] - ab[0] * ac[2],
            ab[0] * ac[1] - ab[1] * ac[0],
        ]
        for vertex in (a, b, c):
            for axis in range(3):
                normals[vertex][axis] += face[axis]
    for normal in normals:
        length = math.sqrt(sum(value * value for value in normal))
        if length:
            normal[:] = [value / length for value in normal]
    return normals


def _recalculate_reversed_normals(path: Path) -> tuple[int, str]:
    try:
        document, chunks, version, _ = read_glb(path)
    except ValueError as error:
        return 0, f"Reversed-normal check skipped: {error}"
    binary_index = next(
        (index for index, (kind, _) in enumerate(chunks) if kind == BIN_CHUNK_TYPE),
        None,
    )
    if binary_index is None:
        return 0, "Reversed-normal check skipped: GLB has no binary geometry chunk."
    binary = bytearray(chunks[binary_index][1])
    repaired = 0
    skipped = 0
    for mesh in document.get("meshes") or []:
        if not isinstance(mesh, dict):
            continue
        for primitive in mesh.get("primitives") or []:
            if not isinstance(primitive, dict):
                continue
            attributes = primitive.get("attributes") or {}
            if not isinstance(attributes.get("NORMAL"), int):
                continue
            if int(primitive.get("mode", 4)) != 4 or "TANGENT" in attributes:
                skipped += 1
                continue
            try:
                positions = _read_vec3_accessor(
                    document, bytes(binary), int(attributes["POSITION"])
                )
                existing = _read_vec3_accessor(
                    document, bytes(binary), int(attributes["NORMAL"])
                )
                index_accessor = primitive.get("indices")
                indices = (
                    _read_index_accessor(document, bytes(binary), int(index_accessor))
                    if isinstance(index_accessor, int)
                    else list(range(len(positions)))
                )
                expected = _vertex_normals(positions, indices)
            except (
                IndexError,
                KeyError,
                TypeError,
                ValueError,
                struct.error,
            ):
                skipped += 1
                continue
            comparisons = [
                sum(left[axis] * right[axis] for axis in range(3))
                for left, right in zip(existing, expected, strict=True)
                if any(right)
            ]
            if not comparisons or sum(comparisons) / len(comparisons) >= -0.5:
                continue
            payload = b"".join(struct.pack("<3f", *normal) for normal in expected)
            accessor = {
                "componentType": 5126,
                "count": len(expected),
                "type": "VEC3",
            }
            attributes["NORMAL"] = _append_accessor(
                document, binary, payload, accessor, 34962
            )
            primitive["attributes"] = attributes
            repaired += 1
    if repaired:
        buffers = document.setdefault("buffers", [{}])
        if not buffers:
            buffers.append({})
        buffers[0]["byteLength"] = len(binary)
        chunks[binary_index] = (BIN_CHUNK_TYPE, bytes(binary))
        write_glb(path, document, chunks, version=version)
    details = f"Recalculated {repaired} primitives whose normals opposed triangle winding."
    if skipped:
        details += f" Skipped {skipped} ambiguous or tangent-bearing primitives."
    return repaired, details


def _generate_missing_uvs_xatlas(path: Path) -> tuple[int, str]:
    try:
        import numpy as np
        import xatlas
    except ImportError:
        return 0, "UV generation skipped: the xatlas geometry worker is not installed."
    try:
        document, chunks, version, _ = read_glb(path)
    except ValueError as error:
        return 0, f"UV generation skipped: {error}"
    binary_index = next(
        (index for index, (kind, _) in enumerate(chunks) if kind == BIN_CHUNK_TYPE),
        None,
    )
    if binary_index is None:
        return 0, "UV generation skipped: GLB has no binary geometry chunk."
    binary = bytearray(chunks[binary_index][1])
    repaired = 0
    skipped: list[str] = []
    for mesh_index, mesh in enumerate(document.get("meshes") or []):
        if not isinstance(mesh, dict):
            continue
        for primitive_index, primitive in enumerate(mesh.get("primitives") or []):
            if not isinstance(primitive, dict):
                continue
            attributes = primitive.get("attributes") or {}
            if "POSITION" not in attributes or "TEXCOORD_0" in attributes:
                continue
            label = f"mesh {mesh_index} primitive {primitive_index}"
            unsupported = set(attributes) - {"POSITION", "NORMAL"}
            if unsupported or int(primitive.get("mode", 4)) != 4:
                skipped.append(
                    f"{label} has unsupported attributes/mode: {sorted(unsupported)}"
                )
                continue
            try:
                positions = _read_vec3_accessor(
                    document, bytes(binary), int(attributes["POSITION"])
                )
                normals = (
                    _read_vec3_accessor(document, bytes(binary), int(attributes["NORMAL"]))
                    if isinstance(attributes.get("NORMAL"), int)
                    else None
                )
                index_accessor = primitive.get("indices")
                indices = (
                    _read_index_accessor(document, bytes(binary), int(index_accessor))
                    if isinstance(index_accessor, int)
                    else list(range(len(positions)))
                )
                vertices = np.asarray(positions, dtype=np.float32)
                faces = np.asarray(indices, dtype=np.uint32).reshape((-1, 3))
                vmapping, atlas_indices, uvs = xatlas.parametrize(vertices, faces)
                remapped_positions = vertices[vmapping]
                remapped_normals = (
                    np.asarray(normals, dtype=np.float32)[vmapping]
                    if normals is not None
                    else None
                )
            except (
                IndexError,
                KeyError,
                RuntimeError,
                TypeError,
                ValueError,
                struct.error,
            ) as error:
                skipped.append(f"{label}: {error}")
                continue
            position_accessor = _append_float_accessor(
                document,
                binary,
                remapped_positions,
                accessor_type="VEC3",
                target=34962,
                include_bounds=True,
            )
            uv_accessor = _append_float_accessor(
                document,
                binary,
                np.asarray(uvs, dtype=np.float32),
                accessor_type="VEC2",
                target=34962,
            )
            new_attributes = {"POSITION": position_accessor, "TEXCOORD_0": uv_accessor}
            if remapped_normals is not None:
                new_attributes["NORMAL"] = _append_float_accessor(
                    document,
                    binary,
                    remapped_normals,
                    accessor_type="VEC3",
                    target=34962,
                )
            primitive["attributes"] = new_attributes
            primitive["indices"] = _append_index_accessor(
                document, binary, np.asarray(atlas_indices, dtype=np.uint32).reshape(-1)
            )
            repaired += 1
    if repaired:
        buffers = document.setdefault("buffers", [{}])
        if not buffers:
            buffers.append({})
        buffers[0]["byteLength"] = len(binary)
        chunks[binary_index] = (BIN_CHUNK_TYPE, bytes(binary))
        write_glb(path, document, chunks, version=version)
    details = f"Generated xatlas TEXCOORD_0 data for {repaired} static primitives."
    if skipped:
        details += " Skipped: " + "; ".join(skipped)
    return repaired, details


def _append_float_accessor(
    document: dict,
    binary: bytearray,
    values,
    *,
    accessor_type: str,
    target: int,
    include_bounds: bool = False,
) -> int:
    import numpy as np

    array = np.ascontiguousarray(values, dtype="<f4")
    accessor: dict = {
        "componentType": 5126,
        "count": int(array.shape[0]),
        "type": accessor_type,
    }
    if include_bounds and len(array):
        accessor["min"] = array.min(axis=0).astype(float).tolist()
        accessor["max"] = array.max(axis=0).astype(float).tolist()
    return _append_accessor(document, binary, array.tobytes(), accessor, target)


def _append_index_accessor(document: dict, binary: bytearray, values) -> int:
    import numpy as np

    array = np.ascontiguousarray(values, dtype="<u4")
    accessor = {
        "componentType": 5125,
        "count": int(array.shape[0]),
        "type": "SCALAR",
        "min": [int(array.min())] if len(array) else [0],
        "max": [int(array.max())] if len(array) else [0],
    }
    return _append_accessor(document, binary, array.tobytes(), accessor, 34963)


def _append_accessor(
    document: dict,
    binary: bytearray,
    payload: bytes,
    accessor: dict,
    target: int,
) -> int:
    while len(binary) % 4:
        binary.append(0)
    offset = len(binary)
    binary.extend(payload)
    views = document.setdefault("bufferViews", [])
    views.append(
        {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(payload),
            "target": target,
        }
    )
    accessors = document.setdefault("accessors", [])
    accessor["bufferView"] = len(views) - 1
    accessors.append(accessor)
    return len(accessors) - 1


def generate_material_artifacts(
    glb_path: Path,
    project_root: Path,
    output_dir: Path,
) -> list[MaterialArtifact]:
    try:
        document, chunks, _, _ = read_glb(glb_path)
    except ValueError:
        return []
    materials = document.get("materials") or []
    textures = document.get("textures") or []
    images = document.get("images") or []
    buffer_views = document.get("bufferViews") or []
    binary = next((payload for kind, payload in chunks if kind == BIN_CHUNK_TYPE), b"")
    texture_dir = output_dir / "textures"
    material_dir = output_dir / "materials"
    texture_dir.mkdir(parents=True, exist_ok=True)
    material_dir.mkdir(parents=True, exist_ok=True)
    image_paths: dict[int, Path] = {}
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            continue
        data, extension = _image_bytes(image, glb_path, buffer_views, binary)
        if data is None:
            continue
        path = texture_dir / f"image_{index}{extension}"
        path.write_bytes(data)
        image_paths[index] = path

    artifacts: list[MaterialArtifact] = []
    for index, material in enumerate(materials):
        if not isinstance(material, dict):
            continue
        name = _safe_name(str(material.get("name") or f"Material_{index}"))
        pbr = material.get("pbrMetallicRoughness") or {}
        slots = {
            "albedo_texture": pbr.get("baseColorTexture"),
            "metallic_texture": pbr.get("metallicRoughnessTexture"),
            "roughness_texture": pbr.get("metallicRoughnessTexture"),
            "normal_texture": material.get("normalTexture"),
            "ao_texture": material.get("occlusionTexture"),
            "emission_texture": material.get("emissiveTexture"),
        }
        resolved = {
            slot: path
            for slot, path in (
                (slot, _resolve_texture(value, textures, image_paths))
                for slot, value in slots.items()
            )
            if path is not None
        }
        tres_path = material_dir / f"{index:03d}_{name}.tres"
        _write_standard_material(tres_path, project_root, material, pbr, resolved)
        artifacts.append(
            MaterialArtifact(
                material_index=index,
                name=name,
                tres_path=tres_path,
                texture_paths=resolved,
            )
        )
    return artifacts


def _scene_roots(document: dict) -> list[int]:
    scenes = document.get("scenes") or []
    scene_index = document.get("scene", 0)
    if not isinstance(scene_index, int) or not 0 <= scene_index < len(scenes):
        return []
    scene = scenes[scene_index]
    return list(scene.get("nodes") or []) if isinstance(scene, dict) else []


def _image_bytes(
    image: dict,
    glb_path: Path,
    buffer_views: list,
    binary: bytes,
) -> tuple[bytes | None, str]:
    mime = str(image.get("mimeType") or "")
    extension = ".png" if mime == "image/png" else ".jpg" if mime == "image/jpeg" else ".bin"
    uri = image.get("uri")
    if isinstance(uri, str) and uri.startswith("data:"):
        header, _, encoded = uri.partition(",")
        if ";base64" in header:
            return base64.b64decode(encoded), extension
        return unquote_to_bytes(encoded), extension
    if isinstance(uri, str):
        candidate = (glb_path.parent / uri).resolve()
        if candidate.is_relative_to(glb_path.parent.resolve()) and candidate.is_file():
            return candidate.read_bytes(), candidate.suffix or extension
    view_index = image.get("bufferView")
    if isinstance(view_index, int) and 0 <= view_index < len(buffer_views):
        view = buffer_views[view_index]
        if isinstance(view, dict) and int(view.get("buffer", 0)) == 0:
            offset = int(view.get("byteOffset", 0))
            length = int(view.get("byteLength", 0))
            return binary[offset : offset + length], extension
    return None, extension


def _resolve_texture(value: object, textures: list, image_paths: dict[int, Path]) -> Path | None:
    if not isinstance(value, dict):
        return None
    texture_index = value.get("index")
    if not isinstance(texture_index, int) or not 0 <= texture_index < len(textures):
        return None
    texture = textures[texture_index]
    source = texture.get("source") if isinstance(texture, dict) else None
    return image_paths.get(source) if isinstance(source, int) else None


def _write_standard_material(
    path: Path,
    project_root: Path,
    material: dict,
    pbr: dict,
    textures: dict[str, Path],
) -> None:
    resources = list(textures.items())
    lines = [f"[gd_resource type=\"StandardMaterial3D\" load_steps={len(resources) + 1} format=3]"]
    ids: dict[str, int] = {}
    for resource_id, (slot, texture_path) in enumerate(resources, 1):
        ids[slot] = resource_id
        resource_path = res_path_for(project_root, texture_path)
        lines.append(
            f"\n[ext_resource type=\"Texture2D\" path=\"{resource_path}\" "
            f"id=\"{resource_id}\"]"
        )
    lines.append("\n[resource]")
    base = pbr.get("baseColorFactor") or [1.0, 1.0, 1.0, 1.0]
    lines.append(f"albedo_color = Color({', '.join(str(float(v)) for v in base[:4])})")
    lines.append(f"metallic = {float(pbr.get('metallicFactor', 1.0))}")
    lines.append(f"roughness = {float(pbr.get('roughnessFactor', 1.0))}")
    emissive = material.get("emissiveFactor") or [0.0, 0.0, 0.0]
    if any(float(value) > 0 for value in emissive[:3]):
        lines.append("emission_enabled = true")
        lines.append(
            f"emission = Color({', '.join(str(float(v)) for v in emissive[:3])}, 1)"
        )
    if bool(material.get("doubleSided", False)):
        lines.append("cull_mode = 2")
    for slot, resource_id in ids.items():
        lines.append(f"{slot} = ExtResource(\"{resource_id}\")")
        if slot == "normal_texture":
            lines.append("normal_enabled = true")
        elif slot == "metallic_texture":
            lines.append("metallic_texture_channel = 2")
        elif slot == "roughness_texture":
            lines.append("roughness_texture_channel = 1")
        elif slot == "ao_texture":
            lines.append("ao_enabled = true")
        elif slot == "emission_texture":
            lines.append("emission_enabled = true")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return normalized.strip("_") or "Material"
