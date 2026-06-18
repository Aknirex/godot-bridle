from __future__ import annotations

import sys

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
