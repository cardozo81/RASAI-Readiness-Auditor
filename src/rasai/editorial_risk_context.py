"""Governed editorial-risk/YMYL context shared by analysis and report projection.

Operator configuration remains canonical in content_analysis_contexts. AUTO
interpretations are execution-scoped AI inference and are never promoted to configured
facts or direct score inputs. The helper combines canonical configuration, persisted or
current-execution AUTO interpretation, and the existing SC-P12 coherence assessment.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping


_YMYL_ALIGNMENT_LABELS = {
    "COHERENT": "Aderente ao contexto YMYL observado",
    "PARTIAL": "Aderência parcial ao contexto YMYL; há lacunas a tratar",
    "INCOHERENT": "Não aderente ao contexto YMYL observado",
    "NOT_DETERMINABLE": "Aderência YMYL não determinável com a evidência disponível",
    "NOT_APPLICABLE": "Contexto YMYL não aplicável à evidência avaliada",
}


def _database_path(workspace: Any) -> Path:
    database = getattr(workspace, "database", None)
    if database is not None:
        return Path(database)
    candidate = Path(workspace)
    if candidate.name == "audit.db" or candidate.suffix.casefold() == ".db":
        return candidate
    root = Path(getattr(workspace, "root", candidate))
    return root / "audit.db"


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def _rows(connection: sqlite3.Connection, table: str, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, table):
        return []
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if "audit_id" not in columns:
        return []
    return [
        dict(row)
        for row in connection.execute(
            f"SELECT * FROM {table} WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall()
    ]


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else []


def _float_or_none(value: Any) -> float | None:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _normalized_interpretation(raw: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    return {
        "status": str(raw.get("status") or "NOT_DETERMINABLE").upper(),
        "value": raw.get("value"),
        "confidence": _float_or_none(raw.get("confidence")),
        "rationale": str(raw.get("rationale") or "").strip(),
        "evidence_ids": _json_list(raw.get("evidence_ids")),
        "provider": raw.get("provider"),
        "model": raw.get("model"),
        "snapshot_id": raw.get("snapshot_id"),
        "page_url": raw.get("page_url"),
        "sequence_no": int(raw.get("sequence_no") or 0),
        "source": source,
    }


def _alignment_result(coherence: list[dict[str, Any]]) -> str:
    results = [str(row.get("result") or "NOT_DETERMINABLE").upper() for row in coherence]
    if "INCOHERENT" in results:
        return "INCOHERENT"
    if "PARTIAL" in results:
        return "PARTIAL"
    if results and all(item in {"COHERENT", "NOT_APPLICABLE"} for item in results):
        return "COHERENT" if "COHERENT" in results else "NOT_APPLICABLE"
    return "NOT_DETERMINABLE"


def ymyl_alignment_label(value: Any) -> str:
    token = str(value or "NOT_DETERMINABLE").upper()
    return _YMYL_ALIGNMENT_LABELS.get(token, token.replace("_", " ").title())


def build_editorial_risk_context(
    workspace: Any,
    audit_id: str,
    *,
    page_url: str | None = None,
) -> dict[str, Any]:
    """Return the exact editorial/YMYL context available to governed AI consumers."""
    database = _database_path(workspace)
    configured: dict[str, Any] = {}
    interpretations: dict[str, dict[str, Any]] = {}
    coherence: list[dict[str, Any]] = []

    if database.is_file():
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            contexts = _rows(connection, "content_analysis_contexts", audit_id)
            if contexts:
                configured = dict(contexts[-1])

            for row in _rows(connection, "content_context_interpretations", audit_id):
                row_url = str(row.get("page_url") or "")
                if page_url and row_url and row_url != page_url:
                    continue
                field = str(row.get("field_name") or "")
                if not field:
                    continue
                candidate = _normalized_interpretation(
                    {
                        "status": row.get("status"),
                        "value": row.get("interpreted_value"),
                        "confidence": row.get("confidence"),
                        "rationale": row.get("rationale"),
                        "evidence_ids": row.get("evidence_ids_json"),
                        "provider": row.get("provider"),
                        "model": row.get("model"),
                        "snapshot_id": row.get("snapshot_id"),
                        "page_url": row.get("page_url"),
                        "sequence_no": row.get("sequence_no"),
                    },
                    source="PERSISTED_AI_INFERENCE",
                )
                current = interpretations.get(field)
                if current is None or candidate["sequence_no"] >= current["sequence_no"]:
                    interpretations[field] = candidate

            for row in _rows(connection, "semantic_coherence_assessments", audit_id):
                if str(row.get("criterion_id") or "") != "SC-P12":
                    continue
                row_url = str(row.get("page_url") or "")
                if page_url and row_url and row_url != page_url:
                    continue
                evidence_ids = _json_list(
                    row.get("evidence_ids_json")
                    if row.get("evidence_ids_json") is not None
                    else row.get("evidence_ids")
                )
                coherence.append(
                    {
                        "criterion_id": "SC-P12",
                        "page_url": row.get("page_url"),
                        "snapshot_id": row.get("snapshot_id"),
                        "result": str(row.get("result") or "NOT_DETERMINABLE").upper(),
                        "confidence": _float_or_none(row.get("confidence")),
                        "declared_context": row.get("declared_context"),
                        "observed_context": row.get("observed_context"),
                        "reasoning_summary": row.get("reasoning_summary"),
                        "evidence_ids": evidence_ids,
                        "provider": row.get("provider"),
                        "model": row.get("model"),
                    }
                )
        finally:
            connection.close()

    try:
        from rasai.ai_execution_state import current_ai_executions

        for execution in current_ai_executions():
            for record in tuple(
                getattr(execution.recorder, "context_interpretations", ()) or ()
            ):
                record_url = str(getattr(record, "page_url", "") or "")
                if page_url and record_url and record_url != page_url:
                    continue
                fields = getattr(record, "fields", {})
                if not isinstance(fields, Mapping):
                    continue
                for field, raw in fields.items():
                    if not isinstance(raw, Mapping):
                        continue
                    candidate = _normalized_interpretation(
                        {
                            **dict(raw),
                            "provider": getattr(record, "provider", None),
                            "model": getattr(record, "model", None),
                            "snapshot_id": getattr(record, "snapshot_id", None),
                            "page_url": getattr(record, "page_url", None),
                            "sequence_no": getattr(record, "sequence_no", 0),
                        },
                        source="CURRENT_AI_INFERENCE",
                    )
                    current = interpretations.get(str(field))
                    if (
                        current is None
                        or candidate["sequence_no"] >= current["sequence_no"]
                        or current["source"] == "PERSISTED_AI_INFERENCE"
                    ):
                        interpretations[str(field)] = candidate
    except Exception:
        pass

    fields = (
        "risk_profile",
        "ymyl_category",
        "page_purpose",
        "intended_audience",
        "experience_requirement",
        "freshness_sensitivity",
        "content_origin",
    )
    canonical = {
        field: configured.get(field)
        for field in fields
        if field in configured
    }

    def effective(field: str) -> Any:
        configured_value = str(canonical.get(field) or "auto").casefold()
        if configured_value != "auto":
            return canonical.get(field)
        item = interpretations.get(field) or {}
        if str(item.get("status") or "").upper() == "INTERPRETED":
            return item.get("value")
        return "auto"

    effective_profile = effective("risk_profile")
    effective_category = effective("ymyl_category")
    alignment = _alignment_result(coherence)
    evidence_ids = list(
        dict.fromkeys(
            [
                evidence_id
                for item in interpretations.values()
                for evidence_id in item.get("evidence_ids", [])
            ]
            + [
                evidence_id
                for item in coherence
                for evidence_id in item.get("evidence_ids", [])
            ]
        )
    )

    return {
        "configured": canonical,
        "auto_interpretations": interpretations,
        "ymyl": {
            "active": str(effective_profile or "").casefold() == "ymyl",
            "configured_risk_profile": canonical.get("risk_profile"),
            "configured_category": canonical.get("ymyl_category"),
            "effective_risk_profile": effective_profile,
            "effective_category": effective_category,
            "alignment_result": alignment,
            "alignment_label": ymyl_alignment_label(alignment),
            "coherence": coherence,
            "evidence_ids": evidence_ids,
        },
        "governance": {
            "configuration_is_canonical": True,
            "auto_interpretation_is_ai_inference": True,
            "affects_scoring_directly": False,
            "human_review_required": True,
            "must_not_infer_legal_or_regulatory_compliance": True,
        },
    }


def ymyl_prompt_directive(context: Mapping[str, Any]) -> str:
    ymyl = context.get("ymyl") if isinstance(context, Mapping) else None
    if not isinstance(ymyl, Mapping) or not bool(ymyl.get("active")):
        return (
            "Editorial risk context is contextual evidence only. Do not invent a YMYL "
            "classification or apply YMYL requirements when the supplied context does not establish it."
        )
    return (
        "The supplied editorial_risk_context establishes an active YMYL risk profile for this audit. "
        "Use it only when a supplied finding/evidence is materially related to trust, responsibility, "
        "claim support, decision risk, completeness or freshness. For each such gap, make the existing "
        "recommendation fields explicit about WHERE the gap is, WHAT is insufficient, HOW it should be "
        "improved, and HOW the correction must be verified. Do not invent credentials, reputation, "
        "professional review, policies, guarantees or hidden facts. Do not convert YMYL into a claim of "
        "legal/regulatory compliance. AUTO category interpretation remains AI inference rather than "
        "canonical operator configuration."
    )


__all__ = [
    "build_editorial_risk_context",
    "ymyl_alignment_label",
    "ymyl_prompt_directive",
]
