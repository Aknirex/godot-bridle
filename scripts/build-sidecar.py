from __future__ import annotations

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


def sidecar_target_path(root: Path, target_triple: str) -> Path:
    if "-linux-gnu" in target_triple:
        suffix = ""
    elif "-windows-" in target_triple:
        suffix = ".exe"
    else:
        raise ValueError(f"Unsupported sidecar target triple: {target_triple}")
    return root / "desktop" / "src-tauri" / "binaries" / (
        f"bridle-sidecar-{target_triple}{suffix}"
    )


def main() -> int:
    target_triple = os.environ.get("TAURI_ENV_TARGET_TRIPLE") or rust_host_triple()
    target_path = sidecar_target_path(ROOT, target_triple)
    if os.environ.get("BRIDLE_REUSE_SIDECAR") == "1" and target_path.is_file():
        print(f"Reusing existing sidecar: {target_path}")
        return 0

    temp_root = Path(tempfile.gettempdir()) / "godot-bridle-pyinstaller"
    spec_path = temp_root / "spec"
    work_path = temp_root / "build"
    dist_path = temp_root / "dist"
    shutil.rmtree(temp_root, ignore_errors=True)
    spec_path.mkdir(parents=True)
    work_path.mkdir(parents=True)
    dist_path.mkdir(parents=True)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYINSTALLER_CONFIG_DIR", str(temp_root / "cache"))
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--collect-data",
        "litellm",
        "--collect-all",
        "tiktoken",
        "--hidden-import",
        "tiktoken_ext.openai_public",
        "--name",
        "bridle-sidecar",
        "--specpath",
        str(spec_path),
        "--workpath",
        str(work_path),
        "--distpath",
        str(dist_path),
        str(ROOT / "bridle" / "app" / "sidecar_entry.py"),
    ]
    subprocess.run(command, cwd=ROOT, env=env, check=True)

    built_name = "bridle-sidecar.exe" if target_path.suffix == ".exe" else "bridle-sidecar"
    built_path = dist_path / built_name
    if not built_path.is_file():
        raise FileNotFoundError(f"PyInstaller did not create {built_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(built_path, target_path)
    print(f"Built sidecar: {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
