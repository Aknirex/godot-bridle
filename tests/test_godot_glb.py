from __future__ import annotations

from bridle.godot.glb import inspect_glb


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
