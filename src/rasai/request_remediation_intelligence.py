"""Deterministic request/runtime error grouping with bounded AI remediation guidance.

Facts remain deterministic and source-bound. The AI receives already grouped evidence and
may only propose a remediation for each group; it never changes Apdex, findings or scores.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import re
import sqlite3
import sys
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit, urlunsplit

REQUEST_REMEDIATION_CONTRACT = "REQUEST-REMEDIATION-001"
AI_BATCH_SIZE = 10
_INSTALLED = False

_FAMILY_META: dict[str, tuple[str, tuple[str, ...], tuple[str, str]]] = {
    "RESOURCE_NOT_FOUND": (
        "Corrigir recursos ausentes ou referências quebradas",
        ("Performance", "Experiência", "Confiabilidade"),
        ("MDN · HTTP 404", "https://developer.mozilla.org/docs/Web/HTTP/Reference/Status/404"),
    ),
    "ACCESS_DENIED": (
        "Corrigir autorização ou exposição indevida de recursos",
        ("Experiência", "Confiabilidade"),
        ("MDN · HTTP 403", "https://developer.mozilla.org/docs/Web/HTTP/Reference/Status/403"),
    ),
    "SERVER_ERROR": (
        "Corrigir falhas do servidor ou dependência upstream",
        ("Performance", "Experiência", "Confiabilidade"),
        ("MDN · HTTP 5xx", "https://developer.mozilla.org/docs/Web/HTTP/Reference/Status#server_error_responses"),
    ),
    "RATE_LIMIT": (
        "Ajustar limitação, backoff ou volume de requisições",
        ("Experiência", "Confiabilidade"),
        ("MDN · HTTP 429", "https://developer.mozilla.org/docs/Web/HTTP/Reference/Status/429"),
    ),
    "TIMEOUT": (
        "Reduzir timeouts e dependências lentas",
        ("Apdex", "Performance", "Experiência", "Confiabilidade"),
        ("web.dev · Reliability", "https://web.dev/reliable/"),
    ),
    "DNS": (
        "Corrigir resolução DNS ou disponibilidade do hostname",
        ("Performance", "Experiência", "Confiabilidade"),
        ("MDN · DNS", "https://developer.mozilla.org/docs/Glossary/DNS"),
    ),
    "CONNECTION": (
        "Corrigir falhas de conexão ou disponibilidade de origem",
        ("Performance", "Experiência", "Confiabilidade"),
        ("web.dev · Reliability", "https://web.dev/reliable/"),
    ),
    "CORS": (
        "Corrigir política CORS para os recursos afetados",
        ("Experiência", "Funcionalidade"),
        ("MDN · CORS", "https://developer.mozilla.org/docs/Web/HTTP/Guides/CORS"),
    ),
    "CSP": (
        "Corrigir Content-Security-Policy para dependências necessárias",
        ("Experiência", "Funcionalidade", "Segurança"),
        ("MDN · CSP", "https://developer.mozilla.org/docs/Web/HTTP/Guides/CSP"),
    ),
    "MIME": (
        "Corrigir Content-Type ou tipo MIME do recurso",
        ("Experiência", "Funcionalidade"),
        ("MDN · MIME types", "https://developer.mozilla.org/docs/Web/HTTP/Guides/MIME_types"),
    ),
    "CLIENT_BLOCK": (
        "Revisar dependência bloqueada no cliente e estratégia de fallback",
        ("Experiência", "Confiabilidade"),
        ("MDN · Fetch", "https://developer.mozilla.org/docs/Web/API/Fetch_API"),
    ),
    "JAVASCRIPT_RUNTIME": (
        "Corrigir exceções JavaScript recorrentes",
        ("Experiência", "Funcionalidade"),
        ("MDN · JavaScript error reference", "https://developer.mozilla.org/docs/Web/JavaScript/Reference/Errors"),
    ),
    "CONSOLE_RUNTIME": (
        "Investigar erros de console recorrentes",
        ("Experiência", "Funcionalidade"),
        ("Chrome DevTools · Console", "https://developer.chrome.com/docs/devtools/console/"),
    ),
    "HTTP_OTHER": (
        "Corrigir respostas HTTP de erro recorrentes",
        ("Experiência", "Confiabilidade"),
        ("MDN · HTTP status", "https://developer.mozilla.org/docs/Web/HTTP/Reference/Status"),
    ),
    "REQUEST_OTHER": (
        "Investigar falhas recorrentes de requisição",
        ("Performance", "Experiência", "Confiabilidade"),
        ("Chrome DevTools · Network", "https://developer.chrome.com/docs/devtools/network/"),
    ),
}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _safe_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple, int, float, bool)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _host(value: str | None) -> str:
    try:
        return str(urlsplit(str(value or "")).hostname or "").casefold().removeprefix("www.")
    except Exception:
        return ""


def _is_first_party(candidate: str | None, target: str | None) -> bool | None:
    candidate_host, target_host = _host(candidate), _host(target)
    if not candidate_host or not target_host:
        return None
    return candidate_host == target_host


def _normalized_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").casefold()
        netloc = host
        if parts.port:
            netloc += f":{parts.port}"
        path = re.sub(r"/{2,}", "/", parts.path or "/")
        return urlunsplit((parts.scheme.casefold(), netloc, path, "", ""))
    except Exception:
        return raw.split("?", 1)[0].split("#", 1)[0]


def _normalized_message(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip()).casefold()
    text = re.sub(r"\b\d{4,}\b", "#", text)
    text = re.sub(r"0x[0-9a-f]+", "0x#", text)
    return text[:500]


def _family(error_type: str, http_status: int | None, message: str) -> str:
    kind = str(error_type or "").upper()
    msg = str(message or "").casefold()
    status = int(http_status) if http_status is not None else None
    if status in {404, 410}:
        return "RESOURCE_NOT_FOUND"
    if status in {401, 403}:
        return "ACCESS_DENIED"
    if status == 429:
        return "RATE_LIMIT"
    if status is not None and 500 <= status <= 599:
        return "SERVER_ERROR"
    if status is not None and status >= 400:
        return "HTTP_OTHER"
    if "cors" in msg or "cross-origin" in msg:
        return "CORS"
    if "content security policy" in msg or "content-security-policy" in msg or "csp" in msg:
        return "CSP"
    if "mime" in msg or "content-type" in msg:
        return "MIME"
    if "timed out" in msg or "timeout" in msg or "err_timed_out" in msg:
        return "TIMEOUT"
    if "name_not_resolved" in msg or "dns" in msg:
        return "DNS"
    if any(token in msg for token in ("connection_refused", "connection_reset", "connection_closed", "network_changed", "internet_disconnected")):
        return "CONNECTION"
    if "blocked_by_client" in msg or "blocked by client" in msg:
        return "CLIENT_BLOCK"
    if kind in {"JAVASCRIPT_ERROR", "PAGE_ERROR"}:
        return "JAVASCRIPT_RUNTIME"
    if kind == "CONSOLE_ERROR":
        return "CONSOLE_RUNTIME"
    return "REQUEST_OTHER" if kind == "REQUEST_FAILED" else "CONSOLE_RUNTIME"


def _party_scope(value: bool | None) -> str:
    return "FIRST_PARTY" if value is True else "THIRD_PARTY" if value is False else "UNKNOWN"


def _recurrence_class(ratio: float) -> str:
    # Presentation bands only. They describe frequency; they do not diagnose causality.
    if ratio >= 0.80:
        return "Recorrente"
    if ratio >= 0.20:
        return "Intermitente"
    return "Ocasional"


def _problem_signature(event: Mapping[str, Any]) -> str:
    return "|".join(
        (
            str(event.get("family") or ""),
            str(event.get("normalized_url") or ""),
            str(event.get("http_status") or ""),
            str(event.get("resource_type") or ""),
            _normalized_message(event.get("message")),
        )
    )


def collect_request_error_evidence(
    database: Any,
    audit_id: str,
    *,
    sources: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Normalize request/browser errors from current deterministic collectors.

    Source adapters are explicit so new catalogs can be added without changing grouping
    semantics. CAT-06 browser diagnostics and CAT-07 per-request details are supported now.
    """
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    events: list[dict[str, Any]] = []
    sample_universe: set[str] = set()
    try:
        if (sources is None or "CAT-07" in sources) and _table_exists(connection, "synthetic_ux_apdex_samples"):
            sample_rows = [dict(row) for row in connection.execute(
                "SELECT * FROM synthetic_ux_apdex_samples WHERE audit_id=? ORDER BY run_index,sample_id",
                (audit_id,),
            ).fetchall()]
            sample_by_id = {str(row.get("sample_id")): row for row in sample_rows}
            for row in sample_rows:
                sample_universe.add("CAT-07:" + str(row.get("sample_id") or row.get("run_index")))
            if _table_exists(connection, "synthetic_ux_apdex_error_details"):
                for raw in connection.execute(
                    "SELECT * FROM synthetic_ux_apdex_error_details WHERE audit_id=? ORDER BY sample_id,sequence_no",
                    (audit_id,),
                ).fetchall():
                    row = dict(raw)
                    sample = sample_by_id.get(str(row.get("sample_id")), {})
                    source_url = str(row.get("source_url") or "")
                    first_party = None if row.get("first_party") is None else bool(row.get("first_party"))
                    status = int(row["http_status"]) if row.get("http_status") is not None else None
                    event = {
                        "source_catalog": "CAT-07",
                        "source_kind": "Synthetic User Experience Apdex",
                        "sample_key": "CAT-07:" + str(row.get("sample_id") or ""),
                        "sample_id": row.get("sample_id"),
                        "run_index": sample.get("run_index"),
                        "device": sample.get("device"),
                        "error_type": str(row.get("error_type") or "UNKNOWN"),
                        "source_url": source_url,
                        "normalized_url": _normalized_url(source_url),
                        "first_party": first_party,
                        "http_status": status,
                        "resource_type": row.get("resource_type"),
                        "message": row.get("message"),
                        "error_forced_frustrated": bool(sample.get("error_forced_frustrated")),
                        "captured_at": row.get("captured_at") or sample.get("captured_at"),
                    }
                    event["family"] = _family(event["error_type"], status, str(event.get("message") or ""))
                    events.append(event)

        if (sources is None or "CAT-06" in sources) and _table_exists(connection, "synthetic_apdex_samples"):
            cols = _columns(connection, "synthetic_apdex_samples")
            if "browser_diagnostics" in cols:
                for raw in connection.execute(
                    "SELECT * FROM synthetic_apdex_samples WHERE audit_id=? ORDER BY run_index,sample_id",
                    (audit_id,),
                ).fetchall():
                    sample = dict(raw)
                    sample_id = str(sample.get("sample_id") or f"{sample.get('url')}:{sample.get('device')}:{sample.get('run_index')}")
                    sample_key = "CAT-06:" + sample_id
                    sample_universe.add(sample_key)
                    parsed = _safe_json(sample.get("browser_diagnostics"), {})
                    browser_events = parsed.get("events", []) if isinstance(parsed, Mapping) else []
                    for item in browser_events if isinstance(browser_events, list) else []:
                        if not isinstance(item, Mapping):
                            continue
                        source_url = str(item.get("url") or "")
                        first_party = _is_first_party(source_url, sample.get("url")) if source_url else None
                        event = {
                            "source_catalog": "CAT-06",
                            "source_kind": "Synthetic Navigation Apdex",
                            "sample_key": sample_key,
                            "sample_id": sample_id,
                            "run_index": sample.get("run_index"),
                            "device": sample.get("device"),
                            "error_type": str(item.get("type") or "UNKNOWN"),
                            "source_url": source_url,
                            "normalized_url": _normalized_url(source_url),
                            "first_party": first_party,
                            "http_status": None,
                            "resource_type": None,
                            "message": item.get("message"),
                            "error_forced_frustrated": False,
                            "captured_at": sample.get("captured_at"),
                        }
                        event["family"] = _family(event["error_type"], None, str(event.get("message") or ""))
                        events.append(event)
    finally:
        connection.close()
    return events, sample_universe


def group_request_error_evidence(
    events: Sequence[Mapping[str, Any]],
    sample_universe: Iterable[str],
    *,
    audit_id: str = "",
) -> list[dict[str, Any]]:
    total_samples = len(set(str(value) for value in sample_universe if str(value)))
    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for raw in events:
        event = dict(raw)
        family = str(event.get("family") or _family(str(event.get("error_type") or ""), event.get("http_status"), str(event.get("message") or "")))
        event["family"] = family
        buckets[(family, _party_scope(event.get("first_party")))].append(event)

    groups: list[dict[str, Any]] = []
    for (family, party), members in buckets.items():
        meta = _FAMILY_META.get(family, _FAMILY_META["REQUEST_OTHER"])
        affected_samples = {str(item.get("sample_key")) for item in members if item.get("sample_key")}
        ratio = (len(affected_samples) / total_samples) if total_samples else 0.0
        observed: set[str] = set()
        if any(item.get("source_catalog") == "CAT-07" for item in members):
            observed.add("Experiência sintética")
        if any(item.get("source_catalog") == "CAT-06" for item in members):
            observed.add("Navegação sintética")
        if any(bool(item.get("error_forced_frustrated")) for item in members):
            observed.add("Apdex de experiência")
        problem_signatures = {_problem_signature(item) for item in members}
        group_basis = f"{audit_id}|{family}|{party}"
        group_id = "REQG-" + sha256(group_basis.encode("utf-8")).hexdigest()[:16].upper()
        resources = sorted({str(item.get("normalized_url") or item.get("source_url") or "") for item in members if item.get("normalized_url") or item.get("source_url")})
        statuses = sorted({int(item["http_status"]) for item in members if item.get("http_status") is not None})
        sources = sorted({str(item.get("source_catalog") or "") for item in members if item.get("source_catalog")})
        error_types = sorted({str(item.get("error_type") or "") for item in members if item.get("error_type")})
        evidence_fingerprint = sha256(json.dumps([
            {
                "source": item.get("source_catalog"),
                "sample": item.get("sample_key"),
                "type": item.get("error_type"),
                "url": item.get("normalized_url"),
                "status": item.get("http_status"),
                "message": _normalized_message(item.get("message")),
            }
            for item in members
        ], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        groups.append({
            "group_id": group_id,
            "family": family,
            "party_scope": party,
            "title": meta[0],
            "occurrence_count": len(members),
            "problem_count": len(problem_signatures),
            "affected_sample_count": len(affected_samples),
            "total_sample_count": total_samples,
            "recurrence_ratio": ratio,
            "recurrence_class": _recurrence_class(ratio),
            "source_catalogs": sources,
            "resource_urls": resources,
            "http_statuses": statuses,
            "error_types": error_types,
            "observed_impacts": sorted(observed),
            "potential_impacts": list(meta[1]),
            "public_reference_label": meta[2][0],
            "public_reference_url": meta[2][1],
            "evidence_fingerprint": evidence_fingerprint,
            "events": members,
        })
    return sorted(
        groups,
        key=lambda item: (-float(item["recurrence_ratio"]), -int(item["affected_sample_count"]), -int(item["occurrence_count"]), str(item["title"])),
    )


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS request_remediation_groups (
            group_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            family TEXT NOT NULL,
            party_scope TEXT NOT NULL,
            title TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL,
            problem_count INTEGER NOT NULL,
            affected_sample_count INTEGER NOT NULL,
            total_sample_count INTEGER NOT NULL,
            recurrence_ratio REAL NOT NULL,
            recurrence_class TEXT NOT NULL,
            source_catalogs_json TEXT NOT NULL,
            resource_urls_json TEXT NOT NULL,
            http_statuses_json TEXT NOT NULL,
            error_types_json TEXT NOT NULL,
            observed_impacts_json TEXT NOT NULL,
            potential_impacts_json TEXT NOT NULL,
            public_reference_label TEXT NOT NULL,
            public_reference_url TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS request_remediation_evidence (
            evidence_id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            audit_id TEXT NOT NULL,
            source_catalog TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            sample_key TEXT NOT NULL,
            sample_id TEXT,
            run_index INTEGER,
            device TEXT,
            error_type TEXT NOT NULL,
            source_url TEXT,
            normalized_url TEXT,
            first_party INTEGER,
            http_status INTEGER,
            resource_type TEXT,
            message TEXT,
            error_forced_frustrated INTEGER NOT NULL,
            captured_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_request_remediation_groups_audit
            ON request_remediation_groups(audit_id,recurrence_ratio DESC,occurrence_count DESC);
        CREATE INDEX IF NOT EXISTS idx_request_remediation_evidence_group
            ON request_remediation_evidence(audit_id,group_id,sample_key);
        CREATE TABLE IF NOT EXISTS request_remediation_ai (
            group_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            provider TEXT,
            model TEXT,
            status TEXT NOT NULL,
            title TEXT,
            solution TEXT,
            technical_detail TEXT,
            example TEXT,
            verification TEXT,
            confidence REAL,
            effort TEXT,
            reason TEXT,
            updated_at TEXT NOT NULL
        );
        """
    )


def persist_request_remediation_groups(database: Any, audit_id: str, groups: Sequence[Mapping[str, Any]]) -> None:
    connection = sqlite3.connect(database)
    try:
        _ensure_schema(connection)
        now = datetime.now(timezone.utc).isoformat()
        current_ids = {str(group["group_id"]) for group in groups}
        with connection:
            connection.execute("DELETE FROM request_remediation_evidence WHERE audit_id=?", (audit_id,))
            connection.execute("DELETE FROM request_remediation_groups WHERE audit_id=?", (audit_id,))
            for group in groups:
                connection.execute(
                    """INSERT INTO request_remediation_groups VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        group["group_id"], audit_id, group["family"], group["party_scope"], group["title"],
                        group["occurrence_count"], group["problem_count"], group["affected_sample_count"],
                        group["total_sample_count"], group["recurrence_ratio"], group["recurrence_class"],
                        json.dumps(group["source_catalogs"], ensure_ascii=False),
                        json.dumps(group["resource_urls"], ensure_ascii=False),
                        json.dumps(group["http_statuses"], ensure_ascii=False),
                        json.dumps(group["error_types"], ensure_ascii=False),
                        json.dumps(group["observed_impacts"], ensure_ascii=False),
                        json.dumps(group["potential_impacts"], ensure_ascii=False),
                        group["public_reference_label"], group["public_reference_url"],
                        group["evidence_fingerprint"], now,
                    ),
                )
                for sequence, event in enumerate(group.get("events", []), 1):
                    basis = "|".join((str(group["group_id"]), str(event.get("sample_key") or ""), str(sequence), _problem_signature(event)))
                    evidence_id = "REQE-" + sha256(basis.encode("utf-8")).hexdigest()[:18].upper()
                    first_party = event.get("first_party")
                    connection.execute(
                        """INSERT INTO request_remediation_evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            evidence_id, group["group_id"], audit_id, event.get("source_catalog") or "—",
                            event.get("source_kind") or "—", event.get("sample_key") or "—", event.get("sample_id"),
                            event.get("run_index"), event.get("device"), event.get("error_type") or "UNKNOWN",
                            event.get("source_url"), event.get("normalized_url"),
                            None if first_party is None else int(bool(first_party)), event.get("http_status"),
                            event.get("resource_type"), str(event.get("message") or "")[:2000] or None,
                            int(bool(event.get("error_forced_frustrated"))), event.get("captured_at"),
                        ),
                    )
            if current_ids:
                placeholders = ",".join("?" for _ in current_ids)
                connection.execute(
                    f"DELETE FROM request_remediation_ai WHERE audit_id=? AND group_id NOT IN ({placeholders})",
                    (audit_id, *sorted(current_ids)),
                )
            else:
                connection.execute("DELETE FROM request_remediation_ai WHERE audit_id=?", (audit_id,))
    finally:
        connection.close()


def _solution_schema(group_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["solutions"],
        "properties": {
            "solutions": {
                "type": "array",
                "minItems": 1,
                "maxItems": len(group_ids),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["group_id", "title", "solution", "technical_detail", "example", "verification", "confidence", "effort"],
                    "properties": {
                        "group_id": {"type": "string", "enum": list(group_ids)},
                        "title": {"type": "string"},
                        "solution": {"type": "string"},
                        "technical_detail": {"type": "string"},
                        "example": {"type": "string"},
                        "verification": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "effort": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
                    },
                },
            }
        },
    }


def _group_payload(group: Mapping[str, Any]) -> dict[str, Any]:
    events = list(group.get("events", []))[:8]
    return {
        "group_id": group["group_id"],
        "deterministic_title": group["title"],
        "family": group["family"],
        "party_scope": group["party_scope"],
        "problem_count": group["problem_count"],
        "occurrence_count": group["occurrence_count"],
        "affected_samples": group["affected_sample_count"],
        "total_samples": group["total_sample_count"],
        "recurrence_ratio": round(float(group["recurrence_ratio"]), 4),
        "recurrence_class": group["recurrence_class"],
        "source_catalogs": group["source_catalogs"],
        "resource_urls": list(group["resource_urls"])[:12],
        "http_statuses": group["http_statuses"],
        "error_types": group["error_types"],
        "observed_impacts": group["observed_impacts"],
        "potential_impacts": group["potential_impacts"],
        "official_reference": {
            "label": group["public_reference_label"],
            "url": group["public_reference_url"],
        },
        "event_examples": [
            {
                "catalog": event.get("source_catalog"),
                "device": event.get("device"),
                "type": event.get("error_type"),
                "url": event.get("normalized_url") or event.get("source_url"),
                "http_status": event.get("http_status"),
                "resource_type": event.get("resource_type"),
                "message": str(event.get("message") or "")[:500],
                "forced_apdex_frustrated": bool(event.get("error_forced_frustrated")),
            }
            for event in events
        ],
    }


def _validate_solutions(payload: Any, groups: Sequence[Mapping[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    allowed = {str(group["group_id"]): group for group in groups}
    accepted: dict[str, dict[str, Any]] = {}
    if not isinstance(payload, Mapping) or not isinstance(payload.get("solutions"), list):
        return accepted, list(allowed)
    for raw in payload["solutions"]:
        if not isinstance(raw, Mapping):
            continue
        group_id = str(raw.get("group_id") or "")
        if group_id not in allowed or group_id in accepted:
            continue
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError):
            continue
        effort = str(raw.get("effort") or "").upper()
        solution = str(raw.get("solution") or "").strip()
        if not 0 <= confidence <= 1 or effort not in {"LOW", "MEDIUM", "HIGH"} or not solution:
            continue
        accepted[group_id] = {
            "group_id": group_id,
            "title": str(raw.get("title") or allowed[group_id]["title"])[:500],
            "solution": solution[:5000],
            "technical_detail": str(raw.get("technical_detail") or "")[:6000],
            "example": str(raw.get("example") or "")[:6000],
            "verification": str(raw.get("verification") or "")[:3000],
            "confidence": confidence,
            "effort": effort,
        }
    return accepted, [group_id for group_id in allowed if group_id not in accepted]


def _mark_latest_exchange_as_request_remediation(state: Any) -> None:
    for recorder in [state.recorder, *state.external_recorders]:
        if not getattr(recorder, "exchanges", None):
            continue
        latest = recorder.exchanges[-1]
        if latest.purpose != "REQUEST_REMEDIATION":
            recorder._exchanges[-1] = replace(latest, purpose="REQUEST_REMEDIATION")


def _call_ai_batch(
    *,
    audit_id: str,
    workspace: Any,
    context: Any,
    config: Any,
    groups: Sequence[Mapping[str, Any]],
    timeout: float,
) -> tuple[dict[str, dict[str, Any]], list[str], str | None, str | None, str | None]:
    from rasai import ai_orchestration_unification as orchestration
    from rasai import improvement_exchange_capture as capture
    from rasai import improvement_intelligence as improvement
    from rasai.accepted_audit_refinements import _deadline_candidate_call
    from rasai.ai_resilience import DECISION_FALLBACK, DECISION_STOP, DECISION_SUCCESS
    from rasai.m18_ai import AttemptStatus, ProviderDiagnostic, ProviderErrorClass
    from rasai.m18_persistence import attempt_governance

    group_ids = [str(group["group_id"]) for group in groups]
    schema = _solution_schema(group_ids)
    instructions = (
        "You are the RASAi remediation specialist for deterministic request/runtime error groups. "
        "The grouped facts, counts, URLs, statuses and observed impacts are immutable evidence. "
        "Return exactly one practical remediation per supplied group_id. Weigh recurrence, first/third-party scope, "
        "observed versus potential impact and implementation risk. confidence is confidence that the proposed remediation "
        "is applicable to this evidence, not confidence in the deterministic observation. technical_detail must explain what "
        "to inspect/change; example should contain a concise code/config example only when technically justified; otherwise "
        "state what concrete artifact should be inspected. verification must be reproducible. Do not invent public URLs or "
        "new observed facts; the official reference is already supplied by RASAi."
    )
    user_text = "Grouped deterministic request/runtime evidence:\n" + json.dumps(
        [_group_payload(group) for group in groups], ensure_ascii=False, default=str
    )
    runtime = improvement._build_provider(config)
    hint = orchestration._token_hint(user_text, output_tokens=min(6000, 1200 + 450 * len(groups)))
    candidates = orchestration._provider_candidates(runtime, hint, scope="IMPROVEMENT_INTELLIGENCE")
    if not candidates:
        return {}, group_ids, None, None, "AI_PROVIDER_CHAIN_EXHAUSTED"

    state = capture._CaptureState(
        audit_id=audit_id,
        workspace=workspace,
        recorder=capture.AiExchangeRecorder(),
        external_recorders=[],
    )
    token = capture._STATE.set(state)
    last_reason: str | None = None
    try:
        for index, provider in enumerate(candidates, 1):
            payload = orchestration._structured_payload(
                provider,
                schema_name="rasai_request_remediation",
                instructions=instructions,
                user_text=user_text,
                schema=schema,
            )
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_hash = orchestration.sha256(body).hexdigest()
            started = orchestration.datetime.now(orchestration.timezone.utc)
            raw, usage, diagnostic, status, duration_ms = _deadline_candidate_call(
                provider,
                body=body,
                timeout=timeout,
                candidate_call=orchestration._candidate_call,
            )
            _mark_latest_exchange_as_request_remediation(state)
            accepted: dict[str, dict[str, Any]] = {}
            missing = list(group_ids)
            if status is AttemptStatus.SUCCESS and raw is not None:
                try:
                    extracted = orchestration._provider_extract(provider, raw)
                    accepted, missing = _validate_solutions(extracted, groups)
                    if not accepted:
                        status = AttemptStatus.CONTRACT_ERROR
                        diagnostic = ProviderDiagnostic(
                            ProviderErrorClass.CONTRACT_ERROR,
                            error_type="RequestRemediationValidation",
                            error_code="REQUEST_REMEDIATION_OUTPUT_INVALID",
                        )
                except Exception as exc:
                    status = AttemptStatus.CONTRACT_ERROR
                    diagnostic = ProviderDiagnostic(
                        ProviderErrorClass.CONTRACT_ERROR,
                        error_type=type(exc).__name__,
                        error_code="REQUEST_REMEDIATION_OUTPUT_INVALID",
                    )
            decision = DECISION_SUCCESS if accepted else (DECISION_FALLBACK if index < len(candidates) else DECISION_STOP)
            attempt = orchestration._attempt(
                provider,
                index=index,
                started=started,
                duration_ms=duration_ms,
                status=status,
                diagnostic=diagnostic,
                usage=usage,
                request_hash=request_hash,
                contract=REQUEST_REMEDIATION_CONTRACT,
                url=context.url,
                snapshot_id=context.snapshot_id,
                decision=decision,
            )
            attempt = replace(
                attempt,
                request_message_summary=(
                    f"contract={REQUEST_REMEDIATION_CONTRACT};groups={len(groups)};"
                    f"accepted={len(accepted)};missing={len(missing)}"
                ),
            )
            with attempt_governance(operation="REQUEST_REMEDIATION"):
                improvement._persist_attempt(workspace, audit_id, context, attempt)
            if accepted:
                return accepted, missing, str(provider.name), str(provider.model), None
            last_reason = diagnostic.reason if diagnostic is not None else "AI_PROVIDER_UNAVAILABLE"
        return {}, group_ids, None, None, last_reason or "AI_PROVIDER_CHAIN_EXHAUSTED"
    finally:
        try:
            capture._persist_state(state)
        finally:
            capture._STATE.reset(token)


def _persist_ai_rows(
    database: Any,
    audit_id: str,
    groups: Sequence[Mapping[str, Any]],
    solutions: Mapping[str, Mapping[str, Any]],
    *,
    provider: str | None,
    model: str | None,
    reason: str | None,
) -> None:
    connection = sqlite3.connect(database)
    try:
        _ensure_schema(connection)
        now = datetime.now(timezone.utc).isoformat()
        with connection:
            for group in groups:
                group_id = str(group["group_id"])
                solution = solutions.get(group_id)
                connection.execute("DELETE FROM request_remediation_ai WHERE group_id=?", (group_id,))
                if solution:
                    connection.execute(
                        "INSERT INTO request_remediation_ai VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            group_id, audit_id, group["evidence_fingerprint"], provider, model, "COMPLETE",
                            solution.get("title"), solution.get("solution"), solution.get("technical_detail"),
                            solution.get("example"), solution.get("verification"), solution.get("confidence"),
                            solution.get("effort"), None, now,
                        ),
                    )
                else:
                    connection.execute(
                        "INSERT INTO request_remediation_ai VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            group_id, audit_id, group["evidence_fingerprint"], provider, model, "UNAVAILABLE",
                            None, None, None, None, None, None, None, reason or "AI_SOLUTION_NOT_RETURNED", now,
                        ),
                    )
    finally:
        connection.close()


def _groups_needing_ai(database: Any, audit_id: str, groups: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        _ensure_schema(connection)
        rows = {str(row["group_id"]): dict(row) for row in connection.execute(
            "SELECT * FROM request_remediation_ai WHERE audit_id=?", (audit_id,)
        ).fetchall()}
    finally:
        connection.close()
    needed: list[dict[str, Any]] = []
    for group in groups:
        row = rows.get(str(group["group_id"]))
        if not row or row.get("status") != "COMPLETE" or row.get("evidence_fingerprint") != group.get("evidence_fingerprint"):
            needed.append(dict(group))
    return needed


def refresh_request_remediation(
    *,
    audit_id: str,
    workspace: Any,
    config: Any | None = None,
    run_ai: bool = True,
) -> list[dict[str, Any]]:
    from rasai import improvement_intelligence as improvement

    events, sample_universe = collect_request_error_evidence(workspace.database, audit_id)
    groups = group_request_error_evidence(events, sample_universe, audit_id=audit_id)
    persist_request_remediation_groups(workspace.database, audit_id, groups)
    if not groups or not run_ai:
        return groups
    cfg = config or improvement.ImprovementConfig.from_environment()
    if not getattr(cfg, "enabled", False):
        return groups
    needed = _groups_needing_ai(workspace.database, audit_id, groups)
    if not needed:
        return groups
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        context = improvement._target_context(connection, audit_id, workspace)
    finally:
        connection.close()
    by_id = {str(group["group_id"]): group for group in groups}
    for offset in range(0, len(needed), AI_BATCH_SIZE):
        batch = needed[offset : offset + AI_BATCH_SIZE]
        solutions, missing, provider, model, reason = _call_ai_batch(
            audit_id=audit_id,
            workspace=workspace,
            context=context,
            config=cfg,
            groups=batch,
            timeout=float(getattr(cfg, "timeout_seconds", 240.0)),
        )
        if missing and solutions:
            repair_groups = [by_id[group_id] for group_id in missing if group_id in by_id]
            repaired, still_missing, repair_provider, repair_model, repair_reason = _call_ai_batch(
                audit_id=audit_id,
                workspace=workspace,
                context=context,
                config=cfg,
                groups=repair_groups,
                timeout=min(45.0, max(15.0, float(getattr(cfg, "timeout_seconds", 240.0)) * 0.25)),
            )
            solutions.update(repaired)
            missing = still_missing
            provider = provider or repair_provider
            model = model or repair_model
            reason = repair_reason if missing else None
        _persist_ai_rows(
            workspace.database,
            audit_id,
            batch,
            solutions,
            provider=provider,
            model=model,
            reason=reason if missing else None,
        )
    return groups


def _load_persisted_groups(database: Any, audit_id: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "request_remediation_groups"):
            return [], {}, {}
        groups = [dict(row) for row in connection.execute(
            "SELECT * FROM request_remediation_groups WHERE audit_id=? ORDER BY recurrence_ratio DESC,occurrence_count DESC,title",
            (audit_id,),
        ).fetchall()]
        ai = {str(row["group_id"]): dict(row) for row in connection.execute(
            "SELECT * FROM request_remediation_ai WHERE audit_id=?", (audit_id,)
        ).fetchall()} if _table_exists(connection, "request_remediation_ai") else {}
        evidence: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if _table_exists(connection, "request_remediation_evidence"):
            for row in connection.execute(
                "SELECT * FROM request_remediation_evidence WHERE audit_id=? ORDER BY group_id,sample_key,evidence_id",
                (audit_id,),
            ).fetchall():
                evidence[str(row["group_id"])].append(dict(row))
        return groups, ai, evidence
    finally:
        connection.close()


def _json_list(value: Any) -> list[Any]:
    parsed = _safe_json(value, [])
    return list(parsed) if isinstance(parsed, list) else []


def _problem_rows(events: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    buckets: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        normalized = {
            "family": _family(str(event.get("error_type") or ""), event.get("http_status"), str(event.get("message") or "")),
            "normalized_url": event.get("normalized_url"),
            "http_status": event.get("http_status"),
            "resource_type": event.get("resource_type"),
            "message": event.get("message"),
        }
        buckets[_problem_signature(normalized)].append(event)
    rows: list[tuple[Any, ...]] = []
    for members in buckets.values():
        first = members[0]
        source = first.get("normalized_url") or first.get("source_url") or first.get("message") or "—"
        rows.append((
            source,
            first.get("http_status") or "—",
            first.get("error_type") or "—",
            len(members),
            len({str(item.get("sample_key") or "") for item in members}),
            " · ".join(sorted({str(item.get("source_catalog") or "") for item in members if item.get("source_catalog")})) or "—",
        ))
    return sorted(rows, key=lambda row: (-int(row[3]), str(row[0])))


def request_remediation_report_html(database: Any, audit_id: str, analysis: Any) -> str:
    groups, ai_rows, evidence = _load_persisted_groups(database, audit_id)
    if not groups:
        events, sample_universe = collect_request_error_evidence(database, audit_id)
        computed = group_request_error_evidence(events, sample_universe, audit_id=audit_id)
        if not computed:
            return ""
        groups = [
            {
                **group,
                "source_catalogs_json": json.dumps(group["source_catalogs"], ensure_ascii=False),
                "resource_urls_json": json.dumps(group["resource_urls"], ensure_ascii=False),
                "http_statuses_json": json.dumps(group["http_statuses"], ensure_ascii=False),
                "error_types_json": json.dumps(group["error_types"], ensure_ascii=False),
                "observed_impacts_json": json.dumps(group["observed_impacts"], ensure_ascii=False),
                "potential_impacts_json": json.dumps(group["potential_impacts"], ensure_ascii=False),
            }
            for group in computed
        ]
        evidence = {str(group["group_id"]): list(group["events"]) for group in computed}

    rows: list[Sequence[Any]] = []
    modals: list[str] = []
    total_occurrences = sum(int(group.get("occurrence_count") or 0) for group in groups)
    total_problems = sum(int(group.get("problem_count") or 0) for group in groups)
    for index, group in enumerate(groups, 1):
        group_id = str(group.get("group_id") or "")
        ai = ai_rows.get(group_id, {})
        anchor_token = re.sub(r"[^a-z0-9_-]+", "-", group_id.casefold()).strip("-") or str(index)
        modal_id = f"request-remediation-{anchor_token}"
        title = ai.get("title") or group.get("title") or "Remediação técnica"
        ratio = float(group.get("recurrence_ratio") or 0.0)
        confidence = "—"
        if ai.get("confidence") is not None:
            confidence = f"{float(ai['confidence']) * 100:.0f}%"
        sources = " · ".join(str(value) for value in _json_list(group.get("source_catalogs_json"))) or "—"
        observed = " · ".join(str(value) for value in _json_list(group.get("observed_impacts_json"))) or "Diagnóstico técnico"
        rows.append((
            title,
            group.get("problem_count") or 0,
            group.get("occurrence_count") or 0,
            f"{group.get('affected_sample_count') or 0}/{group.get('total_sample_count') or 0}",
            f"{ratio * 100:.1f}% · {group.get('recurrence_class') or '—'}",
            observed,
            sources,
            confidence,
            analysis._modal_button(modal_id, "Ver solução"),
        ))
        body = analysis._kv((
            ("Grupo determinístico", group_id),
            ("Família técnica", group.get("family") or "—"),
            ("Escopo da origem", str(group.get("party_scope") or "—").replace("FIRST_PARTY", "Primeira parte").replace("THIRD_PARTY", "Terceiro").replace("UNKNOWN", "Indeterminado")),
            ("Problemas distintos", group.get("problem_count") or 0),
            ("Ocorrências", group.get("occurrence_count") or 0),
            ("Amostras afetadas", f"{group.get('affected_sample_count') or 0}/{group.get('total_sample_count') or 0}"),
            ("Recorrência", f"{ratio * 100:.1f}% · {group.get('recurrence_class') or '—'}"),
            ("Impacto observado", observed),
            ("Riscos / impactos potenciais", " · ".join(str(value) for value in _json_list(group.get("potential_impacts_json"))) or "—"),
            ("Catálogos de origem", sources),
        ))
        if ai and ai.get("status") == "COMPLETE":
            body += "<h3>Solução ponderada por IA</h3>" + analysis._kv((
                ("Solução", ai.get("solution") or "—"),
                ("Confiança de aplicabilidade", confidence),
                ("Esforço", analysis._level_label(ai.get("effort"))),
                ("Detalhamento técnico", ai.get("technical_detail") or "—"),
                ("Como validar", ai.get("verification") or "—"),
            ))
            if ai.get("example"):
                body += "<h3>Exemplo técnico</h3><div class='pre'>" + escape(str(ai.get("example"))) + "</div>"
        else:
            reason = ai.get("reason") if ai else "Improvement Intelligence não executada para este grupo."
            body += "<div class='notice'>A evidência e o agrupamento são determinísticos. A orientação de IA não está disponível para este grupo: " + escape(str(reason or "indisponível")) + "</div>"
        reference_url = str(group.get("public_reference_url") or "")
        reference_label = str(group.get("public_reference_label") or "Referência pública")
        if reference_url:
            body += f"<h3>Referência pública</h3><p><a href='{escape(reference_url)}' target='_blank' rel='noopener noreferrer'>{escape(reference_label)}</a></p>"
        group_events = evidence.get(group_id, [])
        problems = _problem_rows(group_events)
        if problems:
            body += "<h3>Problemas cobertos por esta solução</h3>" + analysis._table(
                ("Recurso / erro", "HTTP", "Tipo", "Ocorrências", "Amostras", "Origem"),
                problems,
                sortable=True,
                page_size=10 if len(problems) > 10 else None,
            )
        if group_events:
            occurrence_rows = []
            for item in group_events:
                first_party = "Sim" if item.get("first_party") in (1, True) else "Não" if item.get("first_party") in (0, False) else "Indeterminado"
                occurrence_rows.append((
                    item.get("source_catalog") or "—",
                    item.get("run_index") or "—",
                    item.get("device") or "—",
                    item.get("error_type") or "—",
                    item.get("source_url") or item.get("message") or "—",
                    item.get("http_status") or "—",
                    item.get("resource_type") or "—",
                    first_party,
                    "Sim" if item.get("error_forced_frustrated") in (1, True) else "Não",
                ))
            body += "<details><summary>Ver ocorrências individuais (" + str(len(group_events)) + ")</summary><div class='detail-body'>" + analysis._table(
                ("Origem", "Amostra", "Dispositivo", "Tipo", "Request / mensagem", "HTTP", "Recurso", "Primeira parte", "Forçou Apdex"),
                occurrence_rows,
                sortable=True,
                page_size=10 if len(occurrence_rows) > 10 else None,
            ) + "</div></details>"
        modals.append(analysis._modal(
            modal_id,
            str(title),
            "Uma solução consolidada para N problemas; evidências permanecem rastreáveis à origem",
            body,
        ))

    intro = (
        "<h2>Remediações de carregamento e execução</h2>"
        "<p class='section-lead'>Erros de request, resposta HTTP, console e JavaScript são normalizados e agrupados deterministicamente por família de solução. "
        "O CAT-09 apresenta uma única remediação para cada grupo e mantém os eventos individuais como evidência subordinada, evitando repetir cada erro como uma recomendação separada. "
        "A IA sugere a solução; contagens, recorrência, origem e impactos observados não são inferidos pela IA.</p>"
        "<div class='metric-grid'>"
        + analysis._metric("Grupos de solução", len(groups))
        + analysis._metric("Problemas distintos", total_problems)
        + analysis._metric("Ocorrências consolidadas", total_occurrences)
        + analysis._metric("Grupos com solução IA", sum(1 for group in groups if ai_rows.get(str(group.get('group_id')), {}).get('status') == 'COMPLETE'))
        + "</div>"
    )
    return intro + analysis._table(
        ("Solução", "Problemas", "Ocorrências", "Amostras", "Recorrência", "Impacto observado", "Origem", "Confiança IA", "Detalhe"),
        rows,
        sortable=bool(rows),
        page_size=10 if len(rows) > 10 else None,
    ) + "".join(modals)


def _patch_execute() -> None:
    from rasai import improvement_intelligence as improvement

    current = improvement.execute_improvement_intelligence
    if getattr(current, "_rasai_request_remediation", False):
        return

    def execute(*args: Any, **kwargs: Any):
        result = current(*args, **kwargs)
        audit_id = str(kwargs.get("audit_id") or (args[0] if args else ""))
        workspace = kwargs.get("workspace")
        config = kwargs.get("config")
        if audit_id and workspace is not None:
            try:
                refresh_request_remediation(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=config,
                    run_ai=str(getattr(result, "status", "")).upper() in {"COMPLETE", "COMPLETE_WITH_LIMITATIONS"},
                )
            except Exception:
                # CAT-09 enrichment is advisory and must not change CAT-08 fulfillment/scoring.
                pass
        return result

    execute._rasai_request_remediation = True
    execute._rasai_original = current
    improvement.execute_improvement_intelligence = execute
    for module_name in ("rasai.improvement_intelligence_runtime", "rasai.improvement_intelligence_console"):
        module = sys.modules.get(module_name)
        if module is not None and getattr(module, "execute_improvement_intelligence", None) is current:
            module.execute_improvement_intelligence = execute


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _patch_execute()
    _INSTALLED = True


__all__ = [
    "REQUEST_REMEDIATION_CONTRACT",
    "collect_request_error_evidence",
    "group_request_error_evidence",
    "persist_request_remediation_groups",
    "refresh_request_remediation",
    "request_remediation_report_html",
    "_validate_solutions",
    "install",
]
