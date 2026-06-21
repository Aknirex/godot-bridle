from __future__ import annotations

import sys
from time import perf_counter

from bridle.godot.cli import run_godot_import_check


async def test_run_godot_import_check_with_python_as_mock_process(tmp_path) -> None:
    (tmp_path / "project.godot").write_text('config/name="Demo"\n', encoding="utf-8")
    mock_godot = tmp_path / "mock_godot.py"
    mock_godot.write_text(
        "import sys\n"
        "print('mock godot import')\n"
        "raise SystemExit(0 if '--headless' in sys.argv and '--path' in sys.argv else 2)\n",
        encoding="utf-8",
    )
    logs_dir = tmp_path / "bridle" / "generated" / "asset" / "logs"

    result = await run_godot_import_check(
        godot_executable=sys.executable,
        project_root=tmp_path,
        logs_dir=logs_dir,
        extra_args=[str(mock_godot)],
        timeout_seconds=5,
    )

    assert result.success
    assert result.exit_code == 0
    assert result.stdout_path.is_file()
    assert result.stderr_path.is_file()
    assert result.stdout_path.read_text(encoding="utf-8").strip() == "mock godot import"


async def test_run_godot_import_check_reports_nonzero_exit(tmp_path) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    mock_godot = tmp_path / "mock_godot.py"
    mock_godot.write_text(
        "import sys\nprint('invalid asset', file=sys.stderr)\nraise SystemExit(3)\n",
        encoding="utf-8",
    )

    result = await run_godot_import_check(
        godot_executable=sys.executable,
        project_root=tmp_path,
        logs_dir=tmp_path / "logs",
        extra_args=[str(mock_godot)],
        timeout_seconds=5,
    )

    assert not result.success
    assert result.exit_code == 3
    assert result.safe_details == "Godot import check failed with exit code 3."
    assert result.stderr_path.read_text(encoding="utf-8").strip() == "invalid asset"


async def test_run_godot_import_check_kills_timed_out_process(tmp_path) -> None:
    (tmp_path / "project.godot").write_text("[application]\n", encoding="utf-8")
    mock_godot = tmp_path / "mock_godot.py"
    mock_godot.write_text(
        "import time\nprint('started', flush=True)\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    started = perf_counter()

    result = await run_godot_import_check(
        godot_executable=sys.executable,
        project_root=tmp_path,
        logs_dir=tmp_path / "logs",
        extra_args=[str(mock_godot)],
        timeout_seconds=0.5,
    )

    assert not result.success
    assert result.exit_code == -1
    assert result.safe_details == "Godot import check timed out."
    assert result.stdout_path.read_text(encoding="utf-8").strip() == "started"
    assert perf_counter() - started < 2
