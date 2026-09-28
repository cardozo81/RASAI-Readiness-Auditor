"""Reconcile Standards service readiness with canonical collector outcomes.

The Standards matrix does not duplicate PageSpeed, CrUX or browser-native Open Web
Metrics acquisition. This module projects already-persisted owner evidence back into
standards_service_runs. No network, browser or provider call is performed here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3
from typing import Any, Mapping

from rasai.persistence import AuditWorkspace


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _details(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _update_service(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    service_id: str,
    state: str,
    attempted: int,
    succeeded: int,
    details: Mapping[str, Any],
) -> bool:
    row = connection.execute(
        "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id=?",
        (audit_id, service_id),
    ).fetchone()
    if row is None:
        return False
    columns = _columns(connection, "standards_service_runs")
    existing = _details(row["details_json"] if "details_json" in row.keys() else None)
    existing.update(dict(details))
    assignments = ["state=?", "targets_attempted=?", "targets_succeeded=?"]
    values: list[Any] = [str(state).upper(), max(int(attempted), 0), max(int(succeeded), 0)]
    if "details_json" in columns:
        assignments.append("details_json=?")
        values.append(json.dumps(existing, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str))
    if "updated_at" in columns:
        assignments.append("updated_at=?")
        values.append(_utc_now())
    values.extend((audit_id, service_id))
    connection.execute(
        "UPDATE standards_service_runs SET " + ",".join(assignments)
        + " WHERE audit_id=? AND service_id=?",
        tuple(values),
    )
    return True


def _attempt_outcome(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    service: str,
) -> tuple[int, int, tuple[str, ...]]:
    if "web_performance_attempts" not in _tables(connection):
        return 0, 0, ()
    columns = _columns(connection, "web_performance_attempts")
    if not {"audit_id", "service", "status"}.issubset(columns):
        return 0, 0, ()
    rows = connection.execute(
        "SELECT status FROM web_performance_attempts WHERE audit_id=? AND service=? ORDER BY rowid",
        (audit_id, service),
    ).fetchall()
    statuses = tuple(
        str(row[0] or "").upper()
        for row in rows
        if str(row[0] or "").upper() not in {"", "DISABLED", "NOT_CONFIGURED"}
    )
    return len(statuses), sum(status == "SUCCESS" for status in statuses), statuses


def _field_contexts(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
) -> tuple[int, tuple[str, ...]]:
    if "web_performance_observations" not in _tables(connection):
        return 0, ()
    columns = _columns(connection, "web_performance_observations")
    if not {"audit_id", "field_source"}.issubset(columns):
        return 0, ()
    metrics = [name for name in ("lcp_p75_ms", "inp_p75_ms", "cls_p75") if name in columns]
    if not metrics:
        return 0, ()
    predicate = " OR ".join(f"{name} IS NOT NULL" for name in metrics)
    rows = connection.execute(
        f"SELECT field_source FROM web_performance_observations WHERE audit_id=? "
        f"AND field_source IS NOT NULL AND ({predicate})",
        (audit_id,),
    ).fetchall()
    sources = tuple(sorted({str(row[0]).upper() for row in rows if str(row[0] or "").strip()}))
    return len(rows), sources


def _legacy_pagespeed_successes(connection: sqlite3.Connection, *, audit_id: str) -> int:
    if "web_performance_runs" not in _tables(connection):
        return 0
    columns = _columns(connection, "web_performance_runs")
    if not {"audit_id", "pagespeed_successes"}.issubset(columns):
        return 0
    row = connection.execute(
        "SELECT pagespeed_successes FROM web_performance_runs WHERE audit_id=?",
        (audit_id,),
    ).fetchone()
    return int(row[0] or 0) if row is not None else 0


def _state(attempted: int, succeeded: int) -> str:
    if succeeded == attempted and attempted:
        return "SUCCESS"
    if succeeded:
        return "PARTIAL"
    return "ERROR"


def reconcile_owned_service_runs(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
) -> dict[str, str]:
    """Project persisted owner outcomes into existing Standards readiness rows."""
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        tables = _tables(connection)
        if "standards_service_runs" not in tables:
            return {}
        output: dict[str, str] = {}
        with connection:
            attempted, succeeded, statuses = _attempt_outcome(
                connection, audit_id=audit_id, service="PAGESPEED_INSIGHTS"
            )
            if attempted:
                state = _state(attempted, succeeded)
                if _update_service(
                    connection,
                    audit_id=audit_id,
                    service_id="pagespeed",
                    state=state,
                    attempted=attempted,
                    succeeded=succeeded,
                    details={
                        "owner": "M21_WEB_PERFORMANCE",
                        "outcome_source": "web_performance_attempts",
                        "provider_service": "PAGESPEED_INSIGHTS",
                        "attempt_statuses": list(statuses),
                    },
                ):
                    output["pagespeed"] = state
            else:
                legacy = _legacy_pagespeed_successes(connection, audit_id=audit_id)
                if legacy and _update_service(
                    connection,
                    audit_id=audit_id,
                    service_id="pagespeed",
                    state="SUCCESS",
                    attempted=legacy,
                    succeeded=legacy,
                    details={
                        "owner": "M21_WEB_PERFORMANCE",
                        "outcome_source": "web_performance_runs",
                        "legacy_projection": True,
                    },
                ):
                    output["pagespeed"] = "SUCCESS"

            field_count, field_sources = _field_contexts(connection, audit_id=audit_id)
            direct_attempted, direct_succeeded, direct_statuses = _attempt_outcome(
                connection, audit_id=audit_id, service="CRUX_API"
            )
            if field_count:
                if _update_service(
                    connection,
                    audit_id=audit_id,
                    service_id="crux",
                    state="SUCCESS",
                    attempted=field_count,
                    succeeded=field_count,
                    details={
                        "owner": "M21_WEB_PERFORMANCE",
                        "outcome_source": "web_performance_observations",
                        "field_sources": list(field_sources),
                        "direct_api_attempts": direct_attempted,
                        "direct_api_successes": direct_succeeded,
                        "direct_api_statuses": list(direct_statuses),
                        "direct_api_call_implied": False,
                    },
                ):
                    output["crux"] = "SUCCESS"
            elif direct_attempted:
                state = _state(direct_attempted, direct_succeeded)
                if _update_service(
                    connection,
                    audit_id=audit_id,
                    service_id="crux",
                    state=state,
                    attempted=direct_attempted,
                    succeeded=direct_succeeded,
                    details={
                        "owner": "M21_WEB_PERFORMANCE",
                        "outcome_source": "web_performance_attempts",
                        "provider_service": "CRUX_API",
                        "attempt_statuses": list(direct_statuses),
                    },
                ):
                    output["crux"] = state

            if "standards_metric_observations" in tables:
                columns = _columns(connection, "standards_metric_observations")
                if {"audit_id", "source", "value"}.issubset(columns):
                    row = connection.execute(
                        "SELECT COUNT(*) FROM standards_metric_observations "
                        "WHERE audit_id=? AND source='OPEN-WEB-METRICS-001' AND value IS NOT NULL",
                        (audit_id,),
                    ).fetchone()
                    observed = int(row[0] or 0) if row is not None else 0
                    if observed and _update_service(
                        connection,
                        audit_id=audit_id,
                        service_id="open-web-metrics",
                        state="SUCCESS",
                        attempted=observed,
                        succeeded=observed,
                        details={
                            "owner": "OPEN_WEB_METRICS",
                            "outcome_source": "standards_metric_observations",
                            "observations": observed,
                            "external_calls": 0,
                        },
                    ):
                        output["open-web-metrics"] = "SUCCESS"
        return output
    finally:
        connection.close()


__all__ = ["reconcile_owned_service_runs"]
