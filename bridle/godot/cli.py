from __future__ import annotations

import asyncio
from contextlib import suppress
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
    stdout_task = asyncio.create_task(process.stdout.read())
    stderr_task = asyncio.create_task(process.stderr.read())
    with suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=timeout_seconds)

    if process.returncode is None:
        # The child can exit between the returncode check and kill(). Treat that
        # race as normal instead of replacing the timeout result with
        # ProcessLookupError.
        with suppress(ProcessLookupError):
            process.kill()
        stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        return GodotImportResult(
            success=False,
            exit_code=-1,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            safe_details="Godot import check timed out.",
        )

    stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return GodotImportResult(
        success=process.returncode == 0,
        exit_code=process.returncode or 0,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        safe_details=(
            "Godot import check completed."
            if process.returncode == 0
            else f"Godot import check failed with exit code {process.returncode}."
        ),
    )
