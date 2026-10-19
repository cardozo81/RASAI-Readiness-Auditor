"""Offline architectural context of an existing AUD, with no collection."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence

from rasai.architecture_audit_projection import inspect_audit_architecture_context
from rasai.architecture_consumer_eligibility import architecture_consumer_eligibility


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Leitura da arquitetura efetiva por URL/device/snapshot, sem coleta"
    )
    parser.add_argument("audit_directory", type=Path)
    parser.add_argument("--consumer-matrix", action="store_true",
                        help="Inclui elegibilidade F3 por catálogo/índice/consumidor")
    args = parser.parse_args(argv)
    folder = args.audit_directory
    projection = inspect_audit_architecture_context(folder.parent, folder.name)
    if args.consumer_matrix:
        projection["consumer_matrix"] = [
            asdict(policy) for policy in architecture_consumer_eligibility()
        ]
    print(json.dumps(projection, ensure_ascii=False, sort_keys=True))
    return 0 if projection["status"] == "ADVISORY_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
