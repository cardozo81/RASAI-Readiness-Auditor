"""Offline, read-only Dynatrace RUM configuration advisory (#355).

Operator-supplied JSON is not verified Dynatrace tenant evidence. This command
has no Dynatrace client, secrets, browser, synthetic scoring or network calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from rasai.dynatrace_apdex_arch_advisory_355 import (
    ARCHITECTURES, assess_dynatrace_apdex_architecture,
)

_FLAG_MAP = {"observed": True, "not-observed": False, "unknown": None}
_MAX_SNAPSHOT_BYTES = 1024 * 1024


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline Dynatrace RUM Load/XHR/Custom Apdex advisory; no account access."
    )
    parser.add_argument(
        "--architecture", choices=sorted(ARCHITECTURES), required=True,
        help="Declared architecture, not an independently verified M6 observation.",
    )
    parser.add_argument(
        "--architecture-evidence-id", default=None,
        help="Operator-supplied M6 evidence reference (unverified by this command).",
    )
    parser.add_argument(
        "--soft-navigation", choices=tuple(_FLAG_MAP), default="unknown",
    )
    parser.add_argument(
        "--async-requests", choices=tuple(_FLAG_MAP), default="unknown",
    )
    parser.add_argument(
        "--settings-json", type=Path,
        help="Optional exported settings JSON matching Load/XHR/Custom advisory schema.",
    )
    args = parser.parse_args(argv)
    settings = None
    if args.settings_json is not None:
        path = args.settings_json
        try:
            if path.is_symlink() or not path.is_file() or (
                path.stat().st_size > _MAX_SNAPSHOT_BYTES
            ):
                parser.error("settings JSON must be a regular local file <= 1 MiB")
            settings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            parser.error("settings JSON cannot be read or parsed")
        if not isinstance(settings, dict):
            parser.error("settings JSON must contain an object")
    result = assess_dynatrace_apdex_architecture(
        architecture=args.architecture,
        architecture_evidence_id=args.architecture_evidence_id,
        soft_navigation_observed=_FLAG_MAP[args.soft_navigation],
        async_requests_observed=_FLAG_MAP[args.async_requests],
        settings=settings,
    )
    result["input_source"] = (
        "OPERATOR_SUPPLIED_LOCAL_JSON" if settings is not None else "NO_SETTINGS"
    )
    result["actual_dynatrace_tenant_consulted"] = False
    result["rasai_synthetic_apdex_unchanged"] = True
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
