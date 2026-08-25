"""Stable command-line boundary; hardware execution remains operator gated."""

import argparse
import json
from pathlib import Path

from motion_core.config import Settings


def emit(value: dict | list) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def command_status(_args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    emit(
        {
            "connected": False,
            "gateway_target": settings.gateway_target,
            "motion_enabled": False,
            "network_interface": settings.network_interface,
            "mode": "offline",
        }
    )
    return 0


def command_manifest(_args: argparse.Namespace) -> int:
    path = Path(__file__).resolve().parents[1] / "third_party_manifest.json"
    emit(json.loads(path.read_text(encoding="utf-8")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status").set_defaults(handler=command_status)
    subparsers.add_parser("manifest").set_defaults(handler=command_manifest)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args) or 0)
