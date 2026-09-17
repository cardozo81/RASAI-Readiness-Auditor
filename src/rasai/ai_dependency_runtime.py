"""Runtime gates and dependency provenance for non-semantic AI purposes."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from rasai.ai_dependency_contract import fulfillment_dependency_state, record_dependency_snapshot
from rasai.ai_governance import collection_state_is_terminal
from rasai.audit_phase_runtime import require_sealed_evidence

_INSTALLED = False


def _technical_evidence_ids(
    workspace: Any,
    audit_id: str,
    rule_ids: tuple[str, ...],
) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in rule_ids)
        try:
            rows = connection.execute(
                f"SELECT evidence_ids FROM rule_executions WHERE audit_id=? AND rule_id IN ({placeholders})",
                (audit_id, *rule_ids),
            ).fetchall()
        except sqlite3.OperationalError:
            return ()
        values: list[str] = []
        for row in rows:
            try:
                ids = json.loads(str(row["evidence_ids"] or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                ids = []
            if isinstance(ids, list):
                for value in ids:
                    text = str(value).strip()
                    if text and text not in values:
                        values.append(text)
        return tuple(values)
    finally:
        connection.close()


def _install_technical_gate_provenance() -> None:
    from rasai import technical_ai_eligibility as technical

    current = technical.technical_evidence_ready
    if getattr(current, "_rasai_dependency_snapshot", False):
        return

    def ready(workspace: Any, audit_id: str) -> bool:
        try:
            snapshot = require_sealed_evidence(audit_id=audit_id, workspace=workspace)
            sealed = True
        except RuntimeError:
            snapshot = None
            sealed = False
        resource_ready = bool(current(workspace, audit_id))
        result = sealed and resource_ready
        evidence_ids = _technical_evidence_ids(
            workspace,
            audit_id,
            tuple(technical._RESOURCE_RULE_IDS),
        )
        record_dependency_snapshot(
            workspace=workspace,
            audit_id=audit_id,
            purpose="TECHNICAL_AI",
            expected=("EVIDENCE_SEALED", "TECHNICAL_RESOURCE_EVIDENCE"),
            present={
                "EVIDENCE_SEALED": "SUCCESS" if sealed else "PENDING",
                "TECHNICAL_RESOURCE_EVIDENCE": "SUCCESS" if resource_ready else "PENDING",
            },
            evidence_ids=evidence_ids,
            context_fingerprint_input={
                "rules": list(technical._RESOURCE_RULE_IDS),
                "evidence_snapshot_id": getattr(snapshot, "evidence_snapshot_id", None),
            },
            ready=result,
        )
        return result

    ready._rasai_dependency_snapshot = True
    ready._rasai_original = current
    technical.technical_evidence_ready = ready


def _finding_evidence(findings: list[dict[str, Any]]) -> tuple[str, ...]:
    values: list[str] = []
    for finding in findings:
        for raw in finding.get("evidence_ids") or ():
            text = str(raw).strip()
            if text and text not in values:
                values.append(text)
    return tuple(values)


def _install_deep_analysis_gate() -> None:
    from rasai import improvement_intelligence as improvement

    current = improvement._ai_analyze
    if getattr(current, "_rasai_dependency_gate", False):
        return

    def ai_analyze(
        *,
        audit_id: str,
        workspace: Any,
        context: Any,
        config: Any,
        findings: list[dict[str, Any]],
        evidence_context: Mapping[str, Any],
        language: str,
        progress=None,
    ):
        expected, present, fulfillment_ready = fulfillment_dependency_state(
            workspace,
            audit_id,
            exclude_components=("IMPROVEMENT_INTELLIGENCE",),
        )
        try:
            snapshot = require_sealed_evidence(audit_id=audit_id, workspace=workspace)
            sealed = True
        except RuntimeError:
            snapshot = None
            sealed = False
        context_ready = bool(findings) and isinstance(evidence_context, Mapping) and bool(evidence_context)
        all_expected = (*expected, "EVIDENCE_SEALED", "IMPROVEMENT_EVIDENCE_CONTEXT")
        all_present = {
            **present,
            "EVIDENCE_SEALED": "SUCCESS" if sealed else "PENDING",
            "IMPROVEMENT_EVIDENCE_CONTEXT": "SUCCESS" if context_ready else "PENDING",
        }
        evidence_ids = _finding_evidence(findings)
        ready = fulfillment_ready and sealed and context_ready
        record_dependency_snapshot(
            workspace=workspace,
            audit_id=audit_id,
            purpose="DEEP_ANALYSIS",
            expected=all_expected,
            present=all_present,
            evidence_ids=evidence_ids,
            context_fingerprint_input={
                "evidence_snapshot_id": getattr(snapshot, "evidence_snapshot_id", None),
                "snapshot_id": getattr(context, "snapshot_id", None),
                "url": getattr(context, "url", None),
                "domains": list(getattr(config, "domains", ()) or ()),
                "supporting_context": evidence_context,
            },
            ready=ready,
        )
        if not ready:
            missing = [
                name
                for name in all_expected
                if name not in all_present or not collection_state_is_terminal(all_present[name])
            ]
            return "", [], "AI_CONTEXT_NOT_READY:" + ",".join(missing or ["DEPENDENCY"])
        return current(
            audit_id=audit_id,
            workspace=workspace,
            context=context,
            config=config,
            findings=findings,
            evidence_context=evidence_context,
            language=language,
            progress=progress,
        )

    ai_analyze._rasai_dependency_gate = True
    ai_analyze._rasai_original = current
    improvement._ai_analyze = ai_analyze


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_technical_gate_provenance()
    _install_deep_analysis_gate()
    _INSTALLED = True


__all__ = ["install"]
