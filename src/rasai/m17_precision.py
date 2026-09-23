"""M17 precise, evidence-backed remediation projection over M16 root causes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import sqlite3
from typing import Any, Iterable

from rasai.domain import utc_now
from rasai.m16_root_cause import M16Persistence, RootCauseAnalysis
from rasai.persistence import AuditWorkspace
from rasai.remediation import recipe_for


@dataclass(frozen=True, slots=True)
class RootCausePrecision:
    finding_id: str
    rule_id: str
    reason_code: str | None
    precise_cause_summary: str
    observed_element_status: str
    observed_selector: str | None
    target_selector: str | None
    target_element: str | None
    target_location: str | None
    materialized_at: datetime


_REASON_SUMMARY: dict[tuple[str, str], str] = {
    ("BR-GEO-013", "CANONICAL_ABSENT"): (
        "Nenhuma declaração <link rel=\"canonical\"> foi encontrada no documento avaliado."
    ),
    ("BR-GEO-013", "CANONICAL_CONFLICT"): (
        "Foram observadas declarações canonical conflitantes no documento avaliado."
    ),
    ("BR-GEO-013", "CANONICAL_INVALID"): (
        "A declaração canonical observada não possui uma forma tecnicamente válida."
    ),
    ("BR-GEO-014", "CANONICAL_TARGET_INVALID"): (
        "O destino canonical observado não satisfez os critérios técnicos avaliados."
    ),
    ("BR-GEO-028", "TITLE_ABSENT"): "O documento avaliado não possui elemento <title> observável.",
    ("BR-GEO-029", "HEADING_HIERARCHY"): (
        "A sequência de headings observada não representa uma hierarquia semântica suficientemente compreensível."
    ),
    ("BR-GEO-034", "STRUCTURED_DATA_INVALID_JSON"): (
        "Pelo menos um bloco script[type=\"application/ld+json\"] contém JSON não interpretável."
    ),
    ("BR-GEO-051", "EXACT_DUPLICATE_MAIN_CONTENT"): (
        "O conteúdo principal extraído desta página é exatamente igual ao conteúdo principal extraído de outra página do universo auditado."
    ),
    ("BR-GEO-051", "NEAR_DUPLICATE_MAIN_CONTENT"): (
        "O conteúdo principal extraído desta página atingiu o limiar persistido de similaridade para near-duplicate dentro do universo auditado."
    ),
}

_TARGET_SELECTOR: dict[str, str] = {
    "BR-GEO-011": 'head > meta[name="robots"]',
    "BR-GEO-012": 'head > meta[name="robots"]',
    "BR-GEO-013": 'head > link[rel="canonical"]',
    "BR-GEO-014": 'head > link[rel="canonical"]',
    "BR-GEO-015": 'head > meta[name="robots"], head > link[rel="canonical"]',
    "BR-GEO-025": "main",
    "BR-GEO-026": "main",
    "BR-GEO-027": "main",
    "BR-GEO-028": "head > title",
    "BR-GEO-029": "h1, h2, h3, h4, h5, h6",
    "BR-GEO-030": "main",
    "BR-GEO-031": "main",
    "BR-GEO-032": "main",
    "BR-GEO-033": "main",
    "BR-GEO-034": 'script[type="application/ld+json"]',
    "BR-GEO-035": 'script[type="application/ld+json"]',
    "BR-GEO-036": 'script[type="application/ld+json"]',
    "BR-GEO-037": 'script[type="application/ld+json"]',
    "BR-GEO-038": "main",
    "BR-GEO-039": "main",
    "BR-GEO-040": "main",
    "BR-GEO-041": "main",
    "BR-GEO-042": "main",
    "BR-GEO-043": "main",
    "BR-GEO-044": "main",
    "BR-GEO-045": "main",
    "BR-GEO-046": "main",
    "BR-GEO-047": "main",
    "BR-GEO-048": "main",
    "BR-GEO-049": "main",
}


class M17PrecisionPersistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self._connection = sqlite3.connect(workspace.database)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "M17PrecisionPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS root_cause_precision (
                    finding_id TEXT PRIMARY KEY REFERENCES findings(finding_id) ON DELETE CASCADE,
                    rule_id TEXT NOT NULL,
                    reason_code TEXT,
                    precise_cause_summary TEXT NOT NULL,
                    observed_element_status TEXT NOT NULL,
                    observed_selector TEXT,
                    target_selector TEXT,
                    target_element TEXT,
                    target_location TEXT,
                    materialized_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_root_cause_precision_rule
                    ON root_cause_precision(rule_id);
                """
            )

    def upsert(self, item: RootCausePrecision) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO root_cause_precision(
                    finding_id, rule_id, reason_code, precise_cause_summary,
                    observed_element_status, observed_selector, target_selector,
                    target_element, target_location, materialized_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(finding_id) DO UPDATE SET
                    rule_id=excluded.rule_id,
                    reason_code=excluded.reason_code,
                    precise_cause_summary=excluded.precise_cause_summary,
                    observed_element_status=excluded.observed_element_status,
                    observed_selector=excluded.observed_selector,
                    target_selector=excluded.target_selector,
                    target_element=excluded.target_element,
                    target_location=excluded.target_location,
                    materialized_at=excluded.materialized_at
                """,
                (
                    item.finding_id,
                    item.rule_id,
                    item.reason_code,
                    item.precise_cause_summary,
                    item.observed_element_status,
                    item.observed_selector,
                    item.target_selector,
                    item.target_element,
                    item.target_location,
                    item.materialized_at.isoformat(),
                ),
            )

    def get(self, finding_id: str) -> RootCausePrecision | None:
        row = self._connection.execute(
            "SELECT * FROM root_cause_precision WHERE finding_id=?", (finding_id,)
        ).fetchone()
        return None if row is None else _map_precision(row)

    def list_for_audit(self, audit_id: str) -> tuple[RootCausePrecision, ...]:
        rows = self._connection.execute(
            """
            SELECT rcp.* FROM root_cause_precision rcp
            JOIN findings f ON f.finding_id=rcp.finding_id
            WHERE f.audit_id=? ORDER BY rcp.rule_id, rcp.finding_id
            """,
            (audit_id,),
        ).fetchall()
        return tuple(_map_precision(row) for row in rows)


def materialize_m17_precision(*, audit_id: str, workspace: AuditWorkspace) -> int:
    """Materialize precise reason/target metadata without changing M16 records."""

    with M16Persistence(workspace) as m16:
        analyses = m16.list_for_audit(audit_id)

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        with M17PrecisionPersistence(workspace) as store:
            for analysis in analyses:
                payloads = _evidence_payloads(connection, analysis.evidence_basis)
                item = derive_precision(analysis=analysis, evidence_payloads=payloads)
                store.upsert(item)
        return len(analyses)
    finally:
        connection.close()


def derive_precision(
    *,
    analysis: RootCauseAnalysis,
    evidence_payloads: Iterable[Any] = (),
) -> RootCausePrecision:
    reason = _reason_code(analysis.observed_value, evidence_payloads)
    if reason is None:
        reason = _derived_rule_reason(analysis.rule_id, analysis.observed_value)
    status = _observed_element_status(analysis, reason)
    observed_selector = _observed_selector(analysis, status)
    recipe = recipe_for(analysis.rule_id)
    target_selector = _TARGET_SELECTOR.get(analysis.rule_id)
    precise = _precise_cause(analysis, reason, status)
    return RootCausePrecision(
        finding_id=analysis.finding_id,
        rule_id=analysis.rule_id,
        reason_code=reason,
        precise_cause_summary=precise,
        observed_element_status=status,
        observed_selector=observed_selector,
        target_selector=target_selector,
        target_element=recipe.element,
        target_location=recipe.location,
        materialized_at=utc_now(),
    )


def _evidence_payloads(connection: sqlite3.Connection, ids: tuple[str, ...]) -> tuple[Any, ...]:
    if not ids:
        return ()
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(
        f"SELECT observed_value FROM evidence WHERE evidence_id IN ({placeholders}) ORDER BY evidence_id",
        ids,
    ).fetchall()
    return tuple(_json_value(row["observed_value"]) for row in rows)


def _reason_code(observed: Any, payloads: Iterable[Any]) -> str | None:
    candidates = [observed, *payloads]
    for value in candidates:
        reason = _reason_from_value(value)
        if reason:
            return reason
    return None


def _reason_from_value(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    direct = value.get("reason")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    observed = value.get("observed")
    if isinstance(observed, dict):
        nested = observed.get("reason")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    checks = value.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            candidate = check.get("reason")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    provider = value.get("provider_observed")
    if isinstance(provider, dict):
        candidate = provider.get("reason") or provider.get("code")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _derived_rule_reason(rule_id: str, observed: Any) -> str | None:
    if rule_id != "BR-GEO-051" or not isinstance(observed, dict):
        return None
    matches = observed.get("matches")
    if not isinstance(matches, list) or not matches:
        return None
    similarities = [
        float(match["similarity"])
        for match in matches
        if isinstance(match, dict) and isinstance(match.get("similarity"), (int, float))
    ]
    if not similarities:
        return None
    if any(similarity >= 1.0 for similarity in similarities):
        return "EXACT_DUPLICATE_MAIN_CONTENT"
    threshold = observed.get("near_duplicate_jaccard_threshold")
    if isinstance(threshold, (int, float)) and any(similarity >= float(threshold) for similarity in similarities):
        return "NEAR_DUPLICATE_MAIN_CONTENT"
    return None


def _observed_element_status(analysis: RootCauseAnalysis, reason: str | None) -> str:
    if analysis.affected_elements:
        if all(item.relation == "CONTEXT_REGION" for item in analysis.affected_elements):
            return "CONTEXT_ONLY"
        return "PRESENT"
    if analysis.affected_scope in {"DOMAIN_RESOURCE", "PAGE_RESOURCE"}:
        return "NOT_APPLICABLE"
    if analysis.rule_id == "BR-GEO-051":
        # Cross-page duplicate evidence applies to an extracted document/content
        # representation, not to one safely attributable DOM node.
        return "NOT_APPLICABLE"
    upper = (reason or "").upper()
    if any(token in upper for token in ("ABSENT", "MISSING", "NOT_FOUND")):
        return "ABSENT"
    observed = analysis.observed_value
    if analysis.rule_id == "BR-GEO-013" and isinstance(observed, dict) and observed.get("canonicals") == []:
        return "ABSENT"
    if analysis.rule_id == "BR-GEO-028" and isinstance(observed, dict) and observed.get("title") in {None, ""}:
        return "ABSENT"
    return "NOT_DETERMINED"


def _observed_selector(analysis: RootCauseAnalysis, status: str) -> str | None:
    selectors = tuple(
        dict.fromkeys(item.selector for item in analysis.affected_elements if item.selector)
    )
    if status in {"ABSENT", "NOT_APPLICABLE"}:
        return None
    if not selectors:
        return None
    if len(selectors) == 1:
        return selectors[0]
    return ", ".join(selectors)


def _precise_cause(
    analysis: RootCauseAnalysis,
    reason: str | None,
    status: str,
) -> str:
    if analysis.rule_id == "BR-GEO-051" and reason:
        duplicate = _duplicate_cause_summary(analysis.observed_value, reason)
        if duplicate:
            return duplicate
    if reason:
        mapped = _REASON_SUMMARY.get((analysis.rule_id, reason.upper()))
        if mapped:
            return mapped
    if analysis.rule_id == "BR-GEO-013" and status == "ABSENT":
        return "Nenhuma declaração <link rel=\"canonical\"> foi encontrada no documento avaliado."
    base = analysis.cause_summary.strip()
    if reason:
        return f"{base} Motivo técnico persistido: {reason}."
    return base


def _duplicate_cause_summary(observed: Any, reason: str) -> str | None:
    if not isinstance(observed, dict):
        return _REASON_SUMMARY.get(("BR-GEO-051", reason.upper()))
    matches = observed.get("matches")
    if not isinstance(matches, list) or not matches:
        return _REASON_SUMMARY.get(("BR-GEO-051", reason.upper()))
    similarities = [
        float(match["similarity"])
        for match in matches
        if isinstance(match, dict) and isinstance(match.get("similarity"), (int, float))
    ]
    count = len(similarities)
    if reason.upper() == "EXACT_DUPLICATE_MAIN_CONTENT":
        exact_count = sum(similarity >= 1.0 for similarity in similarities)
        return (
            "O conteúdo principal extraído desta página é exatamente igual ao de "
            f"{exact_count} outra(s) página(s) do universo auditado (similaridade 1.0)."
        )
    if reason.upper() == "NEAR_DUPLICATE_MAIN_CONTENT":
        threshold = observed.get("near_duplicate_jaccard_threshold")
        threshold_text = f"{float(threshold):.2f}" if isinstance(threshold, (int, float)) else "persistido"
        return (
            f"O conteúdo principal extraído desta página possui {count} correspondência(s) que atingem "
            f"o limiar de near-duplicate {threshold_text} dentro do universo auditado."
        )
    return None


def _json_value(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(value)


def _map_precision(row: sqlite3.Row) -> RootCausePrecision:
    return RootCausePrecision(
        finding_id=str(row["finding_id"]),
        rule_id=str(row["rule_id"]),
        reason_code=str(row["reason_code"]) if row["reason_code"] else None,
        precise_cause_summary=str(row["precise_cause_summary"]),
        observed_element_status=str(row["observed_element_status"]),
        observed_selector=str(row["observed_selector"]) if row["observed_selector"] else None,
        target_selector=str(row["target_selector"]) if row["target_selector"] else None,
        target_element=str(row["target_element"]) if row["target_element"] else None,
        target_location=str(row["target_location"]) if row["target_location"] else None,
        materialized_at=datetime.fromisoformat(row["materialized_at"]),
    )