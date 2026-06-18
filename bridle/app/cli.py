from __future__ import annotations

import argparse
import json

from bridle import __version__


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

    args = parser.parse_args(argv)
    if args.command == "health":
        print(json.dumps(health_payload(), ensure_ascii=False))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
