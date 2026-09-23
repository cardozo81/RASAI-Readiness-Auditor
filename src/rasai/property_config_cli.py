"""CLI for validating and inspecting secret-free property configurations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .property_config import PROPERTY_CONFIG_CONTRACT, load_property_config
from .secret_safety import redact_value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai property-config",
        description="Validate versionable PROPERTY-CONFIG-001 files without exposing secrets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate schema and secret-safety rules")
    validate.add_argument("path", type=Path)

    show = subparsers.add_parser("show", help="Show the normalized secret-safe configuration")
    show.add_argument("path", type=Path)

    references = subparsers.add_parser("references", help="List required environment references by name only")
    references.add_argument("path", type=Path)
    references.add_argument("--missing-only", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        config = load_property_config(args.path)
        if args.command == "validate":
            print(json.dumps({
                "contract": PROPERTY_CONFIG_CONTRACT,
                "status": "VALID",
                "property_id": config.property_id,
                "origin": config.origin,
                "source": str(config.source),
                "secret_values_persisted": False,
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "show":
            print(json.dumps(redact_value(config.document), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "references":
            names = config.missing_environment_references() if args.missing_only else config.environment_references()
            print(json.dumps({
                "contract": PROPERTY_CONFIG_CONTRACT,
                "property_id": config.property_id,
                "references": list(names),
                "values_exposed": False,
            }, ensure_ascii=False, indent=2))
            return 0
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
