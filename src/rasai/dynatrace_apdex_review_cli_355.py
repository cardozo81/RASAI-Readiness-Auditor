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
from rasai.dynatrace_effective_values_adapter_355 import extract_apdex_from_effective_values

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
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--settings-json", type=Path,
        help="Optional operator-mapped offline Load/XHR/Custom settings JSON.",
    )
    source_group.add_argument(
        "--effective-values-json", type=Path,
        help="Offline exported Dynatrace Settings API effectiveValues response (no HTTP).",
    )
    parser.add_argument(
        "--application-scope", default=None,
        help="Required with --effective-values-json; operator-declared APP scope, NOT verified.",
    )
    args = parser.parse_args(argv)
    settings = None
    exported = None
    if args.effective_values_json is not None and not args.application_scope:
        parser.error("--application-scope is required with --effective-values-json")
    if args.application_scope and args.effective_values_json is None:
        parser.error("--application-scope requires --effective-values-json")
    input_path = args.settings_json or args.effective_values_json
    if input_path is not None:
        try:
            if input_path.is_symlink() or not input_path.is_file() or (
                input_path.stat().st_size > _MAX_SNAPSHOT_BYTES
            ):
                parser.error("settings JSON must be a regular local file <= 1 MiB")
            supplied = json.loads(input_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            parser.error("settings JSON cannot be read or parsed")
        if not isinstance(supplied, dict):
            parser.error("settings JSON must contain an object")
        if args.effective_values_json is not None:
            try:
                exported = extract_apdex_from_effective_values(
                    supplied, declared_application_scope=args.application_scope,
                )
            except ValueError as exc:
                parser.error(str(exc))
            settings = exported["settings"]
        else:
            settings = supplied
    result = assess_dynatrace_apdex_architecture(
        architecture=args.architecture,
        architecture_evidence_id=args.architecture_evidence_id,
        soft_navigation_observed=_FLAG_MAP[args.soft_navigation],
        async_requests_observed=_FLAG_MAP[args.async_requests],
        settings=settings,
    )
    result["input_source"] = (
        "OPERATOR_SUPPLIED_DYNATRACE_EFFECTIVE_VALUES_EXPORT"
        if exported is not None else
        "OPERATOR_SUPPLIED_LOCAL_JSON" if settings is not None else "NO_SETTINGS"
    )
    if exported is not None:
        result["effective_values_export"] = {
            key: value for key, value in exported.items() if key != "settings"
        }
    result["actual_dynatrace_tenant_consulted"] = False
    result["rasai_synthetic_apdex_unchanged"] = True
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
