"""Persistence and deterministic cross-page aggregation for semantic coherence."""
from __future__ import annotations

import json
import re
import sqlite3
from statistics import mean
from typing import Any

from rasai.domain import new_id, utc_now
from rasai.persistence import AuditWorkspace
from rasai.property_semantic_profile_persistence import load_property_semantic_profile
from rasai.semantic_coherence import CoherenceResult, PROPERTY_COHERENCE_CRITERIA

_PAGE_TO_PROPERTY = {
    "SC-X02": "SC-P05",
    "SC-X03": "SC-P04",
    "SC-X04": "SC-P06",
    "SC-X05": "SC-P10",
    "SC-X06": "SC-P03",
}


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _initialize(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS semantic_coherence_assessments (
            assessment_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
            page_url TEXT NOT NULL,
            criterion_id TEXT NOT NULL,
            result TEXT NOT NULL,
            confidence REAL NOT NULL,
            declared_context TEXT NOT NULL,
            observed_context TEXT NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            reasoning_summary TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(audit_id,snapshot_id,criterion_id)
        );
        CREATE INDEX IF NOT EXISTS idx_semantic_coherence_audit
            ON semantic_coherence_assessments(audit_id,criterion_id,page_url);
        CREATE TABLE IF NOT EXISTS semantic_property_signals (
            observation_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
            page_url TEXT NOT NULL,
            signal_name TEXT NOT NULL,
            value TEXT,
            confidence REAL NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(audit_id,snapshot_id,signal_name)
        );
        CREATE INDEX IF NOT EXISTS idx_semantic_property_signal_audit
            ON semantic_property_signals(audit_id,signal_name,page_url);
        CREATE TABLE IF NOT EXISTS property_semantic_summaries (
            summary_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            criterion_id TEXT NOT NULL,
            result TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_ids_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            observation_count INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(audit_id,criterion_id)
        );
        """
    )


def persist_page_coherence(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    snapshot_id: str,
    page_url: str,
    response: Any,
) -> None:
    assessments = tuple(getattr(response, "coherence_assessments", ()) or ())
    signals = tuple(getattr(response, "property_signals", ()) or ())
    if not assessments and not signals:
        return
    created_at = str(utc_now())
    provider = str(getattr(response, "provider", "UNKNOWN") or "UNKNOWN")
    model = getattr(response, "model", None)
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            _initialize(connection)
            for item in assessments:
                connection.execute(
                    """INSERT INTO semantic_coherence_assessments(
                        assessment_id,audit_id,snapshot_id,page_url,criterion_id,result,confidence,
                        declared_context,observed_context,evidence_ids_json,reasoning_summary,
                        provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(audit_id,snapshot_id,criterion_id) DO NOTHING""",
                    (
                        new_id("SCA"), audit_id, snapshot_id, page_url, item.criterion_id,
                        item.result.value, float(item.confidence), item.declared_context,
                        item.observed_context, _dump(list(item.evidence_ids)), item.reasoning_summary,
                        provider, model, created_at,
                    ),
                )
            for item in signals:
                connection.execute(
                    """INSERT INTO semantic_property_signals(
                        observation_id,audit_id,snapshot_id,page_url,signal_name,value,confidence,
                        evidence_ids_json,provider,model,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(audit_id,snapshot_id,signal_name) DO NOTHING""",
                    (
                        new_id("SPS"), audit_id, snapshot_id, page_url, item.signal_name, item.value,
                        float(item.confidence), _dump(list(item.evidence_ids)), provider, model, created_at,
                    ),
                )
    finally:
        connection.close()


def _distinct_page_rows(connection: sqlite3.Connection, audit_id: str, criterion_id: str) -> list[sqlite3.Row]:
    # Multiple device snapshots may analyze the same page. Keep the highest-confidence
    # result per URL so cross-page aggregation does not accidentally become device-weighted.
    rows = connection.execute(
        """SELECT * FROM semantic_coherence_assessments
           WHERE audit_id=? AND criterion_id=?
           ORDER BY page_url,confidence DESC,created_at""",
        (audit_id, criterion_id),
    ).fetchall()
    chosen: dict[str, sqlite3.Row] = {}
    for row in rows:
        chosen.setdefault(str(row["page_url"]), row)
    return list(chosen.values())


def _aggregate_page_results(rows: list[sqlite3.Row]) -> tuple[CoherenceResult, float, tuple[str, ...], str]:
    if not rows:
        return CoherenceResult.NOT_DETERMINABLE, 0.0, (), "Nenhuma avaliação page-level disponível."
    results = [CoherenceResult(str(row["result"])) for row in rows]
    determinate = [item for item in results if item not in {CoherenceResult.NOT_DETERMINABLE, CoherenceResult.NOT_APPLICABLE}]
    if not determinate:
        result = CoherenceResult.NOT_DETERMINABLE
    elif CoherenceResult.INCOHERENT in determinate:
        result = CoherenceResult.INCOHERENT
    elif CoherenceResult.PARTIAL in determinate:
        result = CoherenceResult.PARTIAL
    elif len(determinate) < len(results):
        result = CoherenceResult.PARTIAL
    else:
        result = CoherenceResult.COHERENT
    confidence = mean(float(row["confidence"]) for row in rows)
    evidence: list[str] = []
    for row in rows:
        try:
            evidence.extend(json.loads(str(row["evidence_ids_json"])))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    counts = {state.value: results.count(state) for state in CoherenceResult if state in results}
    summary = f"Agregação determinística de {len(rows)} página(s): " + ", ".join(f"{key}={value}" for key, value in counts.items())
    return result, confidence, tuple(dict.fromkeys(evidence)), summary


def _normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _aggregate_identity(connection: sqlite3.Connection, audit_id: str) -> tuple[CoherenceResult, float, tuple[str, ...], str, int]:
    rows = connection.execute(
        """SELECT * FROM semantic_property_signals
           WHERE audit_id=? AND signal_name='organization_identity' AND value IS NOT NULL
           ORDER BY page_url,confidence DESC,created_at""",
        (audit_id,),
    ).fetchall()
    per_page: dict[str, sqlite3.Row] = {}
    for row in rows:
        if float(row["confidence"]) >= 0.60:
            per_page.setdefault(str(row["page_url"]), row)
    values = list(per_page.values())
    if len(values) < 2:
        return CoherenceResult.NOT_DETERMINABLE, 0.0, (), "São necessárias ao menos duas páginas com identidade observável.", len(values)
    labels = {_normalize_label(str(row["value"])) for row in values if str(row["value"] or "").strip()}
    result = CoherenceResult.COHERENT if len(labels) == 1 else CoherenceResult.PARTIAL
    confidence = mean(float(row["confidence"]) for row in values)
    evidence: list[str] = []
    for row in values:
        try:
            evidence.extend(json.loads(str(row["evidence_ids_json"])))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    if result is CoherenceResult.COHERENT:
        summary = f"A mesma identidade organizacional foi observada em {len(values)} página(s)."
    else:
        summary = (
            f"Foram observadas {len(labels)} formas de identidade organizacional em {len(values)} página(s); "
            "o estado permanece PARCIAL porque variações nominais podem ser legítimas."
        )
    return result, confidence, tuple(dict.fromkeys(evidence)), summary, len(values)


def aggregate_property_coherence(*, workspace: AuditWorkspace, audit_id: str) -> None:
    """Aggregate persisted page AI output without issuing another provider call."""
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            _initialize(connection)
            identity_result, identity_confidence, identity_evidence, identity_summary, identity_count = _aggregate_identity(connection, audit_id)
            rows_to_write = [
                ("SC-X01", identity_result, identity_confidence, identity_evidence, identity_summary, identity_count)
            ]
            for property_criterion, page_criterion in _PAGE_TO_PROPERTY.items():
                rows = _distinct_page_rows(connection, audit_id, page_criterion)
                result, confidence, evidence, summary = _aggregate_page_results(rows)
                rows_to_write.append((property_criterion, result, confidence, evidence, summary, len(rows)))

            created_at = str(utc_now())
            for criterion_id, result, confidence, evidence, summary, count in rows_to_write:
                description = PROPERTY_COHERENCE_CRITERIA[criterion_id]
                connection.execute(
                    """INSERT INTO property_semantic_summaries(
                        summary_id,audit_id,criterion_id,result,confidence,evidence_ids_json,
                        summary,observation_count,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(audit_id,criterion_id) DO UPDATE SET
                        result=excluded.result,confidence=excluded.confidence,
                        evidence_ids_json=excluded.evidence_ids_json,summary=excluded.summary,
                        observation_count=excluded.observation_count,created_at=excluded.created_at""",
                    (
                        new_id("SCS"), audit_id, criterion_id, result.value, float(confidence),
                        _dump(list(evidence)), f"{description}. {summary}", int(count), created_at,
                    ),
                )
    finally:
        connection.close()


def coherence_counts(*, workspace: AuditWorkspace, audit_id: str) -> dict[str, int]:
    connection = sqlite3.connect(workspace.database)
    try:
        _initialize(connection)
        rows = connection.execute(
            "SELECT result,COUNT(*) FROM semantic_coherence_assessments WHERE audit_id=? GROUP BY result",
            (audit_id,),
        ).fetchall()
        return {str(result): int(count) for result, count in rows}
    finally:
        connection.close()
