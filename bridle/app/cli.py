from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from bridle import __version__
from bridle.app.sidecar import run_stdio_sidecar


def health_payload() -> dict[str, str]:
    return {
        "name": "godot-bridle",
        "version": __version__,
        "status": "ok",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bridle")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="Print a minimal core health payload.")
    sidecar_parser = subparsers.add_parser("sidecar", help="Run the stdio JSON-RPC sidecar.")
    sidecar_parser.add_argument("--db", type=Path, default=None, help="SQLite database path.")

    args = parser.parse_args(argv)
    if args.command == "health":
        print(json.dumps(health_payload(), ensure_ascii=False))
        return 0
    if args.command == "sidecar":
        return asyncio.run(run_stdio_sidecar(args.db))

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
