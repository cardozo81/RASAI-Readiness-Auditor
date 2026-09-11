"""CLI for detached RASAi execution workers."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from rasai.saas_context_integration import install as install_saas_context_integration
from rasai.secret_safety import redact_value
from rasai.worker import run_one


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rasai worker", description="Run detached control-plane execution jobs")
    sub = parser.add_subparsers(dest="worker_command", required=True)
    once = sub.add_parser("run-once", help="claim and execute at most one durable job")
    once.add_argument("--worker-id", required=True)
    once.add_argument("--audits-root", default="audits")
    once.add_argument("--lease-seconds", type=int, default=900)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    install_saas_context_integration()
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.worker_command == "run-once":
        item = run_one(
            args.worker_id,
            audits_root=args.audits_root,
            lease_seconds=args.lease_seconds,
        )
        if item is None:
            print(json.dumps({"status": "IDLE"}, ensure_ascii=False))
            return 0
        from dataclasses import asdict
        print(json.dumps(redact_value(asdict(item)), ensure_ascii=False, indent=2, default=str))
        return 0 if item.status == "SUCCEEDED" else 1
    raise SystemExit("unsupported worker command")


if __name__ == "__main__":
    raise SystemExit(main())
