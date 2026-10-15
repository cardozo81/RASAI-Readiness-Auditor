"""Offline, read-only Dynatrace RUM configuration advisory (#355).

Operator-supplied JSON is not verified Dynatrace tenant evidence. This command
has no Dynatrace client, secrets, browser, synthetic scoring or network calls.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from rasai.dynatrace_apdex_arch_advisory import (
    ARCHITECTURES, assess_dynatrace_apdex_architecture,
    explain_dynatrace_apdex_pt_br,
)
from rasai.dynatrace_effective_values_adapter import extract_apdex_from_effective_values
from rasai.dynatrace_settings_live import read_live_dynatrace_apdex_settings

_FLAG_MAP = {"observed": True, "not-observed": False, "unknown": None}
_MAX_SNAPSHOT_BYTES = 1024 * 1024


def _unique_snapshot_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A local Settings export with duplicate fields has no unique meaning."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate local Settings JSON key")
        result[key] = value
    return result


def _reject_snapshot_constant(token: str) -> None:
    raise ValueError("non-JSON numeric constant in local Settings export")


def _load_offline_snapshot(path: Path) -> object:
    """Bounded UTF-8 physical read; never authenticate a partial/changed file."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("settings JSON must be a regular local file <= 1 MiB")
    before = path.stat()
    if before.st_size > _MAX_SNAPSHOT_BYTES:
        raise ValueError("settings JSON must be a regular local file <= 1 MiB")
    with path.open("rb") as stream:
        try:
            opened = os.fstat(stream.fileno())
        except (OSError, AttributeError, ValueError) as exc:
            raise ValueError("settings JSON changed during physical read") from exc
        raw = stream.read(_MAX_SNAPSHOT_BYTES + 1)
    after = path.stat()
    # On Windows st_ctime_ns is creation time and is not always
    # identical between a path stat and the opened file descriptor,
    # even with unchanged bytes. Use portable dev/inode/size/mtime;
    # retain the POSIX ctime drift guard where it is consistent.
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if os.name != "nt":
        fields += ("st_ctime_ns",)
    if (
        path.is_symlink() or len(raw) > _MAX_SNAPSHOT_BYTES
        or len(raw) != before.st_size
        or any(
            getattr(before, field) != getattr(reference, field)
            for reference in (opened, after) for field in fields
        )
    ):
        raise ValueError("settings JSON changed during physical read")
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_snapshot_keys,
        parse_constant=_reject_snapshot_constant,
    )


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
    source_group.add_argument(
        "--live-base-url", default=None,
        help="Explicit Dynatrace SaaS HTTPS tenant for a read-only settings.read GET.",
    )
    parser.add_argument(
        "--allow-live-settings-read", action="store_true",
        help="Explicitly authorize exactly one live, read-only Settings API request.",
    )
    parser.add_argument(
        "--application-scope", default=None,
        help="Required with --effective-values-json; operator-declared APP scope, NOT verified.",
    )
    args = parser.parse_args(argv)
    settings = None
    exported = None
    if (args.effective_values_json is not None or args.live_base_url is not None) and not args.application_scope:
        parser.error("--application-scope is required with --effective-values-json")
    if args.application_scope and args.effective_values_json is None and args.live_base_url is None:
        parser.error("--application-scope requires --effective-values-json")
    if args.allow_live_settings_read and args.live_base_url is None:
        parser.error("--allow-live-settings-read requires --live-base-url")
    if args.live_base_url is not None:
        if not args.allow_live_settings_read:
            parser.error("explicit --allow-live-settings-read is required")
        token = os.environ.get("DYNATRACE_API_TOKEN")
        try:
            exported = read_live_dynatrace_apdex_settings(
                base_url=args.live_base_url,
                application_scope=args.application_scope,
                api_token=token,
            )
        except ValueError:
            parser.error("live Dynatrace read-only Settings API request unavailable or invalid")
        settings = exported["settings"]
    input_path = args.settings_json or args.effective_values_json
    if input_path is not None:
        try:
            supplied = _load_offline_snapshot(input_path)
        except (OSError, UnicodeError, ValueError, TypeError):
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
        "AUTHENTICATED_LIVE_DYNATRACE_EFFECTIVE_VALUES"
        if args.live_base_url is not None else
        "OPERATOR_SUPPLIED_DYNATRACE_EFFECTIVE_VALUES_EXPORT"
        if exported is not None else
        "OPERATOR_SUPPLIED_LOCAL_JSON" if settings is not None else "NO_SETTINGS"
    )
    if exported is not None:
        result["effective_values_export"] = {
            key: value for key, value in exported.items() if key != "settings"
        }
    if args.live_base_url is not None and exported is not None:
        result["settings_provenance"] = exported["settings_provenance"]
        result["scope_provenance"] = exported["scope_provenance"]
        result["rum_action_population_verified"] = False
        result["rasai_same_page_device_time_verified"] = False
    # Populate independently observed transport/scope evidence BEFORE the
    # human-readable projection. A bare source string must never be
    # sufficient to claim that a live tenant was consulted.
    result["actual_dynatrace_tenant_consulted"] = args.live_base_url is not None
    result["dynatrace_provider_requests"] = 1 if args.live_base_url is not None else 0
    result["rasai_synthetic_apdex_unchanged"] = True
    result["analyst_guidance_pt_br"] = explain_dynatrace_apdex_pt_br(result)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
