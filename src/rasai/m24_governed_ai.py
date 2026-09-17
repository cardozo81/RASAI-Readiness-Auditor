"""Governed AI-only phase for M24.

M24 collects deterministic/network diagnostics before evidence sealing and invokes
technical AI only after the seal. Provider/fallback/attempt persistence stays in the
existing M24 provider runtime. Logical partial continuation is installed by
``m24_partial_runtime`` so initial execution and RPR share the same engine.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from typing import Any

from rasai.audit_phase_runtime import require_sealed_evidence
from rasai.m24_crawling_discovery import M24Diagnostic, M24ExecutionResult, load_m24_result
from rasai.m24_partial_runtime import install as install_partial_runtime, latest_task_status
from rasai.semantic import ProviderState


def _decode(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list, tuple)):
        return raw
    try:
        return json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _load_diagnostics(workspace: Any, audit_id: str) -> tuple[M24Diagnostic, ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = connection.execute(
                """SELECT code,category,severity,title,scope_url,observed_value,evidence_ids,remediation
                   FROM m24_diagnostics WHERE audit_id=? ORDER BY created_at,diagnostic_id""",
                (audit_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            return ()
        return tuple(
            M24Diagnostic(
                code=str(row["code"]),
                category=str(row["category"]),
                severity=str(row["severity"]),
                title=str(row["title"]),
                scope_url=str(row["scope_url"]) if row["scope_url"] else None,
                observed=dict(_decode(row["observed_value"], {})),
                evidence_ids=tuple(
                    str(item)
                    for item in _decode(row["evidence_ids"], [])
                    if str(item).strip()
                ),
                remediation=str(row["remediation"]),
            )
            for row in rows
        )
    finally:
        connection.close()


def _update_run(
    workspace: Any,
    audit_id: str,
    *,
    state: str,
    scoring_impact: str,
) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """UPDATE m24_runs
                   SET ai_enabled=1,ai_state=?,scoring_impact=?,updated_at=datetime('now')
                   WHERE audit_id=?""",
                (state, scoring_impact, audit_id),
            )
    finally:
        connection.close()


def execute_m24_ai_phase(
    *,
    audit_id: str,
    workspace: Any,
    provider: Any,
    enabled: bool,
) -> M24ExecutionResult:
    """Run only the optional technical-AI consumer against sealed persisted M24 facts."""
    base = load_m24_result(audit_id=audit_id, workspace=workspace)
    if base is None:
        raise RuntimeError("M24 deterministic collection must complete before technical AI")
    if not enabled:
        return base

    require_sealed_evidence(audit_id=audit_id, workspace=workspace)
    install_partial_runtime()
    diagnostics = _load_diagnostics(workspace, audit_id)

    try:
        from rasai.m24_ai import maybe_remediate_m24

        result = maybe_remediate_m24(
            audit_id=audit_id,
            workspace=workspace,
            provider=provider,
            diagnostics=diagnostics,
        )
    except Exception:
        _update_run(workspace, audit_id, state="UNAVAILABLE", scoring_impact="NONE")
        reopened = load_m24_result(audit_id=audit_id, workspace=workspace) or base
        return replace(reopened, ai_enabled=True, ai_state="UNAVAILABLE", scoring_impact="NONE")

    assessments: tuple[dict[str, Any], ...] = ()
    if result.explanation and isinstance(
        result.explanation.get("resource_assessments"), list
    ):
        assessments = tuple(
            dict(item)
            for item in result.explanation["resource_assessments"]
            if isinstance(item, dict)
        )

    task_status = latest_task_status(workspace, audit_id)
    if task_status == "COMPLETE":
        persisted_state = result.state.value
    elif task_status in {"PARTIAL", "FAILED", "STALE"}:
        persisted_state = "PARTIAL" if assessments else "UNAVAILABLE"
    else:
        # No resource-bound task means M24 ran as one atomic advisory remediation
        # (for example diagnostics exist but no ROBOTS/SITEMAP scoring evidence).
        persisted_state = result.state.value

    scoring_impact = "BOUNDED_AI_RESOURCE_ASSESSMENT" if assessments else "NONE"
    _update_run(
        workspace,
        audit_id,
        state=persisted_state,
        scoring_impact=scoring_impact,
    )

    # Scoring may safely consume every individually accepted assessment even while the
    # logical technical-AI task remains PARTIAL. Fulfillment remains retryable until all
    # declared requirements are accepted; later RPR clears/rebuilds only this bounded
    # technical scoring bridge using the consolidated task result.
    scoring_state = ProviderState.AVAILABLE.value if assessments else result.state.value
    return replace(
        base,
        ai_enabled=True,
        ai_state=scoring_state,
        scoring_impact=scoring_impact,
        ai_provider=result.provider,
        ai_model=result.model,
        ai_assessments=assessments,
    )


__all__ = ["execute_m24_ai_phase"]
