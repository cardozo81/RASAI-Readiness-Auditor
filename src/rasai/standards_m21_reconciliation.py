"""Reconcile the current M21 PageSpeed-first execution with per-service toggles."""
from __future__ import annotations

from dataclasses import replace
import sqlite3
from typing import Any

from rasai.standards_service_registry import service, service_state


def install() -> None:
    from rasai import cli as audit_cli
    from rasai import m21_web_performance as m21

    original = m21.execute_m21
    if getattr(original, "_rasai_m21_service_reconciliation", False):
        audit_cli.execute_m21 = original
        return

    def execute(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        psi = service_state(service("pagespeed"))
        crux = service_state(service("crux"))
        if bool(psi["effective_enabled"]) or not bool(crux["effective_enabled"]):
            return result
        workspace = kwargs.get("workspace")
        audit_id = kwargs.get("audit_id")
        if workspace is None or audit_id is None or not getattr(result, "enabled", False):
            return result

        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                connection.execute(
                    """UPDATE web_performance_attempts
                       SET status='DISABLED',error_message='PageSpeed disabled by service policy'
                       WHERE audit_id=? AND service='PAGESPEED_INSIGHTS' AND error_code='SERVICE_DISABLED'""",
                    (str(audit_id),),
                )
                rows = connection.execute(
                    "SELECT observation_id,status,error_summary,lcp_p75_ms,inp_p75_ms,cls_p75 FROM web_performance_observations WHERE audit_id=?",
                    (str(audit_id),),
                ).fetchall()
                for row in rows:
                    parts = [
                        part for part in str(row["error_summary"] or "").split(";")
                        if part and part != "PAGESPEED:SERVICE_DISABLED"
                    ]
                    has_field = any(row[name] is not None for name in ("lcp_p75_ms", "inp_p75_ms", "cls_p75"))
                    if has_field:
                        status = "SUCCESS" if not parts else "PARTIAL"
                    else:
                        status = "UNAVAILABLE"
                    connection.execute(
                        "UPDATE web_performance_observations SET status=?,error_summary=? WHERE observation_id=?",
                        (status, ";".join(parts) if parts else None, row["observation_id"]),
                    )
                summary = connection.execute(
                    """SELECT COUNT(*) AS total,
                              SUM(CASE WHEN status IN ('SUCCESS','PARTIAL') THEN 1 ELSE 0 END) AS successful,
                              SUM(CASE WHEN status='PARTIAL' THEN 1 ELSE 0 END) AS partial
                       FROM web_performance_observations WHERE audit_id=?""",
                    (str(audit_id),),
                ).fetchone()
                total = int(summary["total"] or 0)
                successful = int(summary["successful"] or 0)
                partial = int(summary["partial"] or 0)
                if total == 0:
                    status, reason = "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
                elif successful == 0:
                    status, reason = "UNAVAILABLE", "CRUX_DATA_UNAVAILABLE"
                elif partial or successful < total:
                    status, reason = "PARTIAL", "ONE_OR_MORE_CRUX_CONTEXTS_UNAVAILABLE"
                else:
                    status, reason = "SUCCESS", None
                connection.execute(
                    """UPDATE web_performance_runs
                       SET status=?,reason=?,successful_contexts=?,pagespeed_successes=0
                       WHERE audit_id=?""",
                    (status, reason, successful, str(audit_id)),
                )
        finally:
            connection.close()

        return replace(
            result,
            status=status,
            successful_contexts=successful,
            pagespeed_attempts=0,
            pagespeed_successes=0,
            partial_contexts=partial,
        )

    execute._rasai_m21_service_reconciliation = True
    m21.execute_m21 = execute
    audit_cli.execute_m21 = execute
