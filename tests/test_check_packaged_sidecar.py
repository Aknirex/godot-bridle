from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "check-packaged-sidecar.py"
SPEC = importlib.util.spec_from_file_location("check_packaged_sidecar", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
check_packaged_sidecar = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_packaged_sidecar)


def test_validate_messages_accepts_ready_and_health_response() -> None:
    output = "\n".join(
        (
            '{"jsonrpc":"2.0","method":"sidecar.ready","params":{}}',
            '{"jsonrpc":"2.0","id":1,"result":{"status":"ok"}}',
        )
    )

    check_packaged_sidecar.validate_messages(output)


def test_validate_messages_requires_ready_notification() -> None:
    with pytest.raises(RuntimeError, match="sidecar.ready"):
        check_packaged_sidecar.validate_messages(
            '{"jsonrpc":"2.0","id":1,"result":{"status":"ok"}}'
        )


def test_validate_messages_requires_health_response() -> None:
    with pytest.raises(RuntimeError, match="health request"):
        check_packaged_sidecar.validate_messages(
            '{"jsonrpc":"2.0","method":"sidecar.ready","params":{}}'
        )
