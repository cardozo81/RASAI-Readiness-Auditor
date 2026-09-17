"""Deterministic governance for CAT-09 client-facing recommendations.

The contract separates a recommendation's source from the action target. It never asks
AI to decide whether an action is safe to present. Every candidate is classified,
checked against persisted source facts and materialized as ACCEPTED or REJECTED before
CAT-09 renders the client action plan.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import re
import sqlite3
from typing import Any, Iterable, Mapping

CONTRACT_VERSION = "RECOMMENDATION-GOVERNANCE-001"

TARGET_SITE = "TARGET_SITE"
AUDITOR_INTERNAL = "AUDITOR_INTERNAL"
EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
ENVIRONMENTAL = "ENVIRONMENTAL"
INFORMATIONAL = "INFORMATIONAL"
TARGET_CLASSES = frozenset({TARGET_SITE, AUDITOR_INTERNAL, EXTERNAL_PROVIDER, ENVIRONMENTAL, INFORMATIONAL})

ACCEPTED = "ACCEPTED"
REJECTED = "REJECTED"

_INTERNAL_MARKERS = (
    "audit.db", "report-catalog", "rasai", "auditor", "orquestrador", "orchestrator",
    "provider fallback", "telemetria", "telemetry", "persistência interna", "internal persistence",
)
_JSONLD_EXISTING_RE = re.compile(r"\b(corrigir|ajustar|alterar|atualizar|reparar|fix|update|repair)\b.*\b(json-?ld|dados estruturados|structured data)\b.*\b(existente|existing|atual|current)\b", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _rows(connection: sqlite3.Connection, table: str, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, table) or "audit_id" not in _columns(connection, table):
        return []
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table} WHERE audit_id=?", (audit_id,)).fetchall()]


def _evidence_values(row: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for field in ("evidence_ids", "evidence_ids_json", "source_evidence_json"):
        raw = _load(row.get(field), [])
        if isinstance(raw, (list, tuple)):
            for item in raw:
                text = str(item).strip()
                if text and text not in values:
                    values.append(text)
    return tuple(values)


def _text(row: Mapping[str, Any]) -> str:
    fields = (
        "title", "description", "objective", "target_location", "proposed_text", "improvements",
        "recommendation", "rationale", "solution", "technical_detail", "verification",
    )
    parts: list[str] = []
    for field in fields:
        value = row.get(field)
        if value is None:
            continue
        parsed = _load(value, value)
        if isinstance(parsed, (list, tuple)):
            parts.extend(str(item) for item in parsed)
        elif isinstance(parsed, Mapping):
            parts.append(_dump(parsed))
        else:
            parts.append(str(parsed))
    return " ".join(parts).strip()


def _internal_target(text: str) -> bool:
    lowered = text.casefold()
    return any(marker in lowered for marker in _INTERNAL_MARKERS)


def _stable_id(audit_id: str, source_kind: str, source_id: str) -> str:
    digest = sha256(f"{audit_id}|{source_kind}|{source_id}".encode("utf-8")).hexdigest()[:24].upper()
    return "RGV-" + digest


def _jsonld_decision(row: Mapping[str, Any]) -> tuple[str, str | None, str | None]:
    existing = _load(row.get("existing_types"), [])
    existing_types = [str(item) for item in existing] if isinstance(existing, (list, tuple)) else []
    proposed = _load(row.get("proposed_json"), row.get("proposed_json"))
    text = _text(row)
    if not existing_types and _JSONLD_EXISTING_RE.search(text):
        return REJECTED, "JSONLD_ABSENT_EXISTING_CONFLICT", "JSONLD_EXISTENCE"
    if not existing_types and proposed in (None, "", {}, []) and str(row.get("status") or "").upper() not in {"NOT_APPLICABLE", "NO_CHANGE"}:
        return REJECTED, "JSONLD_ABSENT_WITHOUT_CREATION_PAYLOAD", "JSONLD_EXISTENCE"
    return ACCEPTED, None, None


def _request_target(row: Mapping[str, Any]) -> str:
    party = str(row.get("party_scope") or "UNKNOWN").upper()
    if party == "FIRST_PARTY":
        return TARGET_SITE
    if party == "THIRD_PARTY":
        return EXTERNAL_PROVIDER
    return INFORMATIONAL


def classify_candidate(source_kind: str, row: Mapping[str, Any]) -> tuple[str, str, str | None, str | None, str]:
    """Return target_class, decision, rejection_reason, conflict_group and rationale."""
    source = str(source_kind).upper()
    text = _text(row)
    if _internal_target(text):
        return AUDITOR_INTERNAL, REJECTED, "AUDITOR_INTERNAL_NOT_CLIENT_ACTION", "TARGET_SCOPE", "A ação trata do auditor/RASAi e não do ativo auditado."
    if source == "REQUEST_REMEDIATION":
        target = _request_target(row)
        if target == INFORMATIONAL:
            return target, REJECTED, "UNKNOWN_OWNERSHIP_INFORMATIONAL_ONLY", "TARGET_SCOPE", "A evidência não permite atribuir ownership da correção."
        return target, ACCEPTED, None, None, "Ownership derivado deterministicamente do escopo first-party/third-party persistido."
    if source == "JSONLD":
        decision, reason, conflict = _jsonld_decision(row)
        rationale = "A sugestão é compatível com a presença/ausência de JSON-LD observada." if decision == ACCEPTED else "A sugestão pressupõe estado de JSON-LD incompatível com a evidência persistida."
        return TARGET_SITE, decision, reason, conflict, rationale
    if source == "M24_DISCOVERY":
        return INFORMATIONAL, ACCEPTED, None, None, "Orientação técnica contextual; requer decisão humana antes de implementação."
    if source in {"DETERMINISTIC", "CONTENT_AI", "DEEP_ANALYSIS"}:
        return TARGET_SITE, ACCEPTED, None, None, "A origem descreve uma mudança no ativo auditado e mantém vínculo com o finding/evidência de origem."
    return INFORMATIONAL, REJECTED, "UNCLASSIFIED_RECOMMENDATION_SOURCE", "TARGET_SCOPE", "A origem não possui contrato de ownership reconhecido."


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS recommendation_governance (
            governance_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_catalog TEXT,
            title TEXT NOT NULL,
            target_class TEXT NOT NULL,
            decision TEXT NOT NULL,
            rejection_reason TEXT,
            conflict_group TEXT,
            source_evidence_json TEXT NOT NULL,
            rationale TEXT NOT NULL,
            contract_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(audit_id, source_kind, source_id)
        );
        CREATE INDEX IF NOT EXISTS idx_recommendation_governance_audit
            ON recommendation_governance(audit_id,decision,target_class,source_kind);
        """
    )


def _candidate(source_kind: str, source_id: Any, title: Any, row: Mapping[str, Any], *, source_catalog: str | None = None, evidence: Iterable[str] = ()) -> dict[str, Any]:
    data = dict(row)
    ids = list(_evidence_values(data))
    for value in evidence:
        text = str(value).strip()
        if text and text not in ids:
            ids.append(text)
    return {
        "source_kind": source_kind,
        "source_id": str(source_id),
        "source_catalog": source_catalog,
        "title": str(title or "Recomendação"),
        "row": data,
        "evidence_ids": tuple(ids),
    }


def collect_candidates(connection: sqlite3.Connection, audit_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    findings = {str(row.get("finding_id")): row for row in _rows(connection, "findings", audit_id)}
    roots = {str(row.get("finding_id")): row for row in _rows(connection, "root_cause_analyses", audit_id)}
    for row in _rows(connection, "recommendations", audit_id):
        finding_id = str(row.get("finding_id") or "")
        root = roots.get(finding_id, {})
        merged = {**root, **row}
        evidence = _evidence_values(findings.get(finding_id, {})) + _evidence_values(root)
        candidates.append(_candidate("DETERMINISTIC", row.get("recommendation_id"), row.get("title"), merged, source_catalog="CAT-09", evidence=evidence))

    for row in _rows(connection, "content_remediation_suggestions", audit_id):
        candidates.append(_candidate("CONTENT_AI", row.get("suggestion_id"), row.get("objective"), row, source_catalog="CAT-03", evidence=_evidence_values(row)))

    for row in _rows(connection, "jsonld_remediation_suggestions", audit_id):
        candidates.append(_candidate("JSONLD", row.get("suggestion_id"), "Dados estruturados / JSON-LD", row, source_catalog="CAT-03", evidence=_evidence_values(row)))

    for row in _rows(connection, "improvement_intelligence_recommendations", audit_id):
        candidates.append(_candidate("DEEP_ANALYSIS", row.get("recommendation_id"), row.get("title"), row, source_catalog="CAT-08", evidence=_evidence_values(row)))

    request_groups = {str(row.get("group_id")): row for row in _rows(connection, "request_remediation_groups", audit_id)}
    request_ai = {str(row.get("group_id")): row for row in _rows(connection, "request_remediation_ai", audit_id)}
    request_evidence = _rows(connection, "request_remediation_evidence", audit_id)
    ev_by_group: dict[str, list[str]] = {}
    for row in request_evidence:
        group_id = str(row.get("group_id") or "")
        evidence_id = str(row.get("evidence_id") or "").strip()
        if group_id and evidence_id:
            ev_by_group.setdefault(group_id, []).append(evidence_id)
    for group_id, group in request_groups.items():
        ai = request_ai.get(group_id, {})
        merged = {**group, **ai}
        title = ai.get("title") or group.get("title") or "Falha de requisição"
        candidates.append(_candidate("REQUEST_REMEDIATION", group_id, title, merged, source_catalog="CAT-06/CAT-07", evidence=ev_by_group.get(group_id, ())))

    return candidates


def evaluate_recommendations(database: Any, audit_id: str) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        _ensure_schema(connection)
        candidates = collect_candidates(connection, audit_id)
        now = _now()
        current_keys = {(str(candidate["source_kind"]), str(candidate["source_id"])) for candidate in candidates}
        with connection:
            for candidate in candidates:
                target, decision, reason, conflict, rationale = classify_candidate(candidate["source_kind"], candidate["row"])
                if target not in TARGET_CLASSES:
                    raise ValueError(f"invalid recommendation target_class: {target}")
                governance_id = _stable_id(audit_id, candidate["source_kind"], candidate["source_id"])
                connection.execute(
                    """INSERT INTO recommendation_governance(
                        governance_id,audit_id,source_kind,source_id,source_catalog,title,target_class,decision,
                        rejection_reason,conflict_group,source_evidence_json,rationale,contract_version,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(audit_id,source_kind,source_id) DO UPDATE SET
                        source_catalog=excluded.source_catalog,title=excluded.title,target_class=excluded.target_class,
                        decision=excluded.decision,rejection_reason=excluded.rejection_reason,
                        conflict_group=excluded.conflict_group,source_evidence_json=excluded.source_evidence_json,
                        rationale=excluded.rationale,contract_version=excluded.contract_version,updated_at=excluded.updated_at""",
                    (
                        governance_id,audit_id,candidate["source_kind"],candidate["source_id"],candidate["source_catalog"],
                        candidate["title"],target,decision,reason,conflict,_dump(candidate["evidence_ids"]),rationale,
                        CONTRACT_VERSION,now,now,
                    ),
                )
            existing = connection.execute("SELECT source_kind,source_id FROM recommendation_governance WHERE audit_id=?", (audit_id,)).fetchall()
            for row in existing:
                key = (str(row["source_kind"]), str(row["source_id"]))
                if key not in current_keys:
                    connection.execute("DELETE FROM recommendation_governance WHERE audit_id=? AND source_kind=? AND source_id=?", (audit_id, *key))
        rows = connection.execute(
            "SELECT * FROM recommendation_governance WHERE audit_id=? ORDER BY decision,target_class,source_kind,title,source_id",
            (audit_id,),
        ).fetchall()
        return tuple(dict(row) for row in rows)
    finally:
        connection.close()


def list_governance(database: Any, audit_id: str, *, decision: str | None = None) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "recommendation_governance"):
            return ()
        if decision:
            rows = connection.execute(
                "SELECT * FROM recommendation_governance WHERE audit_id=? AND decision=? ORDER BY target_class,source_kind,title",
                (audit_id, decision),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM recommendation_governance WHERE audit_id=? ORDER BY decision,target_class,source_kind,title",
                (audit_id,),
            ).fetchall()
        return tuple(dict(row) for row in rows)
    finally:
        connection.close()


__all__ = [
    "CONTRACT_VERSION", "TARGET_SITE", "AUDITOR_INTERNAL", "EXTERNAL_PROVIDER", "ENVIRONMENTAL", "INFORMATIONAL",
    "ACCEPTED", "REJECTED", "classify_candidate", "collect_candidates", "evaluate_recommendations", "list_governance",
]
