from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def validate_messages(output: str) -> None:
    messages = [json.loads(line) for line in output.splitlines() if line.strip()]
    if not any(message.get("method") == "sidecar.ready" for message in messages):
        raise RuntimeError("Packaged sidecar did not emit sidecar.ready")
    if not any(message.get("id") == 1 and "result" in message for message in messages):
        raise RuntimeError("Packaged sidecar did not answer the health request")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check-packaged-sidecar.py <sidecar executable>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.is_file():
        raise FileNotFoundError(executable)
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "health", "params": {}})
    result = subprocess.run(
        [str(executable)],
        input=f"{request}\n",
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Packaged sidecar exited with {result.returncode}: {result.stderr[-2_000:]}"
        )
    validate_messages(result.stdout)
    print("Packaged sidecar health check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
