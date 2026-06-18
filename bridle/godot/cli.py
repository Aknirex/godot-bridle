from __future__ import annotations

import asyncio
from pathlib import Path

from bridle.domain.assets import GodotImportResult


async def run_godot_import_check(
    *,
    godot_executable: Path,
    project_root: Path,
    logs_dir: Path,
    extra_args: list[str] | None = None,
    timeout_seconds: float = 30,
) -> GodotImportResult:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / "godot_import_stdout.log"
    stderr_path = logs_dir / "godot_import_stderr.log"

    process = await asyncio.create_subprocess_exec(
        str(godot_executable),
        *(extra_args or []),
        "--headless",
        "--path",
        str(project_root),
        "--quit",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        return GodotImportResult(
            success=False,
            exit_code=-1,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            safe_details="Godot import check timed out.",
        )

    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return GodotImportResult(
        success=process.returncode == 0,
        exit_code=process.returncode or 0,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        safe_details="Godot import check completed.",
    )
