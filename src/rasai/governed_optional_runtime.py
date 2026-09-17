"""Composition bridge moving optional collection out of report finalization.

The existing optional integrations keep their storage, safety and reporting code.  This
module only changes *when* their collectors execute.  Finalizer wrappers subsequently
read the already-persisted current-run outcome instead of performing another network
request.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.audit_phase_runtime import register_collection_hook


_INSTALLED = False
_CURRENT_AUDIT_ARGV: tuple[str, ...] = ()
_M21_CACHE: dict[str, Any] = {}


def configure_audit_argv(argv: Sequence[str]) -> None:
    global _CURRENT_AUDIT_ARGV
    _CURRENT_AUDIT_ARGV = tuple(str(item) for item in argv)


def _service_row(workspace: Any, audit_id: str, service_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            row = connection.execute(
                "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id=?",
                (audit_id, service_id),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
        if row is None:
            return None
        details: dict[str, Any] = {}
        try:
            parsed = json.loads(str(row["details_json"] or "{}"))
            if isinstance(parsed, dict):
                details = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        details.setdefault("service_state", str(row["state"] or "UNKNOWN"))
        details.setdefault("collection_state", str(row["state"] or "UNKNOWN"))
        details.setdefault("requested", bool(row["requested"]))
        details.setdefault("configured", bool(row["configured"]))
        details.setdefault("effective_enabled", bool(row["effective_enabled"]))
        details.setdefault("targets_attempted", int(row["targets_attempted"] or 0))
        details.setdefault("targets_succeeded", int(row["targets_succeeded"] or 0))
        return details
    finally:
        connection.close()


def _aggregate(states: Sequence[str]) -> str:
    normalized = tuple(str(value or "UNKNOWN").upper() for value in states)
    enabled = tuple(value for value in normalized if value not in {"DISABLED", "NOT_CONFIGURED", "NOT_APPLICABLE"})
    if not enabled:
        return "DISABLED"
    if all(value in {"SUCCESS", "NO_DATA", "SKIPPED", "SKIPPED_SOURCE_BLOCKER"} for value in enabled):
        return "SUCCESS" if any(value == "SUCCESS" for value in enabled) else "NO_DATA"
    if any(value == "SUCCESS" for value in enabled):
        return "PARTIAL"
    if all(value in {"ERROR", "FAILED_RETRYABLE", "FAILED_PERMANENT", "BLOCKED"} for value in enabled):
        return "ERROR"
    return "PARTIAL"


def _install_gsc() -> None:
    from rasai import standards_gsc_observability_runtime as gsc

    original = gsc.collect_configured_search_console
    if getattr(original, "_rasai_governed_collection", False):
        return

    def collect(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        if source_blocked:
            # GSC is a remote property API rather than another target navigation, so a
            # source blocker does not make the configured property data unsafe to query.
            pass
        result = original(audit_id=audit_id, workspace=workspace)
        return dict(result)

    collect._rasai_governed_collection = True
    collect._rasai_original = original
    register_collection_hook("GOOGLE_SEARCH_CONSOLE", collect, order=40)

    def persisted_only(*, audit_id: str, workspace: Any, env: Mapping[str, str] | None = None):
        del env
        return _service_row(workspace, audit_id, "google-search-console") or {
            "service_state": "NOT_CONFIGURED",
            "collection_state": "NOT_CONFIGURED",
            "requested": False,
            "configured": False,
            "effective_enabled": False,
            "operations": [],
            "errors": [],
        }

    persisted_only._rasai_governed_projection_only = True
    persisted_only._rasai_original = original
    gsc.collect_configured_search_console = persisted_only


def _install_external_observability() -> None:
    from rasai import external_observability_runtime as external

    original = external.collect_configured_external_observability
    if getattr(original, "_rasai_governed_collection", False):
        return

    def collect(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        del source_blocked
        outcomes = original(audit_id=audit_id, workspace=workspace)
        states = [
            str(item.get("collection_state") or item.get("service_state") or "UNKNOWN")
            for item in outcomes.values()
        ]
        return {
            "collection_state": _aggregate(states),
            "services": outcomes,
        }

    collect._rasai_governed_collection = True
    collect._rasai_original = original
    register_collection_hook("EXTERNAL_OBSERVABILITY", collect, order=50)

    def persisted_only(*, audit_id: str, workspace: Any, env: Mapping[str, str] | None = None):
        del env
        outcomes: dict[str, dict[str, Any]] = {}
        for service_id in ("crux-history", "microsoft-clarity", "common-crawl"):
            outcomes[service_id] = _service_row(workspace, audit_id, service_id) or {
                "service_state": "NOT_CONFIGURED",
                "collection_state": "NOT_CONFIGURED",
                "requested": False,
                "configured": False,
                "effective_enabled": False,
                "targets_attempted": 0,
                "targets_succeeded": 0,
                "datasets": [],
                "errors": [],
            }
        return outcomes

    persisted_only._rasai_governed_projection_only = True
    persisted_only._rasai_original = original
    external.collect_configured_external_observability = persisted_only


def _m21_config():
    if not _CURRENT_AUDIT_ARGV or "audit" not in _CURRENT_AUDIT_ARGV:
        return None
    from rasai import cli as audit_cli
    from rasai import cli_extensions

    parser = cli_extensions.build_parser()
    args = parser.parse_args(list(_CURRENT_AUDIT_ARGV))
    return audit_cli._configured_web_performance(args)


def _install_m21() -> None:
    def collect(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        from rasai import cli as audit_cli
        from rasai import cli_extensions
        from rasai.m24_crawling_discovery import execute_m24 as base_execute_m24

        config = _m21_config()
        if config is None:
            return {"collection_state": "DISABLED", "reason": "NO_AUDIT_CLI_CONTEXT"}

        current_execute = audit_cli.execute_m21
        current_m24 = cli_extensions.execute_m24

        # The CLI extension composes M23 and M24 into the M21 call. During the
        # collection phase M24 is allowed to persist deterministic/network evidence but
        # not to cross the provider boundary; its AI-only phase runs after sealing.
        def deterministic_m24(*args: Any, **kwargs: Any):
            kwargs["technical_ai"] = False
            return base_execute_m24(*args, **kwargs)

        cli_extensions.execute_m24 = deterministic_m24
        try:
            result = current_execute(audit_id=audit_id, workspace=workspace, config=config)
        finally:
            cli_extensions.execute_m24 = current_m24

        _M21_CACHE[audit_id] = result

        # cli.main historically invokes M21 after run_audit returns. Replace only this
        # in-process second invocation with the already-persisted result. Reporting
        # enrichment still runs normally and therefore remains a projection step.
        def cached_execute(*args: Any, **kwargs: Any):
            requested_audit = str(kwargs.get("audit_id") or "")
            if requested_audit == audit_id and requested_audit in _M21_CACHE:
                return _M21_CACHE[requested_audit]
            return current_execute(*args, **kwargs)

        cached_execute._rasai_governed_projection_only = True
        cached_execute._rasai_original = current_execute
        audit_cli.execute_m21 = cached_execute
        state = str(getattr(result, "status", "SUCCESS") or "SUCCESS").upper()
        return {
            "collection_state": state,
            "enabled": bool(getattr(config, "enabled", False)),
            "pages_considered": int(getattr(result, "pages_considered", 0) or 0),
            "context_attempts": int(getattr(result, "context_attempts", 0) or 0),
            "successful_contexts": int(getattr(result, "successful_contexts", 0) or 0),
            "source_blocked": source_blocked,
        }

    register_collection_hook("WEB_PERFORMANCE_APDEX", collect, order=20)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m21()
    _install_gsc()
    _install_external_observability()
    _INSTALLED = True


__all__ = ["configure_audit_argv", "install"]
