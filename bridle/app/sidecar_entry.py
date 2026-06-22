from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from bridle.app.sidecar import run_stdio_sidecar


def main() -> int:
    parser = argparse.ArgumentParser(prog="bridle-sidecar")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()
    return asyncio.run(run_stdio_sidecar(args.db))


if __name__ == "__main__":
    raise SystemExit(main())
