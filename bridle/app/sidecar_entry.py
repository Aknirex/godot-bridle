from __future__ import annotations

import asyncio

from bridle.app.sidecar import run_stdio_sidecar


def main() -> int:
    return asyncio.run(run_stdio_sidecar())


if __name__ == "__main__":
    raise SystemExit(main())
