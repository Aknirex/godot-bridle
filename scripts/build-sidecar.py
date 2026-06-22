from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rust_host_triple() -> str:
    result = subprocess.run(
        ["rustc", "-vV"],
        check=True,
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("host: "):
            return line.removeprefix("host: ").strip()
    raise RuntimeError("rustc did not report a host target triple")


def executable_suffix(target_triple: str) -> str:
    if "-linux-gnu" in target_triple:
        return ""
    if "-windows-" in target_triple:
        return ".exe"
    raise ValueError(f"Unsupported sidecar target triple: {target_triple}")


def sidecar_runtime_path(root: Path, target_triple: str) -> Path:
    return (
        root
        / "desktop"
        / "src-tauri"
        / "binaries"
        / "bridle-sidecar-runtime"
        / f"bridle-sidecar{executable_suffix(target_triple)}"
    )


def daemon_runtime_path(root: Path, target_triple: str) -> Path:
    return (
        root
        / "desktop"
        / "src-tauri"
        / "binaries"
        / "bridle-daemon-runtime"
        / f"bridled{executable_suffix(target_triple)}"
    )


def build_python_worker(target_path: Path) -> None:
    temp_root = Path(tempfile.gettempdir()) / "godot-bridle-nuitka"
    shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=standalone",
        "--assume-yes-for-downloads",
        "--remove-output",
        "--nofollow-import-to=litellm",
        "--nofollow-import-to=chromadb",
        "--nofollow-import-to=tiktoken",
        "--nofollow-import-to=pytest",
        f"--output-dir={temp_root}",
        f"--output-filename={target_path.name}",
        str(ROOT / "bridle" / "app" / "sidecar_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    built_dir = temp_root / "sidecar_entry.dist"
    built_path = built_dir / target_path.name
    if not built_path.is_file():
        raise FileNotFoundError(f"Nuitka did not create {built_path}")
    shutil.rmtree(target_path.parent, ignore_errors=True)
    shutil.copytree(built_dir, target_path.parent)
    (target_path.parent / "bridle-worker.json").write_text(
        json.dumps(
            {
                "packager": "nuitka",
                "protocol_version": "2026-06-22",
                "entrypoint": target_path.name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def build_daemon(target_path: Path) -> None:
    manifest = ROOT / "desktop" / "src-tauri" / "Cargo.toml"
    subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--manifest-path",
            str(manifest),
            "--bin",
            "bridled",
        ],
        cwd=ROOT,
        check=True,
    )
    source = manifest.parent / "target" / "release" / target_path.name
    if not source.is_file():
        raise FileNotFoundError(f"Cargo did not create {source}")
    if target_path.is_file() and filecmp.cmp(source, target_path, shallow=False):
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target_path)
    except PermissionError as error:
        raise RuntimeError(
            "Cannot replace the Bridle daemon while it is running. Close desktop/plugin "
            "clients or set BRIDLE_REUSE_SIDECAR=1."
        ) from error


def main() -> int:
    target_triple = os.environ.get("TAURI_ENV_TARGET_TRIPLE") or rust_host_triple()
    sidecar_path = sidecar_runtime_path(ROOT, target_triple)
    daemon_path = daemon_runtime_path(ROOT, target_triple)
    reuse = os.environ.get("BRIDLE_REUSE_SIDECAR") == "1"
    if not reuse or not sidecar_path.is_file():
        build_python_worker(sidecar_path)
        print(f"Built lazy Python worker: {sidecar_path}")
    else:
        print(f"Reusing lazy Python worker: {sidecar_path}")
    if not reuse or not daemon_path.is_file():
        build_daemon(daemon_path)
        print(f"Built lightweight daemon: {daemon_path}")
    else:
        print(f"Reusing lightweight daemon: {daemon_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
