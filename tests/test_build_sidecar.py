from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build-sidecar.py"
SPEC = importlib.util.spec_from_file_location("build_sidecar", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
build_sidecar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_sidecar)


def test_linux_sidecar_target_has_no_extension(tmp_path: Path) -> None:
    target = build_sidecar.sidecar_runtime_path(tmp_path, "x86_64-unknown-linux-gnu")

    assert target == (
        tmp_path / "desktop/src-tauri/binaries/bridle-sidecar-runtime/bridle-sidecar"
    )


def test_windows_sidecar_target_has_exe_extension(tmp_path: Path) -> None:
    target = build_sidecar.sidecar_runtime_path(tmp_path, "x86_64-pc-windows-msvc")

    assert target == (
        tmp_path / "desktop/src-tauri/binaries/bridle-sidecar-runtime/bridle-sidecar.exe"
    )


def test_sidecar_target_rejects_unsupported_platform(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported sidecar target triple"):
        build_sidecar.sidecar_runtime_path(tmp_path, "aarch64-apple-darwin")


def test_windows_daemon_target_has_exe_extension(tmp_path: Path) -> None:
    assert build_sidecar.daemon_runtime_path(tmp_path, "x86_64-pc-windows-msvc") == (
        tmp_path / "desktop/src-tauri/binaries/bridle-daemon-runtime/bridled.exe"
    )
