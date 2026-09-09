"""CLI for deterministic Search Intelligence before/after comparison."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .history import compare_search_deployment_pair, compare_search_workspaces


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai search-history",
        description=(
            "Compare persisted Search Intelligence observations without inferring "
            "deployment or ranking causality."
        ),
    )
    parser.add_argument("--baseline-workspace")
    parser.add_argument("--current-workspace")
    parser.add_argument("--milestone")
    parser.add_argument("--baseline-mode", choices=["AUTO", "GOLDEN", "EXPLICIT"], default="AUTO")
    parser.add_argument("--baseline-audit")
    parser.add_argument("--current-audit")
    parser.add_argument("--audits-root", default="audits")
    parser.add_argument("--platform-db")
    parser.add_argument("--json", dest="json_path", help="optional output JSON file")
    return parser


def _payload(result: object) -> dict[str, object]:
    return asdict(result)  # type: ignore[arg-type]


def _write(payload: dict[str, object], json_path: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    print(text)
    if json_path:
        path = Path(json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        direct = bool(args.baseline_workspace or args.current_workspace)
        milestone = bool(args.milestone)
        if direct and milestone:
            raise ValueError("use direct workspaces or --milestone, not both")
        if direct:
            if not args.baseline_workspace or not args.current_workspace:
                raise ValueError("direct mode requires --baseline-workspace and --current-workspace")
            result = compare_search_workspaces(args.baseline_workspace, args.current_workspace)
        elif milestone:
            from rasai.platform.central_store import CentralPlatformStore
            from rasai.platform.deployment import resolve_deployment_pair
            from rasai.platform.store import default_platform_database

            database = Path(args.platform_db) if args.platform_db else default_platform_database(args.audits_root)
            with CentralPlatformStore(database) as store:
                pair = resolve_deployment_pair(
                    store,
                    args.milestone,
                    baseline_mode=args.baseline_mode,
                    baseline_audit_id=args.baseline_audit,
                    current_audit_id=args.current_audit,
                )
                result = compare_search_deployment_pair(store, pair)
        else:
            raise ValueError(
                "provide --baseline-workspace/--current-workspace or --milestone"
            )
        _write(_payload(result), args.json_path)
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(f"RASAI Search history error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
