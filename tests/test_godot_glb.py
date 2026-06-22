from __future__ import annotations

import base64
import hashlib
import struct

from bridle.godot.glb import BIN_CHUNK_TYPE, inspect_glb, write_glb
from bridle.godot.glb_normalize import generate_material_artifacts, normalize_glb


def make_glb_bytes(total_length: int = 20) -> bytes:
    return b"glTF" + (2).to_bytes(4, "little") + total_length.to_bytes(4, "little") + b"\0" * (
        total_length - 12
    )


def test_inspect_glb_accepts_basic_header(tmp_path) -> None:
    path = tmp_path / "asset.glb"
    path.write_bytes(make_glb_bytes())

    report = inspect_glb(path)

    assert report.is_glb
    assert report.errors == []
    assert report.metadata["version"] == 2


def test_inspect_glb_reports_invalid_magic(tmp_path) -> None:
    path = tmp_path / "asset.glb"
    path.write_bytes(b"nope")

    report = inspect_glb(path)

    assert not report.is_glb
    assert report.errors


def test_inspect_glb_warns_on_declared_length_mismatch(tmp_path) -> None:
    path = tmp_path / "asset.glb"
    path.write_bytes(make_glb_bytes(total_length=24)[:-4])

    report = inspect_glb(path)

    assert "GLB declared length does not match file size." in report.warnings


def test_inspect_glb_reports_geometry_material_and_rig_metadata(tmp_path) -> None:
    path = tmp_path / "structured.glb"
    write_glb(
        path,
        {
            "asset": {"version": "2.0"},
            "accessors": [{"min": [-1, 0, -1], "max": [1, 2, 1]}],
            "meshes": [
                {
                    "primitives": [
                        {
                            "attributes": {"POSITION": 0},
                            "material": 0,
                            "targets": [{"POSITION": 0}],
                        }
                    ]
                }
            ],
            "materials": [{"name": "Hero", "pbrMetallicRoughness": {}}],
            "skins": [{"joints": []}],
            "animations": [{"channels": [], "samplers": []}],
            "scenes": [{"nodes": []}],
            "scene": 0,
        },
        [],
    )

    report = inspect_glb(path)

    assert report.metadata["structure_valid"] is True
    assert report.metadata["mesh_count"] == 1
    assert report.metadata["missing_normal_primitives"] == 1
    assert report.metadata["missing_uv_primitives"] == 1
    assert report.metadata["missing_tangent_primitives"] == 1
    assert report.metadata["unit_assumption"] == "meters (glTF 2.0 convention)"
    assert report.metadata["skin_count"] == 1
    assert report.metadata["animation_count"] == 1
    assert report.metadata["morph_target_count"] == 1


def test_normalize_recalculates_static_missing_normals_without_changing_source(
    tmp_path,
) -> None:
    source = tmp_path / "triangle.glb"
    output = tmp_path / "triangle.normalized.glb"
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + indices + b"\0\0"
    write_glb(
        source,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
                {
                    "buffer": 0,
                    "byteOffset": len(positions),
                    "byteLength": len(indices),
                },
            ],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC3",
                    "min": [0, 0, 0],
                    "max": [1, 1, 0],
                },
                {
                    "bufferView": 1,
                    "componentType": 5123,
                    "count": 3,
                    "type": "SCALAR",
                },
            ],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
            "nodes": [{"mesh": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        },
        [(BIN_CHUNK_TYPE, binary)],
    )
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    inspection = inspect_glb(source)

    repairs = normalize_glb(source, output, inspection)
    normalized = inspect_glb(output)

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert normalized.metadata["missing_normal_primitives"] == 0
    assert normalized.metadata["missing_uv_primitives"] == 0
    assert any(action.action == "recalculate_normals" and action.applied for action in repairs)
    assert any(action.action == "generate_uv_xatlas" and action.applied for action in repairs)


def test_generates_explicit_godot_pbr_material_channels(tmp_path) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    source = tmp_path / "pbr.glb"
    image = base64.b64encode(b"fake-png-bytes").decode("ascii")
    write_glb(
        source,
        {
            "asset": {"version": "2.0"},
            "images": [
                {"uri": f"data:image/png;base64,{image}", "mimeType": "image/png"}
            ],
            "textures": [{"source": 0}],
            "materials": [
                {
                    "name": "PBR Hero",
                    "emissiveFactor": [0.2, 0.1, 0.0],
                    "normalTexture": {"index": 0},
                    "emissiveTexture": {"index": 0},
                    "pbrMetallicRoughness": {
                        "baseColorTexture": {"index": 0},
                        "metallicRoughnessTexture": {"index": 0},
                    },
                }
            ],
            "scenes": [{"nodes": []}],
            "scene": 0,
        },
        [],
    )

    artifacts = generate_material_artifacts(source, tmp_path, tmp_path / "godot")
    material = artifacts[0].tres_path.read_text(encoding="utf-8")

    assert "albedo_texture = ExtResource" in material
    assert "normal_enabled = true" in material
    assert "metallic_texture_channel = 2" in material
    assert "roughness_texture_channel = 1" in material
    assert "emission_enabled = true" in material


def test_normalize_recalculates_normals_opposing_triangle_winding(tmp_path) -> None:
    source = tmp_path / "reversed.glb"
    output = tmp_path / "reversed.normalized.glb"
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    reversed_normals = struct.pack("<9f", 0, 0, -1, 0, 0, -1, 0, 0, -1)
    indices = struct.pack("<3H", 0, 1, 2)
    binary = positions + reversed_normals + indices + b"\0\0"
    write_glb(
        source,
        {
            "asset": {"version": "2.0"},
            "buffers": [{"byteLength": len(binary)}],
            "bufferViews": [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                {"buffer": 0, "byteOffset": 72, "byteLength": 6},
            ],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": 3,
                    "type": "VEC3",
                    "min": [0, 0, 0],
                    "max": [1, 1, 0],
                },
                {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
                {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR"},
            ],
            "meshes": [
                {
                    "primitives": [
                        {"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}
                    ]
                }
            ],
            "nodes": [{"mesh": 0}],
            "scenes": [{"nodes": [0]}],
            "scene": 0,
        },
        [(BIN_CHUNK_TYPE, binary)],
    )

    repairs = normalize_glb(source, output, inspect_glb(source))

    assert any(
        action.action == "recalculate_reversed_normals" and action.applied
        for action in repairs
    )
