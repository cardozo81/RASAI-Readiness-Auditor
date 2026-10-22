"""Offline architectural context of an existing AUD, with no collection."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Sequence

from rasai.architecture_audit_projection import inspect_audit_architecture_context
from rasai.architecture_audit_html import _public_url
from rasai.architecture_consumer_eligibility import architecture_consumer_eligibility


def _public_cli_projection(projection: dict) -> dict:
    """Sanitize CLI serialization only; never alter sealed M6 identity.

    The canonical resolver requires the exact unmodified requested/final URLs.
    Its advisory projection stays backward compatible for in-memory consumers.
    The human CLI is a publication boundary and must not leak URL userinfo,
    tokens in query strings, fragments, or embedded credentials.
    """
    output = dict(projection)
    records = projection.get("snapshots")
    if isinstance(records, list):
        output["snapshots"] = [
            {**row, "requested_url": _public_url(row.get("requested_url")),
             "final_url": _public_url(row.get("final_url"))}
            if isinstance(row, dict) else row
            for row in records
        ]
    output["url_exposure"] = "SCHEME_HOST_PATH_ONLY_QUERY_REDACTED"
    output["raw_url_tokens_exposed"] = False
    return output


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
    print(json.dumps(_public_cli_projection(projection), ensure_ascii=False, sort_keys=True))
    return 0 if projection["status"] == "ADVISORY_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
