"""Evidence-bound strategic synthesis over already-persisted catalog data.

Directed Analysis is not a catalog and does not collect new evidence. It builds a compact
strategic context from persisted catalog-owned facts/remediations, optionally asks the
configured AI provider to correlate only pre-existing action IDs, validates that output,
then persists the structured strategy for read-only report projection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re
import sqlite3
import time
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError

from rasai.ai_exchange_log import AiExchangeRecorder, instrument_provider_transport, persist_ai_exchange_log
from rasai.ai_resilience import DECISION_RETRY, DECISION_STOP, DECISION_SUCCESS, DECISION_SUCCESS_AFTER_RETRY, retry_policy
from rasai.catalog_report_contract import CATALOG_PAGE_BY_ID, CATALOG_REPORT_CONTRACT_VERSION
from rasai.catalog_report_model import _DOMAIN_CATALOG, _load_data
from rasai import catalog_report_page as catalog_page
from rasai.domain import new_id
from rasai.improvement_intelligence import (
    DEFAULT_DOMAINS,
    ImprovementConfig,
    _build_provider,
    _persist_attempt,
    _provider_extract,
    _provider_native_error,
    _provider_payload,
    _provider_usage,
    _target_context,
    configured_analysis_language,
)
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ResponsesSemanticProvider,
    _diagnostic_from_http as _core_diagnostic_from_http,
    estimate_cost,
)
from rasai.persistence import AuditWorkspace
from rasai.provider_extensions import _diagnostic_from_http as _extension_diagnostic_from_http
from rasai.recommendation_governance import ACCEPTED, collect_candidates, evaluate_recommendations
from rasai.secret_safety import redact_value


CONTRACT_VERSION = "DIRECTED-ANALYSIS-001"
PROMPT_VERSION = "DIRECTED-ANALYSIS-PROMPT-001"
MAX_ACTIONS = 60

_DIMENSIONS = (
    "APDEX_NAVIGATION",
    "APDEX_EXPERIENCE",
    "PERFORMANCE",
    "ACCESSIBILITY",
    "SEO",
    "GEO_SEARCH_AI",
    "BEST_PRACTICES",
    "CONTENT",
    "SEMANTICS",
    "STRUCTURED_DATA",
    "YMYL",
    "SECURITY",
    "VULNERABILITIES",
    "HTML_CSS",
    "CRAWLABILITY",
    "INDEXABILITY",
    "EXPERIENCE",
    "COMPETITIVE_INTELLIGENCE",
    "TECHNICAL_QUALITY",
)
_GAIN = {"LOW", "MEDIUM", "HIGH"}
_LEVEL = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
_CATALOG_SECTIONS = frozenset({"summary","scope","config","execution","results","evidence","analysis","remediation","technical"})


@dataclass(frozen=True, slots=True)
class DirectedAnalysisResult:
    status: str
    analysis_run_id: str | None
    actions_count: int
    ai_actions_count: int
    provider: str | None = None
    model: str | None = None
    reason: str | None = None
    reused: bool = False


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
    return [dict(row) for row in connection.execute(
        f"SELECT * FROM {table} WHERE audit_id=? ORDER BY rowid", (audit_id,)
    ).fetchall()]


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS directed_analysis_runs (
            analysis_run_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL UNIQUE REFERENCES audits(audit_id) ON DELETE CASCADE,
            contract_version TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            status TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            reasoning TEXT,
            analysis_language TEXT,
            input_context_hash TEXT NOT NULL,
            catalog_versions_json TEXT NOT NULL,
            source_evidence_json TEXT NOT NULL,
            source_remediations_json TEXT NOT NULL,
            strategic_summary_json TEXT NOT NULL,
            dimensions_json TEXT NOT NULL,
            objectives_json TEXT NOT NULL,
            roadmap_json TEXT NOT NULL,
            limitations_json TEXT NOT NULL,
            context_json TEXT NOT NULL,
            raw_ai_response_json TEXT,
            actions_count INTEGER NOT NULL,
            ai_actions_count INTEGER NOT NULL,
            reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS directed_analysis_actions (
            action_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
            source_kind TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT NOT NULL,
            reason TEXT NOT NULL,
            primary_objective TEXT,
            affected_dimensions_json TEXT NOT NULL,
            priority TEXT,
            effort TEXT,
            confidence TEXT,
            confidence_rationale TEXT,
            dependencies_json TEXT NOT NULL,
            implementation_guidance_json TEXT NOT NULL,
            validation_steps_json TEXT NOT NULL,
            source_refs_json TEXT NOT NULL,
            evidence_refs_json TEXT NOT NULL,
            remediation_refs_json TEXT NOT NULL,
            analysis_state TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_directed_actions_audit
            ON directed_analysis_actions(audit_id,priority,effort,action_id);
        """
    )


def _stable_action_id(audit_id: str, source_kind: str, source_id: str) -> str:
    digest = sha256(f"{audit_id}|{source_kind}|{source_id}".encode("utf-8")).hexdigest()[:16].upper()
    return "ACT-" + digest


def _anchor_token(value: Any, fallback: str) -> str:
    token = re.sub(r"[^a-z0-9_-]+", "-", str(value or fallback).strip().casefold()).strip("-")
    return token or fallback


def _exact_ref(
    catalog_id: str,
    section_id: str,
    *,
    topic: str,
    ref_id: str,
    anchor_id: str,
) -> dict[str, Any]:
    ref = _catalog_ref(catalog_id, section_id, topic=topic, ref_id=ref_id)
    page = CATALOG_PAGE_BY_ID[catalog_id]
    return {**ref, "anchor_id": anchor_id, "href": f"{page.filename}#{anchor_id}"}


def _catalog_ref(catalog_id: str, section_id: str, *, topic: str, ref_id: str | None = None) -> dict[str, Any]:
    page = CATALOG_PAGE_BY_ID.get(catalog_id)
    if page is None or section_id not in _CATALOG_SECTIONS:
        raise ValueError(f"invalid catalog reference: {catalog_id}#{section_id}")
    return {
        "catalog_id": catalog_id,
        "section_id": section_id,
        "topic": topic,
        "reference_id": ref_id,
        "href": f"{page.filename}#{section_id}",
    }


def _domain_catalog(row: Mapping[str, Any]) -> str | None:
    domain = str(row.get("domain") or "").upper().replace("-", "_").replace(" ", "_")
    return _DOMAIN_CATALOG.get(domain)


def _catalogs_for_candidate(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    row = candidate.get("row") if isinstance(candidate.get("row"), Mapping) else {}
    values: list[str] = []
    domain_catalog = _domain_catalog(row)
    if domain_catalog:
        values.append(domain_catalog)
    raw = str(candidate.get("source_catalog") or "")
    for token in raw.replace(",", "/").split("/"):
        token = token.strip().upper()
        if token in CATALOG_PAGE_BY_ID and token not in values:
            values.append(token)
    if not values:
        category = str(row.get("category") or "").upper()
        if any(key in category for key in ("CRAWL","DISCOVERY","INDEX","TECHNICAL")):
            values.append("CAT-01")
        elif "ACCESS" in category:
            values.append("CAT-02")
        elif any(key in category for key in ("CONTENT","SEMANTIC","STRUCTURED","ENTITY")):
            values.append("CAT-03")
        elif any(key in category for key in ("PERFORMANCE","WEB_VITAL")):
            values.append("CAT-04")
    return tuple(values)


def _dimension_baseline(candidate: Mapping[str, Any]) -> list[dict[str, str]]:
    row = candidate.get("row") if isinstance(candidate.get("row"), Mapping) else {}
    domain = str(row.get("domain") or "").upper()
    mapping = {
        "TECHNICAL_HTML": ("HTML_CSS","CRAWLABILITY","INDEXABILITY","SEO","GEO_SEARCH_AI"),
        "SEMANTICS_STRUCTURE": ("SEMANTICS","STRUCTURED_DATA","SEO","GEO_SEARCH_AI"),
        "CONTENT": ("CONTENT","SEO","GEO_SEARCH_AI","YMYL"),
        "SEARCH_RANKING": ("SEO","GEO_SEARCH_AI","COMPETITIVE_INTELLIGENCE"),
        "FILES_DISCOVERY": ("CRAWLABILITY","INDEXABILITY","SEO","GEO_SEARCH_AI"),
        "PERFORMANCE": ("PERFORMANCE","APDEX_NAVIGATION","APDEX_EXPERIENCE","EXPERIENCE","SEO","BEST_PRACTICES"),
        "ACCESSIBILITY": ("ACCESSIBILITY","EXPERIENCE","BEST_PRACTICES"),
        "BEST_PRACTICES": ("BEST_PRACTICES","TECHNICAL_QUALITY"),
        "SECURITY": ("SECURITY","VULNERABILITIES","BEST_PRACTICES"),
        "AI_ACCESS": ("GEO_SEARCH_AI","SEMANTICS","CONTENT"),
    }
    dims = list(mapping.get(domain, ()))
    source_kind = str(candidate.get("source_kind") or "").upper()
    if source_kind == "REQUEST_REMEDIATION":
        for value in ("APDEX_NAVIGATION","APDEX_EXPERIENCE","PERFORMANCE","EXPERIENCE"):
            if value not in dims:
                dims.append(value)
    if source_kind == "JSONLD":
        for value in ("STRUCTURED_DATA","SEMANTICS","SEO","GEO_SEARCH_AI"):
            if value not in dims:
                dims.append(value)
    return [{"dimension": value, "expected_gain": "MEDIUM"} for value in dims]


def _first_text(row: Mapping[str, Any], fields: Sequence[str], default: str = "") -> str:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            if isinstance(value, (dict, list, tuple)):
                return _dump(value)[:4000]
            return str(value)[:4000]
    return default


def _confidence_label(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).upper()
    if text in _CONFIDENCE:
        return text
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return "HIGH" if number >= 0.8 else "MEDIUM" if number >= 0.55 else "LOW"


def _existing_evidence_refs(
    connection: sqlite3.Connection,
    audit_id: str,
    evidence_ids: Iterable[str],
    catalogs: Sequence[str],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    evidence_rows = {}
    if _table_exists(connection, "evidence"):
        cols = _columns(connection, "evidence")
        id_col = "evidence_id" if "evidence_id" in cols else None
        if id_col:
            for row in connection.execute("SELECT * FROM evidence WHERE audit_id=?", (audit_id,)).fetchall():
                evidence_rows[str(row[id_col])] = dict(row)
    target_catalog = catalogs[0] if catalogs else "CAT-01"
    for evidence_id in evidence_ids:
        token = str(evidence_id).strip()
        if not token or token not in evidence_rows:
            continue
        refs.append({
            **_catalog_ref(target_catalog, "evidence", topic="Evidência persistida", ref_id=token),
            "evidence_id": token,
            "kind": "evidence",
        })
    return refs


def _action_from_candidate(
    connection: sqlite3.Connection,
    audit_id: str,
    candidate: Mapping[str, Any],
    governance: Mapping[str, Any],
) -> dict[str, Any]:
    row = candidate.get("row") if isinstance(candidate.get("row"), Mapping) else {}
    source_kind = str(candidate.get("source_kind") or "")
    source_id = str(candidate.get("source_id") or "")
    catalogs = _catalogs_for_candidate(candidate)
    title = str(governance.get("title") or candidate.get("title") or "Ação")
    reason = _first_text(
        row,
        ("rationale","description","observation","reason","objective","technical_detail"),
        str(governance.get("rationale") or ""),
    )
    source_refs = [
        _catalog_ref(cat, "results", topic=title, ref_id=source_id)
        for cat in catalogs
        if cat in CATALOG_PAGE_BY_ID
    ]
    if source_kind == "DETERMINISTIC" and "CAT-09" in CATALOG_PAGE_BY_ID:
        source_refs = [
            _exact_ref(
                "CAT-09","results",topic=title,ref_id=source_id,
                anchor_id="rem-det-"+_anchor_token(source_id,"recommendation"),
            )
        ]
    if source_kind == "DEEP_ANALYSIS" and row.get("finding_id") and "CAT-08" in CATALOG_PAGE_BY_ID:
        finding_id = str(row.get("finding_id"))
        source_refs = [
            _exact_ref(
                "CAT-08","results",topic=title,ref_id=finding_id,
                anchor_id="improvement-"+_anchor_token(finding_id,"finding"),
            )
        ]
    if not source_refs and "CAT-09" in CATALOG_PAGE_BY_ID:
        source_refs = [_catalog_ref("CAT-09","results",topic=title,ref_id=source_id)]

    evidence_ids = _load(governance.get("source_evidence_json"), [])
    evidence_ids = [str(v) for v in evidence_ids] if isinstance(evidence_ids, (list, tuple)) else []
    evidence_refs = _existing_evidence_refs(connection, audit_id, evidence_ids, catalogs)
    # The persisted source record itself is always a validated evidence-bound reference.
    evidence_refs.insert(0, {
        **(source_refs[0] if source_refs else _catalog_ref("CAT-09","results",topic=title,ref_id=source_id)),
        "evidence_id": f"{source_kind}:{source_id}",
        "kind": "source_record",
    })

    remediation_refs: list[dict[str, Any]] = []
    remediation_prefix = {
        "DETERMINISTIC": "rem-det",
        "CONTENT_AI": "rem-content",
        "JSONLD": "rem-jsonld",
        "DEEP_ANALYSIS": "rem-deep",
        "REQUEST_REMEDIATION": "request-remediation",
    }.get(source_kind)
    if remediation_prefix and "CAT-09" in CATALOG_PAGE_BY_ID:
        remediation_refs = [
            _exact_ref(
                "CAT-09","results",topic=title,ref_id=source_id,
                anchor_id=remediation_prefix+"-"+_anchor_token(source_id,"remediation"),
            )
        ]

    guidance = _first_text(
        row,
        ("recommendation","solution","proposed_text","improvements","technical_detail","correction"),
        "",
    )
    verification = _first_text(row, ("verification","validation","acceptance_criteria"), "")
    effort = str(row.get("effort") or "").upper() or None
    priority = str(row.get("priority") or "").upper() or None
    confidence = _confidence_label(row.get("confidence"))
    return {
        "action_id": _stable_action_id(audit_id, source_kind, source_id),
        "source_kind": source_kind,
        "source_id": source_id,
        "title": title[:500],
        "reason": reason[:4000] or str(governance.get("rationale") or "Ação sustentada por recomendação persistida."),
        "primary_objective": None,
        "affected_dimensions": _dimension_baseline(candidate),
        "priority": priority if priority in _LEVEL else None,
        "effort": effort if effort in {"LOW","MEDIUM","HIGH"} else None,
        "confidence": confidence,
        "confidence_rationale": None,
        "dependencies": [],
        "implementation_guidance": [guidance[:4000]] if guidance else [],
        "validation_steps": [verification[:2500]] if verification else [],
        "source_refs": source_refs,
        "evidence_refs": evidence_refs,
        "remediation_refs": remediation_refs,
        "analysis_state": "PERSISTED_SOURCE",
        "_severity": str(row.get("severity") or "").upper(),
    }


def _security_actions(connection: sqlite3.Connection, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, "passive_security_remediations"):
        return []
    findings = {
        str(row.get("finding_id")): row
        for row in _rows(connection, "passive_security_findings", audit_id)
    }
    actions: list[dict[str, Any]] = []
    for row in _rows(connection, "passive_security_remediations", audit_id):
        finding_id = str(row.get("finding_id") or "")
        finding = findings.get(finding_id, {})
        source_id = str(row.get("remediation_id") or finding_id)
        title = str(finding.get("title") or "Correção de segurança")
        evidence_ids = _load(finding.get("evidence_ids_json"), [])
        refs = _existing_evidence_refs(connection, audit_id, evidence_ids if isinstance(evidence_ids,list) else [], ("CAT-10",))
        refs.insert(0, {
            **_catalog_ref("CAT-10","results",topic=title,ref_id=finding_id or source_id),
            "evidence_id": f"PASSIVE_SECURITY:{finding_id or source_id}",
            "kind": "source_record",
        })
        finding_anchor="security-finding-"+_anchor_token(finding_id or source_id,"finding")
        actions.append({
            "action_id": _stable_action_id(audit_id, "SECURITY_REMEDIATION", source_id),
            "source_kind": "SECURITY_REMEDIATION",
            "source_id": source_id,
            "title": title[:500],
            "reason": str(finding.get("description") or finding.get("impact") or "Finding de segurança passiva persistido.")[:4000],
            "primary_objective": None,
            "affected_dimensions": [
                {"dimension":"SECURITY","expected_gain":"HIGH"},
                {"dimension":"VULNERABILITIES","expected_gain":"HIGH"},
                {"dimension":"BEST_PRACTICES","expected_gain":"MEDIUM"},
            ],
            "priority": str(finding.get("severity") or "").upper() if str(finding.get("severity") or "").upper() in _LEVEL else None,
            "effort": None,
            "confidence": _confidence_label(finding.get("confidence")),
            "confidence_rationale": None,
            "dependencies": [],
            "implementation_guidance": [str(row.get("correction") or row.get("containment") or "")[:4000]] if row.get("correction") or row.get("containment") else [],
            "validation_steps": [str(row.get("validation") or "")[:2500]] if row.get("validation") else [],
            "source_refs": [_exact_ref("CAT-10","results",topic=title,ref_id=finding_id or source_id,anchor_id=finding_anchor)],
            "evidence_refs": refs,
            "remediation_refs": [_exact_ref("CAT-10","results",topic=title,ref_id=source_id,anchor_id=finding_anchor)],
            "analysis_state": "PERSISTED_SOURCE",
            "_severity": str(finding.get("severity") or "").upper(),
        })
    return actions


def _validate_references(actions: Sequence[Mapping[str, Any]]) -> None:
    for action in actions:
        if not action.get("evidence_refs"):
            raise ValueError(f"action without evidence reference: {action.get('action_id')}")
        for field in ("source_refs","evidence_refs","remediation_refs"):
            values = action.get(field)
            if not isinstance(values, list):
                raise ValueError(f"{field} must be list")
            for ref in values:
                if not isinstance(ref, Mapping):
                    raise ValueError(f"invalid {field} reference")
                catalog_id = str(ref.get("catalog_id") or "")
                section_id = str(ref.get("section_id") or "")
                page = CATALOG_PAGE_BY_ID.get(catalog_id)
                if page is None or section_id not in _CATALOG_SECTIONS:
                    raise ValueError(f"unresolvable catalog reference: {catalog_id}#{section_id}")
                anchor_id = str(ref.get("anchor_id") or "")
                expected_href = f"{page.filename}#{anchor_id}" if anchor_id else f"{page.filename}#{section_id}"
                if str(ref.get("href") or "") != expected_href:
                    raise ValueError("catalog href is not deterministic")
                if anchor_id and not re.fullmatch(r"[a-z0-9_-]+", anchor_id):
                    raise ValueError("catalog anchor is not deterministic")


def build_strategic_context(*, audit_id: str, workspace: AuditWorkspace) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    """Build compact context only from persisted audit/catalog-owned data."""
    data = _load_data(audit_id, workspace.database)
    # Recommendation governance is deterministic persisted analysis, not collection.
    evaluate_recommendations(workspace.database, audit_id)

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        governance_rows = _rows(connection, "recommendation_governance", audit_id)
        candidates = collect_candidates(connection, audit_id)
        candidate_map = {
            (str(item.get("source_kind")), str(item.get("source_id"))): item
            for item in candidates
        }
        actions: list[dict[str, Any]] = []
        for governance in governance_rows:
            if str(governance.get("decision") or "").upper() != ACCEPTED:
                continue
            key = (str(governance.get("source_kind")), str(governance.get("source_id")))
            candidate = candidate_map.get(key)
            if candidate is None:
                continue
            actions.append(_action_from_candidate(connection, audit_id, candidate, governance))
        actions.extend(_security_actions(connection, audit_id))
        unique = {}
        for action in actions:
            unique[str(action["action_id"])] = action
        actions = list(unique.values())[:MAX_ACTIONS]
        _validate_references(actions)

        catalog_rows = []
        limitations = []
        for catalog_id in sorted(data.selected):
            if catalog_id not in CATALOG_PAGE_BY_ID:
                continue
            status, _tone, detail = catalog_page._catalog_status(workspace.database, data, catalog_id)
            metrics = [
                {"name": str(name), "value": value, "kind": str(kind)}
                for name, value, kind in catalog_page._catalog_metrics(workspace.database, data, catalog_id)[:12]
            ]
            catalog_rows.append({
                "catalog_id": catalog_id,
                "status": status,
                "detail": detail,
                "metrics": metrics,
                "page": CATALOG_PAGE_BY_ID[catalog_id].filename,
            })
            if status not in {"CONCLUÍDO","NÃO SOLICITADO"}:
                limitations.append({"catalog_id":catalog_id,"status":status,"detail":detail})

        audit = {
            "audit_id": audit_id,
            "targets": list(data.targets),
            "primary_language": data.audit.get("primary_language"),
            "market": data.audit.get("market"),
            "audit_status": data.audit.get("status"),
            "logical_status": data.fulfillment.get("status") if isinstance(data.fulfillment,Mapping) else None,
        }
        context = {
            "contract_version": CONTRACT_VERSION,
            "prompt_version": PROMPT_VERSION,
            "purpose": "DIRECTED_ANALYSIS",
            "audit": audit,
            "catalogs": catalog_rows,
            "actions": [
                {key:value for key,value in action.items() if not key.startswith("_")}
                for action in actions
            ],
            "limitations": limitations,
            "governance": {
                "facts_must_come_from_persisted_sources": True,
                "ai_may_only_annotate_existing_action_ids": True,
                "ai_must_not_create_catalog_links": True,
                "human_review_required": True,
                "security_active_testing_forbidden": True,
                "ranking_causality_forbidden": True,
            },
        }
    finally:
        connection.close()
    sanitized = redact_value(context)
    normalized = dict(sanitized) if isinstance(sanitized, Mapping) else context
    fingerprint = sha256(_dump(normalized).encode("utf-8")).hexdigest()
    return normalized, actions, fingerprint


def _ai_requested(audit_id: str, workspace: AuditWorkspace) -> bool:
    data = _load_data(audit_id, workspace.database)
    for catalog_id in data.selected:
        item = data.catalog_items.get(catalog_id, {})
        if isinstance(item, Mapping) and bool(item.get("ai_execution_enabled", False)):
            return True
    return False


def _provider_config(audit_id: str, workspace: AuditWorkspace, language: str) -> ImprovementConfig | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        provider = model = reasoning = ""
        if _table_exists(connection, "improvement_intelligence_runs"):
            row = connection.execute(
                """SELECT provider,model,reasoning FROM improvement_intelligence_runs
                   WHERE audit_id=? AND provider IS NOT NULL ORDER BY updated_at DESC LIMIT 1""",
                (audit_id,),
            ).fetchone()
            if row:
                provider, model, reasoning = str(row["provider"] or ""), str(row["model"] or ""), str(row["reasoning"] or "")
        if (not provider or provider.casefold() in {"auto","none"}) and _table_exists(connection, "ai_provider_attempts"):
            cols = _columns(connection, "ai_provider_attempts")
            where = "audit_id=?"
            params: list[Any] = [audit_id]
            if "status" in cols:
                where += " AND status='SUCCESS'"
            if "operation" in cols:
                preferred = connection.execute(
                    f"""SELECT provider,model,reasoning_profile FROM ai_provider_attempts
                        WHERE {where} AND operation='IMPROVEMENT_INTELLIGENCE'
                        ORDER BY started_at DESC,rowid DESC LIMIT 1""",
                    tuple(params),
                ).fetchone()
            else:
                preferred = None
            row = preferred or connection.execute(
                f"""SELECT provider,model,reasoning_profile FROM ai_provider_attempts
                    WHERE {where} ORDER BY started_at DESC,rowid DESC LIMIT 1""",
                tuple(params),
            ).fetchone()
            if row:
                provider, model, reasoning = str(row["provider"] or ""), str(row["model"] or ""), str(row["reasoning_profile"] or "")
    finally:
        connection.close()
    if not provider:
        provider = str(os.environ.get("RASAI_AI_PROVIDER") or "").strip()
        model = str(os.environ.get("RASAI_AI_MODEL") or "").strip()
        reasoning = str(os.environ.get("RASAI_AI_REASONING") or "").strip()
    if not provider or provider.casefold() in {"auto","none"}:
        return None
    try:
        return ImprovementConfig(
            enabled=True,
            provider=provider.casefold(),
            model=model,
            reasoning=reasoning,
            domains=DEFAULT_DOMAINS,
            max_recommendations=MAX_ACTIONS,
            timeout_seconds=240.0,
            language=language,
        ).validate()
    except (ValueError, TypeError):
        return None


def _schema(action_ids: Sequence[str]) -> dict[str, Any]:
    action_enum = list(action_ids)
    return {
        "type":"object",
        "additionalProperties":False,
        "required":["summary","actions","roadmap"],
        "properties":{
            "summary":{
                "type":"object","additionalProperties":False,
                "required":["strengths","fragilities","risks","opportunities","insufficient_evidence","plan_overview"],
                "properties":{
                    "strengths":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":800}},
                    "fragilities":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":800}},
                    "risks":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":800}},
                    "opportunities":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":800}},
                    "insufficient_evidence":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":800}},
                    "plan_overview":{"type":"string","maxLength":4000},
                },
            },
            "actions":{
                "type":"array","maxItems":len(action_enum),
                "items":{
                    "type":"object","additionalProperties":False,
                    "required":["action_id","reason","primary_objective","affected_dimensions","priority","effort","confidence","confidence_reason","dependencies","implementation_guidance","validation_steps"],
                    "properties":{
                        "action_id":{"type":"string","enum":action_enum},
                        "reason":{"type":"string","maxLength":3000},
                        "primary_objective":{"type":"string","maxLength":500},
                        "affected_dimensions":{
                            "type":"array","maxItems":len(_DIMENSIONS),
                            "items":{
                                "type":"object","additionalProperties":False,
                                "required":["dimension","expected_gain"],
                                "properties":{
                                    "dimension":{"type":"string","enum":list(_DIMENSIONS)},
                                    "expected_gain":{"type":"string","enum":sorted(_GAIN)},
                                },
                            },
                        },
                        "priority":{"type":"string","enum":["LOW","MEDIUM","HIGH","CRITICAL"]},
                        "effort":{"type":"string","enum":["LOW","MEDIUM","HIGH"]},
                        "confidence":{"type":"string","enum":["LOW","MEDIUM","HIGH"]},
                        "confidence_reason":{"type":"string","maxLength":1800},
                        "dependencies":{"type":"array","uniqueItems":True,"maxItems":20,"items":{"type":"string","enum":action_enum}},
                        "implementation_guidance":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":1800}},
                        "validation_steps":{"type":"array","maxItems":10,"items":{"type":"string","maxLength":1800}},
                    },
                },
            },
            "roadmap":{
                "type":"array","maxItems":12,
                "items":{
                    "type":"object","additionalProperties":False,
                    "required":["phase","objective","action_ids"],
                    "properties":{
                        "phase":{"type":"string","maxLength":300},
                        "objective":{"type":"string","maxLength":1000},
                        "action_ids":{"type":"array","uniqueItems":True,"items":{"type":"string","enum":action_enum}},
                    },
                },
            },
        },
    }


def _validate_ai_output(payload: Any, actions: Sequence[Mapping[str, Any]]) -> tuple[dict[str,Any],dict[str,dict[str,Any]],list[dict[str,Any]]]:
    if not isinstance(payload, Mapping):
        raise ValueError("Directed Analysis AI response must be an object")
    summary = payload.get("summary")
    raw_actions = payload.get("actions")
    roadmap = payload.get("roadmap")
    if not isinstance(summary, Mapping) or not isinstance(raw_actions, list) or not isinstance(roadmap, list):
        raise ValueError("Directed Analysis AI response missing summary/actions/roadmap")
    known = {str(action["action_id"]): action for action in actions}
    enriched: dict[str,dict[str,Any]] = {}
    for raw in raw_actions:
        if not isinstance(raw, Mapping):
            raise ValueError("Directed Analysis action must be object")
        action_id = str(raw.get("action_id") or "")
        if action_id not in known:
            raise ValueError(f"unknown action_id {action_id!r}")
        if action_id in enriched:
            raise ValueError(f"duplicate action_id {action_id!r}")
        deps = [str(item) for item in raw.get("dependencies", [])]
        if action_id in deps or any(item not in known for item in deps):
            raise ValueError("invalid action dependency")
        dims = raw.get("affected_dimensions")
        if not isinstance(dims, list):
            raise ValueError("affected_dimensions must be list")
        for item in dims:
            if not isinstance(item, Mapping) or str(item.get("dimension")) not in _DIMENSIONS or str(item.get("expected_gain")) not in _GAIN:
                raise ValueError("invalid affected dimension")
        priority = str(raw.get("priority") or "").upper()
        effort = str(raw.get("effort") or "").upper()
        confidence = str(raw.get("confidence") or "").upper()
        if priority not in _LEVEL or effort not in {"LOW","MEDIUM","HIGH"} or confidence not in _CONFIDENCE:
            raise ValueError("invalid priority/effort/confidence")
        enriched[action_id] = {
            "reason": str(raw.get("reason") or "")[:3000],
            "primary_objective": str(raw.get("primary_objective") or "")[:500],
            "affected_dimensions": [{"dimension":str(v["dimension"]),"expected_gain":str(v["expected_gain"])} for v in dims],
            "priority": priority,
            "effort": effort,
            "confidence": confidence,
            "confidence_rationale": str(raw.get("confidence_reason") or "")[:1800],
            "dependencies": deps,
            "implementation_guidance": [str(v)[:1800] for v in raw.get("implementation_guidance", []) if str(v).strip()],
            "validation_steps": [str(v)[:1800] for v in raw.get("validation_steps", []) if str(v).strip()],
            "analysis_state": "AI_ANALYZED",
        }
    validated_roadmap=[]
    for phase in roadmap:
        if not isinstance(phase, Mapping):
            raise ValueError("invalid roadmap phase")
        ids=[str(v) for v in phase.get("action_ids", [])]
        if any(v not in known for v in ids):
            raise ValueError("roadmap references unknown action")
        validated_roadmap.append({
            "phase":str(phase.get("phase") or "")[:300],
            "objective":str(phase.get("objective") or "")[:1000],
            "action_ids":ids,
        })
    clean_summary={
        key:[str(v)[:800] for v in summary.get(key,[]) if str(v).strip()]
        for key in ("strengths","fragilities","risks","opportunities","insufficient_evidence")
    }
    clean_summary["plan_overview"]=str(summary.get("plan_overview") or "")[:4000]
    return clean_summary,enriched,validated_roadmap


def _ai_analyze(
    *, audit_id: str, workspace: AuditWorkspace, context_payload: Mapping[str,Any],
    actions: Sequence[Mapping[str,Any]], config: ImprovementConfig, target_context: Any,
) -> tuple[dict[str,Any],dict[str,dict[str,Any]],list[dict[str,Any]],Any,str|None]:
    provider = _build_provider(config)
    if not getattr(provider, "api_key", None):
        return {},{},[],None,"AI_NOT_CONFIGURED"
    recorder=AiExchangeRecorder()
    instrument_provider_transport(provider,recorder)
    schema=_schema([str(action["action_id"]) for action in actions])
    instructions=(
        "You are the evidence-bound Directed Analysis strategist for RASAi. "
        "Use only the supplied persisted context and existing action IDs. Do not create new technical facts, actions, "
        "catalog links, evidence IDs, vulnerabilities, ranking causes, metrics or claims. Correlate actions across dimensions, "
        "prioritize by impact, breadth, evidence confidence, effort, dependencies, risk and blockers. "
        "Security findings may override ordinary benefit/effort ordering when material. "
        "Confidence means support from evidence in this audit, never probability of guaranteed improvement. "
        "Return JSON only matching the schema. Dependencies and roadmap may reference only supplied action IDs. "
        "For validation, describe how to re-run the corresponding CAT/metric from the supplied source references. "
        "Do not propose active exploitation, payloads, credential attacks or security bypasses. "
        "Do not claim that SEO/GEO changes guarantee ranking improvements. Human review is mandatory. "
        f"Write human-readable text in {config.language}. This request purpose is DIRECTED_ANALYSIS."
    )
    request_context=dict(context_payload)
    request_context["snapshot_id"]=target_context.snapshot_id
    request_context["page_url"]=target_context.url
    user_text="Persisted RASAi strategic context:\n"+json.dumps(request_context,ensure_ascii=False,default=str)
    body=json.dumps(_provider_payload(provider,instructions=instructions,user_text=user_text,schema=schema),ensure_ascii=False,separators=(",",":")).encode("utf-8")
    payload_hash=sha256(body).hexdigest()
    summary_text=f"contract={CONTRACT_VERSION};actions={len(actions)};context={context_payload.get('contract_version')};snapshot={target_context.snapshot_id}"
    last_reason=None
    raw_payload=None
    try:
        for ordinal in range(1,3):
            started_at=datetime.now(timezone.utc); started_perf=time.perf_counter()
            diagnostic=None; usage=None; raw=None; status=AttemptStatus.TECHNICAL_ERROR
            try:
                candidate=provider._transport(provider.endpoint,provider._headers(),body,config.timeout_seconds)
                if not isinstance(candidate,Mapping):
                    diagnostic=ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE)
                else:
                    raw=candidate; usage=_provider_usage(provider,raw); diagnostic=_provider_native_error(provider,raw)
                    if diagnostic is None:
                        status=AttemptStatus.SUCCESS
            except HTTPError as exc:
                diagnostic=_core_diagnostic_from_http(exc) if isinstance(provider,ResponsesSemanticProvider) else _extension_diagnostic_from_http(exc)
            except TimeoutError:
                diagnostic=ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR)
            except (URLError,OSError):
                diagnostic=ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR)
            except Exception as exc:
                diagnostic=ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,error_type=type(exc).__name__)
            finished_at=datetime.now(timezone.utc)
            duration_ms=max(0,int((time.perf_counter()-started_perf)*1000))
            estimated,currency,pricing_version=estimate_cost(str(provider.name),str(provider.model),usage,finished_at)
            if status is AttemptStatus.SUCCESS and raw is not None:
                try:
                    raw_payload=_provider_extract(provider,raw)
                    summary,enriched,roadmap=_validate_ai_output(raw_payload,actions)
                except Exception as exc:
                    status=AttemptStatus.CONTRACT_ERROR
                    diagnostic=ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR,error_type=type(exc).__name__,error_code="DIRECTED_ANALYSIS_OUTPUT_INVALID")
                else:
                    attempt=ProviderAttempt(
                        provider=str(provider.name),model=str(provider.model),
                        reasoning_profile=str(getattr(provider,"reasoning_profile",config.reasoning)),
                        provider_rank=int(getattr(provider.policy,"rank",999)),attempt_index=ordinal,
                        snapshot_id=target_context.snapshot_id,url=target_context.url,
                        started_at=started_at,finished_at=finished_at,duration_ms=duration_ms,
                        status=AttemptStatus.SUCCESS,usage=usage,estimated_cost=estimated,cost_currency=currency,
                        pricing_version=pricing_version,request_message_summary=summary_text,
                        request_payload_hash=payload_hash,provider_qualification=str(getattr(provider.policy,"qualification","PROVISIONAL")),
                        provider_reliability_score=getattr(provider.policy,"reliability_score",None),
                        semantic_contract_version=CONTRACT_VERSION,retry_eligible=False,
                        decision=DECISION_SUCCESS_AFTER_RETRY if ordinal>1 else DECISION_SUCCESS,
                    )
                    _persist_attempt(workspace,audit_id,target_context,attempt)
                    return summary,enriched,roadmap,raw_payload,None
            policy=retry_policy(diagnostic.error_class if diagnostic else None,diagnostic.retry_after_seconds if diagnostic else None)
            decision=DECISION_RETRY if policy.eligible and ordinal<2 else DECISION_STOP
            attempt=ProviderAttempt(
                provider=str(provider.name),model=str(provider.model),
                reasoning_profile=str(getattr(provider,"reasoning_profile",config.reasoning)),
                provider_rank=int(getattr(provider.policy,"rank",999)),attempt_index=ordinal,
                snapshot_id=target_context.snapshot_id,url=target_context.url,
                started_at=started_at,finished_at=finished_at,duration_ms=duration_ms,status=status,
                diagnostic=diagnostic,usage=usage,estimated_cost=estimated,cost_currency=currency,
                pricing_version=pricing_version,request_message_summary=summary_text,request_payload_hash=payload_hash,
                provider_qualification=str(getattr(provider.policy,"qualification","PROVISIONAL")),
                provider_reliability_score=getattr(provider.policy,"reliability_score",None),
                semantic_contract_version=CONTRACT_VERSION,retry_eligible=policy.eligible,decision=decision,
            )
            _persist_attempt(workspace,audit_id,target_context,attempt)
            last_reason=diagnostic.reason if diagnostic else "AI_PROVIDER_UNAVAILABLE"
            if decision==DECISION_RETRY:
                if policy.delay_seconds>0:
                    time.sleep(policy.delay_seconds)
                continue
            break
        return {},{},[],raw_payload,last_reason or "AI_PROVIDER_UNAVAILABLE"
    finally:
        persist_ai_exchange_log(audit_id=audit_id,workspace=workspace,recorder=recorder)


def _persist(
    *, audit_id: str, workspace: AuditWorkspace, context: Mapping[str,Any], context_hash: str,
    actions: Sequence[Mapping[str,Any]], status: str, provider: str|None, model: str|None,
    reasoning: str|None, language: str, summary: Mapping[str,Any], roadmap: Sequence[Mapping[str,Any]],
    raw_ai: Any, reason: str|None,
) -> str:
    connection=sqlite3.connect(workspace.database); connection.row_factory=sqlite3.Row
    try:
        _ensure_schema(connection)
        existing=connection.execute("SELECT * FROM directed_analysis_runs WHERE audit_id=?",(audit_id,)).fetchone()
        run_id=str(existing["analysis_run_id"]) if existing else new_id("DAN")
        created=str(existing["created_at"]) if existing else _now()
        now=_now()
        dims=sorted({
            str(item.get("dimension"))
            for action in actions
            for item in action.get("affected_dimensions",[])
            if isinstance(item,Mapping) and item.get("dimension")
        })
        objectives=sorted({str(action.get("primary_objective")) for action in actions if action.get("primary_objective")})
        limitations=list(context.get("limitations") or [])
        if reason:
            limitations.append({"scope":"DIRECTED_ANALYSIS","reason":reason})
        source_evidence=[ref for action in actions for ref in action.get("evidence_refs",[])]
        source_remediations=[ref for action in actions for ref in action.get("remediation_refs",[])]
        with connection:
            connection.execute("DELETE FROM directed_analysis_actions WHERE audit_id=?",(audit_id,))
            for action in actions:
                connection.execute(
                    """INSERT INTO directed_analysis_actions(
                        action_id,audit_id,source_kind,source_id,title,reason,primary_objective,
                        affected_dimensions_json,priority,effort,confidence,confidence_rationale,
                        dependencies_json,implementation_guidance_json,validation_steps_json,
                        source_refs_json,evidence_refs_json,remediation_refs_json,analysis_state,created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        action["action_id"],audit_id,action["source_kind"],action["source_id"],action["title"],action["reason"],
                        action.get("primary_objective"),_dump(action.get("affected_dimensions",[])),action.get("priority"),
                        action.get("effort"),action.get("confidence"),action.get("confidence_rationale"),
                        _dump(action.get("dependencies",[])),_dump(action.get("implementation_guidance",[])),
                        _dump(action.get("validation_steps",[])),_dump(action.get("source_refs",[])),
                        _dump(action.get("evidence_refs",[])),_dump(action.get("remediation_refs",[])),
                        action.get("analysis_state") or "PERSISTED_SOURCE",created,now,
                    ),
                )
            connection.execute(
                """INSERT INTO directed_analysis_runs(
                    analysis_run_id,audit_id,contract_version,prompt_version,status,provider,model,reasoning,analysis_language,
                    input_context_hash,catalog_versions_json,source_evidence_json,source_remediations_json,
                    strategic_summary_json,dimensions_json,objectives_json,roadmap_json,limitations_json,context_json,
                    raw_ai_response_json,actions_count,ai_actions_count,reason,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    contract_version=excluded.contract_version,prompt_version=excluded.prompt_version,status=excluded.status,
                    provider=excluded.provider,model=excluded.model,reasoning=excluded.reasoning,
                    analysis_language=excluded.analysis_language,input_context_hash=excluded.input_context_hash,
                    catalog_versions_json=excluded.catalog_versions_json,source_evidence_json=excluded.source_evidence_json,
                    source_remediations_json=excluded.source_remediations_json,
                    strategic_summary_json=excluded.strategic_summary_json,dimensions_json=excluded.dimensions_json,
                    objectives_json=excluded.objectives_json,roadmap_json=excluded.roadmap_json,
                    limitations_json=excluded.limitations_json,context_json=excluded.context_json,
                    raw_ai_response_json=excluded.raw_ai_response_json,actions_count=excluded.actions_count,
                    ai_actions_count=excluded.ai_actions_count,reason=excluded.reason,updated_at=excluded.updated_at""",
                (
                    run_id,audit_id,CONTRACT_VERSION,PROMPT_VERSION,status,provider,model,reasoning,language,context_hash,
                    _dump({"catalog_report_contract":CATALOG_REPORT_CONTRACT_VERSION,"catalogs":[row.get("catalog_id") for row in context.get("catalogs",[])]}),
                    _dump(source_evidence),_dump(source_remediations),_dump(summary),_dump(dims),_dump(objectives),
                    _dump(list(roadmap)),_dump(limitations),_dump(context),_dump(redact_value(raw_ai)) if raw_ai is not None else None,
                    len(actions),sum(1 for action in actions if action.get("analysis_state")=="AI_ANALYZED"),reason,created,now,
                ),
            )
        return run_id
    finally:
        connection.close()


def execute_directed_analysis(*, audit_id: str, workspace: AuditWorkspace, force: bool=False) -> DirectedAnalysisResult:
    """Execute strategic synthesis after all catalog-owned data is in a final known state."""
    context,actions,context_hash=build_strategic_context(audit_id=audit_id,workspace=workspace)
    connection=sqlite3.connect(workspace.database); connection.row_factory=sqlite3.Row
    try:
        _ensure_schema(connection)
        existing=connection.execute("SELECT * FROM directed_analysis_runs WHERE audit_id=?",(audit_id,)).fetchone()
        if (
            not force and existing is not None
            and str(existing["input_context_hash"])==context_hash
            and str(existing["status"]) in {"COMPLETE","COMPLETE_WITH_LIMITATIONS","DISABLED","NO_ACTIONS"}
        ):
            return DirectedAnalysisResult(
                str(existing["status"]),str(existing["analysis_run_id"]),int(existing["actions_count"] or 0),
                int(existing["ai_actions_count"] or 0),str(existing["provider"] or "") or None,
                str(existing["model"] or "") or None,str(existing["reason"] or "") or None,True,
            )
    finally:
        connection.close()

    language=configured_analysis_language(audit_language=str(context.get("audit",{}).get("primary_language") or "pt-BR"))
    if not actions:
        run_id=_persist(
            audit_id=audit_id,workspace=workspace,context=context,context_hash=context_hash,actions=[],
            status="NO_ACTIONS",provider=None,model=None,reasoning=None,language=language,
            summary={},roadmap=[],raw_ai=None,reason="NO_ACTIONABLE_PERSISTED_RECOMMENDATIONS",
        )
        return DirectedAnalysisResult("NO_ACTIONS",run_id,0,0,reason="NO_ACTIONABLE_PERSISTED_RECOMMENDATIONS")

    if not _ai_requested(audit_id,workspace):
        run_id=_persist(
            audit_id=audit_id,workspace=workspace,context=context,context_hash=context_hash,actions=actions,
            status="DISABLED",provider=None,model=None,reasoning=None,language=language,
            summary={},roadmap=[],raw_ai=None,reason="AI_NOT_REQUESTED_FOR_AUDIT",
        )
        return DirectedAnalysisResult("DISABLED",run_id,len(actions),0,reason="AI_NOT_REQUESTED_FOR_AUDIT")

    config=_provider_config(audit_id,workspace,language)
    if config is None:
        run_id=_persist(
            audit_id=audit_id,workspace=workspace,context=context,context_hash=context_hash,actions=actions,
            status="COMPLETE_WITH_LIMITATIONS",provider=None,model=None,reasoning=None,language=language,
            summary={},roadmap=[],raw_ai=None,reason="AI_PROVIDER_NOT_RESOLVED",
        )
        return DirectedAnalysisResult("COMPLETE_WITH_LIMITATIONS",run_id,len(actions),0,reason="AI_PROVIDER_NOT_RESOLVED")

    try:
        connection=sqlite3.connect(workspace.database); connection.row_factory=sqlite3.Row
        try:
            target_context=_target_context(connection,audit_id,workspace)
        finally:
            connection.close()
        summary,enriched,roadmap,raw_ai,reason=_ai_analyze(
            audit_id=audit_id,workspace=workspace,context_payload=context,
            actions=actions,config=config,target_context=target_context,
        )
    except Exception as exc:
        summary,enriched,roadmap,raw_ai,reason={}, {}, [], None, f"DIRECTED_ANALYSIS_ERROR:{type(exc).__name__}"

    merged=[]
    for action in actions:
        item={key:value for key,value in action.items() if not key.startswith("_")}
        extra=enriched.get(str(action["action_id"]))
        if extra:
            item.update(extra)
            severity=str(action.get("_severity") or "").upper()
            if severity in {"CRITICAL","HIGH"} and "SECURITY" in {d.get("dimension") for d in item.get("affected_dimensions",[]) if isinstance(d,Mapping)}:
                if item.get("priority") in {"LOW","MEDIUM"}:
                    item["priority"]="HIGH"
        merged.append(item)
    status="COMPLETE" if reason is None else "COMPLETE_WITH_LIMITATIONS"
    run_id=_persist(
        audit_id=audit_id,workspace=workspace,context=context,context_hash=context_hash,actions=merged,status=status,
        provider=config.provider,model=config.model,reasoning=config.reasoning,language=language,
        summary=summary,roadmap=roadmap,raw_ai=raw_ai,reason=reason,
    )
    return DirectedAnalysisResult(
        status,run_id,len(merged),sum(1 for item in merged if item.get("analysis_state")=="AI_ANALYZED"),
        provider=config.provider,model=config.model,reason=reason,
    )


def reprocess_directed_analysis(*, audit_id: str, workspace: AuditWorkspace) -> DirectedAnalysisResult:
    """Refresh Directed Analysis only when its persisted strategic context changed.

    Reprocessing must not create a paid AI call merely because another requirement was
    retried. The canonical executor fingerprints persisted inputs and reuses a completed
    result when that context is unchanged.
    """
    return execute_directed_analysis(audit_id=audit_id,workspace=workspace,force=False)


__all__=[
    "CONTRACT_VERSION","PROMPT_VERSION","DirectedAnalysisResult","build_strategic_context",
    "execute_directed_analysis","reprocess_directed_analysis",
]
