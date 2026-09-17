"""Governed AI-only phase for M24.

M24 collects deterministic/network diagnostics before evidence sealing and invokes
technical AI only after the seal. Provider/fallback/attempt persistence stays in the
existing M24 provider runtime; this module adds causal ordering and task provenance.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from rasai.ai_governance import (
    begin_round,
    complete_round,
    register_task,
    task_missing_requirements,
)
from rasai.ai_selective_invalidation import register_task_dependency
from rasai.audit_phase_runtime import require_sealed_evidence
from rasai.m24_crawling_discovery import M24Diagnostic, M24ExecutionResult, load_m24_result
from rasai.semantic import ProviderState


_PURPOSE = "TECHNICAL_AI"
_REQUIREMENTS = ("RESOURCE:SITEMAP", "RESOURCE:ROBOTS")


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
    """Run only the optional technical-AI consumer against persisted M24 facts."""
    base = load_m24_result(audit_id=audit_id, workspace=workspace)
    if base is None:
        raise RuntimeError("M24 deterministic collection must complete before technical AI")
    if not enabled:
        return base

    snapshot = require_sealed_evidence(audit_id=audit_id, workspace=workspace)
    diagnostics = _load_diagnostics(workspace, audit_id)
    evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for diagnostic in diagnostics
            for evidence_id in diagnostic.evidence_ids
        )
    )
    task_id = register_task(
        workspace=workspace,
        audit_id=audit_id,
        purpose=_PURPOSE,
        scope_type="AUDIT",
        scope_key="AUDIT",
        evidence_snapshot_id=snapshot.evidence_snapshot_id,
        requirements=_REQUIREMENTS,
        semantic_contract_version="M24-TECHNICAL-REMEDIATION-v2",
    )
    register_task_dependency(
        workspace=workspace,
        ai_task_id=task_id,
        dependency_kind="TECHNICAL_RESOURCE_EVIDENCE",
        scope_key="AUDIT",
    )
    pending = task_missing_requirements(workspace, task_id)
    if not pending:
        # Same sealed technical evidence and a complete accepted task: never pay for a
        # duplicate provider call merely because reporting/reprocessing is invoked again.
        return base

    round_id = begin_round(
        workspace=workspace,
        ai_task_id=task_id,
        requested_requirements=pending,
        input_payload={
            "evidence_snapshot_id": snapshot.evidence_snapshot_id,
            "evidence_fingerprint": snapshot.fingerprint,
            "requested_requirements": list(pending),
            "diagnostics": [
                {
                    "code": item.code,
                    "category": item.category,
                    "evidence_ids": list(item.evidence_ids),
                }
                for item in diagnostics
            ],
        },
        input_summary={
            "diagnostics": len(diagnostics),
            "evidence_ids": list(evidence_ids),
            "requested_requirements": list(pending),
        },
    )

    try:
        from rasai.m24_ai import maybe_remediate_m24

        result = maybe_remediate_m24(
            audit_id=audit_id,
            workspace=workspace,
            provider=provider,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        complete_round(
            workspace=workspace,
            ai_round_id=round_id,
            accepted={},
            rejected={
                "PROVIDER": {
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:512],
                }
            },
            missing=pending,
            output_payload={"error": type(exc).__name__},
            failed=True,
        )
        _update_run(workspace, audit_id, state="UNAVAILABLE", scoring_impact="NONE")
        return load_m24_result(audit_id=audit_id, workspace=workspace) or base

    assessments: list[dict[str, Any]] = []
    if result.explanation and isinstance(
        result.explanation.get("resource_assessments"), list
    ):
        assessments = [
            item
            for item in result.explanation["resource_assessments"]
            if isinstance(item, dict)
        ]
    accepted = {
        f"RESOURCE:{str(item.get('resource') or '').upper()}": dict(item)
        for item in assessments
        if f"RESOURCE:{str(item.get('resource') or '').upper()}" in pending
    }
    missing = tuple(item for item in pending if item not in accepted)
    complete_round(
        workspace=workspace,
        ai_round_id=round_id,
        accepted=accepted,
        rejected={},
        missing=missing,
        output_payload=(
            result.explanation
            or {"state": result.state.value, "reason": result.reason}
        ),
        failed=result.state is not ProviderState.AVAILABLE,
    )
    scoring_impact = "BOUNDED_AI_RESOURCE_ASSESSMENT" if assessments else "NONE"
    _update_run(
        workspace,
        audit_id,
        state=result.state.value,
        scoring_impact=scoring_impact,
    )
    return load_m24_result(audit_id=audit_id, workspace=workspace) or base


__all__ = ["execute_m24_ai_phase"]
