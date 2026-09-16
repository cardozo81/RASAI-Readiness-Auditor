"""Catalog-driven HTML report experiment.

This generator is intentionally isolated from the current ``report/`` mini-site.  It
reads only persisted AUD data and writes only ``report-catalog/``.  It never invokes
collectors, providers, AI, scoring, or legacy HTML renderers.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

from rasai.audit_catalog import CATALOGS, CATALOG_BY_ID
from rasai.audit_configuration_reuse import configuration_hash
from rasai.catalog_report_contract import (
    CATALOG_PAGE_BY_ID,
    CATALOG_REPORT_CONTRACT_VERSION,
    CATALOG_REPORT_DIR,
    CATALOG_REPORT_PAGES,
    CatalogReportPage,
)


_CSS = r"""
:root{--nav:286px;--bg:#f6f8fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#e2e7ef;--blue:#3157c8;--green:#187a45;--amber:#9a6200;--red:#b42318;--cyan:#087a8c;--radius:14px;--shadow:0 1px 3px rgba(16,24,40,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}a{color:var(--blue)}.app-nav{position:fixed;inset:0 auto 0 0;width:var(--nav);overflow:auto;padding:20px 14px;background:#111827;color:#d6dfeb}.brand{padding:0 9px 15px;border-bottom:1px solid #2b3547;margin-bottom:12px}.brand small{display:block;color:#93a4ba;text-transform:uppercase;letter-spacing:.1em;font-size:.68rem}.brand strong{display:block;color:#fff;margin-top:4px}.nav-group{margin:14px 9px 5px;color:#8798ae;font-size:.66rem;text-transform:uppercase;letter-spacing:.1em}.app-nav a{display:block;color:#cbd5e1;text-decoration:none;padding:8px 10px;margin:3px 0;border-radius:8px;font-size:.82rem}.app-nav a:hover,.app-nav a:focus,.app-nav a.active{background:#253146;color:#fff}.app-main{margin-left:var(--nav);width:calc(100% - var(--nav));max-width:1500px;padding:28px 34px 60px}.hero,.panel,.card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}.hero{padding:24px 26px;margin-bottom:16px}.hero .eyebrow,.kicker{font-size:.7rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700}.hero h1{font-size:clamp(1.7rem,2.3vw,2.3rem);line-height:1.15;margin:.28rem 0 .6rem}.hero p{color:#4b5565;max-width:1000px}.panel{padding:19px 21px;margin:14px 0}.panel h2{font-size:1.26rem;margin:.15rem 0 .75rem}.panel h3{font-size:1rem;margin:.2rem 0 .55rem}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:11px}.card{padding:14px}.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:9px}.metric{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:11px}.metric small{display:block;color:var(--muted);font-size:.7rem}.metric strong{display:block;margin-top:3px;overflow-wrap:anywhere}.badge{display:inline-flex;align-items:center;border-radius:999px;padding:4px 8px;font-size:.68rem;font-weight:750;background:#eef1f5;color:#4b5565}.badge.good{background:#e9f7ee;color:var(--green)}.badge.warn{background:#fff3d7;color:#805200}.badge.bad{background:#feeceb;color:var(--red)}.badge.info{background:#eaf1ff;color:#244ea4}.badge.neutral{background:#eef0f3;color:#596274}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;background:#fff}table{width:100%;border-collapse:collapse;font-size:.83rem}th,td{text-align:left;vertical-align:top;padding:9px 10px;border-bottom:1px solid #edf0f4}th{background:#f8fafc;color:#4b5565;text-transform:uppercase;letter-spacing:.03em;font-size:.69rem}tr:last-child td{border-bottom:0}.notice{border:1px solid #cbd8f5;background:#f2f6ff;border-radius:10px;padding:11px 13px;margin:10px 0}.notice.warn{border-color:#ecd09d;background:#fff8e9}.notice.bad{border-color:#efb7b2;background:#fff1f0}.notice.good{border-color:#b9dec5;background:#edf8f0}.muted{color:var(--muted)}.mono,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}.outline{position:sticky;top:0;z-index:5;background:rgba(246,248,251,.96);backdrop-filter:blur(7px);padding:8px 0 10px;display:flex;gap:6px;overflow:auto}.outline a{white-space:nowrap;text-decoration:none;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 9px;font-size:.72rem;color:#46536a}.catalog-state{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}.source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}.source-item{border:1px solid var(--line);border-radius:9px;padding:9px;background:#fbfcfe}.source-item small{display:block;color:var(--muted)}details{border:1px solid var(--line);border-radius:9px;background:#fbfcfd;margin:8px 0}summary{cursor:pointer;padding:9px 11px;font-weight:650}details>.detail-body{padding:0 11px 11px}.footer{margin-top:24px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:.74rem}
@media(max-width:900px){.app-nav{position:sticky;top:0;width:auto;inset:auto;display:flex;gap:5px;overflow:auto;padding:8px;z-index:20}.brand,.nav-group{display:none}.app-nav nav{display:flex;min-width:max-content}.app-nav a{background:#253146;margin:0 2px}.app-main{margin:0;width:100%;padding:18px 12px 40px}.outline{top:47px}}
@media print{body{background:#fff}.app-nav,.outline{display:none}.app-main{margin:0;width:100%;max-width:none;padding:0}.hero,.panel,.card{box-shadow:none;break-inside:avoid}}
"""

_STATUS_SUCCESS = {"SUCCESS", "COMPLETE", "COMPLETED", "READY", "MEASURED", "FINAL", "CONSOLIDATED"}
_STATUS_FAILURE = {"FAILED_RETRYABLE", "FAILED_PERMANENT", "FAILED_FATAL", "BLOCKED", "ERROR", "FAILURE", "UNAVAILABLE"}
_STATUS_PENDING = {"PENDING", "RUNNING", "WAITING_FOR_DATA", "REQUESTED_NOT_EXECUTED", "PROCESSING", "PARTIAL"}
_STATUS_NEUTRAL = {"DISABLED", "NOT_APPLICABLE", "NOT_REQUESTED", "SKIPPED"}

_CAT_TABLE_PATTERNS: dict[str, tuple[str, ...]] = {
    "CAT-01": ("rule_execut", "standards_", "score", "finding", "evidence"),
    "CAT-02": ("web_performance_observation", "accessib", "finding"),
    "CAT-03": ("structured", "content", "semantic", "rule_execut", "finding", "evidence"),
    "CAT-04": ("web_performance_", "lighthouse_", "crux"),
    "CAT-05": ("serp_", "gsc_", "search_", "observability", "ai_visibility", "external_"),
    "CAT-06": ("synthetic_apdex_",),
    "CAT-07": ("synthetic_ux_apdex_", "experience_apdex"),
    "CAT-08": ("improvement", "deep_analysis"),
    "CAT-09": ("remediation", "content_suggestion"),
}

_DIMENSION_CONTEXT = {
    "DISCOVERY_ACCESS": "CAT-01", "TECHNICAL_ACCESSIBILITY": "CAT-01", "INDEXABILITY": "CAT-01",
    "CONTENT_EXTRACTABILITY": "CAT-01", "SEMANTIC_STRUCTURE": "CAT-03", "ENTITY_CLARITY": "CAT-03",
    "STRUCTURED_DATA": "CAT-03", "ANSWERABILITY": "CAT-03", "CITATION_READINESS": "CAT-03",
    "EVIDENCE_TRUST": "CAT-03", "INTENT_COVERAGE": "CAT-03", "CONTENT_VALUE": "CAT-03",
}

_DIMENSION_LABELS = {
    "OVERALL_READINESS": "SARI · Search & AI Readiness",
    "DISCOVERY_ACCESS": "Acesso e descoberta", "TECHNICAL_ACCESSIBILITY": "Acesso e descoberta",
    "INDEXABILITY": "Indexabilidade e canonicalização", "CONTENT_EXTRACTABILITY": "Renderização e extração",
    "SEMANTIC_STRUCTURE": "Estrutura semântica", "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados", "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação", "EVIDENCE_TRUST": "Evidência e confiança",
    "INTENT_COVERAGE": "Cobertura de intenção", "CONTENT_VALUE": "Valor de conteúdo",
}

_WEB_METRICS = {
    "performance_score": ("Lighthouse Performance", "índice"),
    "accessibility_score": ("Lighthouse Accessibility", "índice"),
    "best_practices_score": ("Lighthouse Best Practices", "índice"),
    "seo_score": ("Lighthouse SEO", "índice"),
    "lcp_ms": ("LCP", "ms"), "field_lcp_ms": ("LCP de campo", "ms"),
    "inp_ms": ("INP", "ms"), "field_inp_ms": ("INP de campo", "ms"),
    "cls": ("CLS", ""), "field_cls": ("CLS de campo", ""),
    "ttfb_ms": ("TTFB", "ms"), "field_ttfb_ms": ("TTFB de campo", "ms"),
    "fcp_ms": ("FCP", "ms"), "speed_index_ms": ("Speed Index", "ms"),
    "total_blocking_time_ms": ("Total Blocking Time", "ms"), "tbt_ms": ("Total Blocking Time", "ms"),
}

_APDEX_FIELDS = {
    "apdex": "Apdex", "apdex_score": "Apdex", "score": "Apdex",
    "threshold_seconds": "Threshold T", "threshold": "Threshold T",
    "satisfied": "Amostras satisfatórias", "satisfied_count": "Amostras satisfatórias",
    "tolerating": "Amostras toleráveis", "tolerating_count": "Amostras toleráveis",
    "frustrated": "Amostras frustradas", "frustrated_count": "Amostras frustradas",
    "sample_count": "Amostras válidas", "samples": "Amostras válidas",
}


@dataclass(slots=True)
class _ReportData:
    audit_id: str
    audit: dict[str, Any]
    configuration: dict[str, Any]
    config_hash: str
    computed_hash: str
    selected: set[str]
    catalog_items: dict[str, dict[str, Any]]
    tables: set[str]
    scores: list[dict[str, Any]]
    work_items: list[dict[str, Any]]
    targets: tuple[str, ...]


def _plain(value: Any) -> str:
    return "" if value is None else str(value)


def _safe_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _rows(connection: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, tuple(params)).fetchall())
    except sqlite3.Error:
        return []


def _dict_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _first_audit_row(connection: sqlite3.Connection, audit_id: str) -> dict[str, Any]:
    if not _table_exists(connection, "audits") or "audit_id" not in _columns(connection, "audits"):
        return {}
    rows = _rows(connection, "SELECT * FROM audits WHERE audit_id=? LIMIT 1", (audit_id,))
    return dict(rows[0]) if rows else {}


def _load_configuration(connection: sqlite3.Connection, audit_id: str) -> tuple[dict[str, Any], str, str]:
    if not _table_exists(connection, "audit_execution_configurations"):
        return {}, "", ""
    cols = _columns(connection, "audit_execution_configurations")
    if "configuration_json" not in cols:
        return {}, "", ""
    hash_sql = "configuration_hash" if "configuration_hash" in cols else "'' AS configuration_hash"
    rows = _rows(connection, f"SELECT configuration_json,{hash_sql} FROM audit_execution_configurations WHERE audit_id=? LIMIT 1", (audit_id,))
    if not rows:
        return {}, "", ""
    parsed = _safe_json(rows[0]["configuration_json"], {})
    configuration = dict(parsed) if isinstance(parsed, Mapping) else {}
    persisted = str(rows[0]["configuration_hash"] or "")
    computed = configuration_hash(configuration) if configuration else ""
    return configuration, persisted, computed


def _score_rows(connection: sqlite3.Connection, audit_id: str) -> list[dict[str, Any]]:
    if not _table_exists(connection, "scores") or "audit_id" not in _columns(connection, "scores"):
        return []
    return _dict_rows(_rows(connection, "SELECT * FROM scores WHERE audit_id=?", (audit_id,)))


def _work_rows(connection: sqlite3.Connection, audit_id: str) -> list[dict[str, Any]]:
    table = "audit_fulfillment_work_items"
    if not _table_exists(connection, table) or "audit_id" not in _columns(connection, table):
        return []
    return _dict_rows(_rows(connection, f"SELECT * FROM {table} WHERE audit_id=?", (audit_id,)))


def _targets(connection: sqlite3.Connection, configuration: Mapping[str, Any], audit_id: str) -> tuple[str, ...]:
    raw = configuration.get("targets")
    if isinstance(raw, list):
        values = tuple(str(item).strip() for item in raw if str(item).strip())
        if values:
            return values
    if _table_exists(connection, "pages") and "audit_id" in _columns(connection, "pages"):
        cols = _columns(connection, "pages")
        column = "normalized_url" if "normalized_url" in cols else "url" if "url" in cols else None
        if column:
            values = tuple(str(row[0]).strip() for row in _rows(connection, f"SELECT {column} FROM pages WHERE audit_id=?", (audit_id,)) if row[0])
            if values:
                return tuple(dict.fromkeys(values))
    return ()


def _load_data(audit_id: str, database: Path) -> _ReportData:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        configuration, persisted, computed = _load_configuration(connection, audit_id)
        catalog_block = configuration.get("audit_catalog") if isinstance(configuration.get("audit_catalog"), Mapping) else {}
        selected = {str(item).strip().upper() for item in catalog_block.get("selected", []) if str(item).strip()} if isinstance(catalog_block, Mapping) else set()
        raw_items = catalog_block.get("items", []) if isinstance(catalog_block, Mapping) else []
        items = {
            str(item.get("id", "")).upper(): dict(item)
            for item in raw_items
            if isinstance(item, Mapping) and str(item.get("id", "")).strip()
        }
        return _ReportData(
            audit_id=audit_id,
            audit=_first_audit_row(connection, audit_id),
            configuration=configuration,
            config_hash=persisted,
            computed_hash=computed,
            selected=selected,
            catalog_items=items,
            tables=tables,
            scores=_score_rows(connection, audit_id),
            work_items=_work_rows(connection, audit_id),
            targets=_targets(connection, configuration, audit_id),
        )
    finally:
        connection.close()


def _audit_count(connection: sqlite3.Connection, table: str, audit_id: str) -> int:
    cols = _columns(connection, table)
    if "audit_id" not in cols:
        return 0
    rows = _rows(connection, f"SELECT COUNT(*) FROM {table} WHERE audit_id=?", (audit_id,))
    return int(rows[0][0]) if rows else 0


def _catalog_sources(database: Path, data: _ReportData, catalog_id: str) -> list[tuple[str, int]]:
    patterns = _CAT_TABLE_PATTERNS[catalog_id]
    connection = sqlite3.connect(database)
    try:
        output: list[tuple[str, int]] = []
        for table in sorted(data.tables):
            lower = table.casefold()
            if not any(pattern in lower for pattern in patterns):
                continue
            count = _audit_count(connection, table, data.audit_id)
            if count:
                output.append((table, count))
        return output
    finally:
        connection.close()


def _normalize_component(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _work_for_catalog(data: _ReportData, catalog_id: str) -> list[dict[str, Any]]:
    hints = {
        "CAT-01": ("DOMAIN", "DISCOVERY", "STANDARDS", "CRAWL", "ROBOTS", "SITEMAP"),
        "CAT-02": ("ACCESSIB",),
        "CAT-03": ("CONTENT", "SEMANTIC", "STRUCTURED"),
        "CAT-04": ("WEB_PERFORMANCE", "LIGHTHOUSE", "PAGESPEED", "CRUX"),
        "CAT-05": ("SEARCH", "SERP", "GSC", "AI_VISIBILITY", "OBSERVABILITY"),
        "CAT-06": ("SYNTHETIC_APDEX", "APDEX_NAVIGATION"),
        "CAT-07": ("EXPERIENCE_APDEX", "SYNTHETIC_UX_APDEX", "APDEX_EXPERIENCE"),
        "CAT-08": ("IMPROVEMENT", "DEEP_ANALYSIS"),
        "CAT-09": ("REMEDIATION",),
    }[catalog_id]
    rows: list[dict[str, Any]] = []
    for row in data.work_items:
        component = _normalize_component(row.get("component"))
        if any(hint in component for hint in hints):
            rows.append(row)
    return rows


def _aggregate_work_status(rows: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    if not rows:
        return "", "neutral"
    states = {_normalize_component(row.get("status")) for row in rows}
    if states & _STATUS_FAILURE:
        return ("PARCIAL" if states & _STATUS_SUCCESS else "FALHA"), ("warn" if states & _STATUS_SUCCESS else "bad")
    if states & _STATUS_PENDING:
        return "PARCIAL / PENDENTE", "warn"
    if states and states <= _STATUS_NEUTRAL:
        return "NÃO EXECUTADO / NÃO APLICÁVEL", "neutral"
    if states & _STATUS_SUCCESS:
        return "CONCLUÍDO", "good"
    return "ESTADO PERSISTIDO", "info"


def _catalog_status(database: Path, data: _ReportData, catalog_id: str) -> tuple[str, str, str]:
    if catalog_id not in data.selected:
        return "NÃO SOLICITADO", "neutral", "O catálogo não fazia parte do plano congelado desta AUD."
    work = _work_for_catalog(data, catalog_id)
    status, tone = _aggregate_work_status(work)
    if status:
        return status, tone, f"{len(work)} item(ns) de execução persistido(s) relacionado(s) ao catálogo."
    sources = _catalog_sources(database, data, catalog_id)
    if sources:
        return "DADOS PERSISTIDOS", "good", f"{sum(count for _, count in sources)} registro(s) de domínio persistido(s)."
    return "SOLICITADO · SEM ESTADO CONSOLIDADO", "warn", "O plano solicitou o catálogo, mas esta projeção não encontrou um estado de execução consolidado."


def _tone_for_status(status: str) -> str:
    upper = status.upper()
    if any(token in upper for token in ("FALHA", "ERRO", "BLOQUEADO")):
        return "bad"
    if any(token in upper for token in ("PARCIAL", "PENDENTE", "LIMIT")):
        return "warn"
    if any(token in upper for token in ("CONCLU", "ÍNTEGRO", "DADOS PERSISTIDOS")):
        return "good"
    return "neutral"


def _badge(text: str, tone: str | None = None) -> str:
    tone = tone or _tone_for_status(text)
    return f"<span class='badge {escape(tone)}'>{escape(text)}</span>"


def _metric(label: str, value: Any, note: str = "") -> str:
    note_html = f"<small>{escape(note)}</small>" if note else ""
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(_plain(value) or '—')}</strong>{note_html}</div>"


def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]], *, empty: str = "Sem dados persistidos para este contexto.") -> str:
    if not rows:
        return f"<div class='notice'>{escape(empty)}</div>"
    head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{item if isinstance(item, _Html) else escape(_plain(item))}</td>" for item in row) + "</tr>" for row in rows)
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


class _Html(str):
    pass


def _section(section_id: str, title: str, body: str, kicker: str = "") -> str:
    kicker_html = f"<div class='kicker'>{escape(kicker)}</div>" if kicker else ""
    return f"<section id='{escape(section_id)}' class='panel'>{kicker_html}<h2>{escape(title)}</h2>{body}</section>"


def _outline(items: Sequence[tuple[str, str]]) -> str:
    return "<nav class='outline' aria-label='Atalhos desta página'>" + "".join(f"<a href='#{escape(anchor)}'>{escape(label)}</a>" for anchor, label in items) + "</nav>"


def _navigation(current: str) -> str:
    groups: list[str] = []
    last_group = None
    for page in CATALOG_REPORT_PAGES:
        if page.group != last_group:
            groups.append(f"<div class='nav-group'>{escape(page.group)}</div>")
            last_group = page.group
        active = " active" if page.filename == current else ""
        aria = " aria-current='page'" if active else ""
        groups.append(f"<a class='{active.strip()}' href='{escape(page.filename)}'{aria}>{escape(page.label)}</a>")
    return "".join(groups)


def _shell(page: CatalogReportPage, audit_id: str, body: str) -> str:
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{escape(page.label)} · RASAi</title><link rel='stylesheet' href='css/site.css'></head><body data-report-contract='{CATALOG_REPORT_CONTRACT_VERSION}' data-page='{escape(page.id)}'><aside class='app-nav' data-shared-report-menu='{CATALOG_REPORT_CONTRACT_VERSION}'><div class='brand'><small>RASAi · proposta por catálogos</small><strong>{escape(audit_id)}</strong></div><nav aria-label='Relatórios'>{_navigation(page.filename)}</nav></aside><main class='app-main'>{body}<footer class='footer'>Projeção read-only de dados persistidos · {CATALOG_REPORT_CONTRACT_VERSION} · o conjunto atual em <code>report/</code> permanece independente.</footer></main></body></html>"""


def _audit_hero(data: _ReportData, title: str, subtitle: str) -> str:
    status = str(data.audit.get("completion_status") or data.audit.get("status") or "—")
    target = data.targets[0] if data.targets else "—"
    project = str(data.audit.get("project_name") or "—")
    return f"<header class='hero'><div class='eyebrow'>Auditoria {escape(data.audit_id)}</div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p><div class='metric-grid'>{_metric('URL / alvo', target)}{_metric('Projeto', project)}{_metric('Estado da AUD', status)}{_metric('Catálogos solicitados', len(data.selected))}</div></header>"


def _score_value(row: Mapping[str, Any]) -> str:
    value = row.get("value")
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return _plain(value) or "—"


def _score_table(data: _ReportData, *, include_overall: bool = True, context: str | None = None) -> str:
    rows: list[Sequence[Any]] = []
    for row in sorted(data.scores, key=lambda item: (str(item.get("device", "")), str(item.get("dimension", "")))):
        dimension = str(row.get("dimension") or "")
        if not include_overall and dimension == "OVERALL_READINESS":
            continue
        if context and _DIMENSION_CONTEXT.get(dimension) != context:
            continue
        label = _DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title())
        rows.append((label, row.get("device", "—"), _score_value(row), row.get("coverage", "—"), row.get("confidence", "—"), row.get("consolidation_status", "—"), row.get("scoring_version", "—")))
    return _table(("Índice / dimensão", "Contexto", "Valor", "Coverage", "Confidence", "Consolidação", "Método"), rows)


def _overall_scores(data: _ReportData) -> list[dict[str, Any]]:
    return [row for row in data.scores if str(row.get("dimension", "")).upper() == "OVERALL_READINESS"]


def _format_web_value(name: str, value: Any) -> str:
    if value is None:
        return "—"
    label, unit = _WEB_METRICS[name]
    del label
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if name.endswith("_score") and 0 <= number <= 1:
        return f"{number * 100:.0f} / 100"
    if unit == "ms":
        return f"{number:g} ms"
    return f"{number:g}"


def _latest_row(connection: sqlite3.Connection, table: str, audit_id: str) -> dict[str, Any]:
    if not _table_exists(connection, table) or "audit_id" not in _columns(connection, table):
        return {}
    rows = _rows(connection, f"SELECT * FROM {table} WHERE audit_id=? LIMIT 1", (audit_id,))
    return dict(rows[0]) if rows else {}


def _web_metrics(database: Path, audit_id: str) -> list[tuple[str, str, str, str]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = _latest_row(connection, "web_performance_observations", audit_id)
    finally:
        connection.close()
    output = []
    for name, (label, _unit) in _WEB_METRICS.items():
        if name in row and row[name] is not None:
            output.append((label, _format_web_value(name, row[name]), "Web Performance", "Índice" if name.endswith("_score") else "Métrica"))
    return output


def _apdex_metrics(database: Path, audit_id: str, *, experience: bool) -> list[tuple[str, str, str, str]]:
    candidates = ("synthetic_ux_apdex_summaries", "synthetic_ux_apdex_runs") if experience else ("synthetic_apdex_summaries", "synthetic_apdex_runs")
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row: dict[str, Any] = {}
        for table in candidates:
            row = _latest_row(connection, table, audit_id)
            if row:
                break
    finally:
        connection.close()
    output = []
    for name, label in _APDEX_FIELDS.items():
        if name not in row or row[name] is None:
            continue
        value = row[name]
        if "threshold" in name:
            try:
                value = f"{float(value):g} s"
            except (TypeError, ValueError):
                pass
        output.append((label, str(value), "Apdex de experiência" if experience else "Apdex de navegação", "Índice" if "apdex" in name or name == "score" else "Métrica"))
    return output


def _serp_metrics(database: Path, data: _ReportData) -> list[tuple[str, str, str, str]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        output: list[tuple[str, str, str, str]] = []
        if _table_exists(connection, "serp_observations") and "audit_id" in _columns(connection, "serp_observations"):
            cols = _columns(connection, "serp_observations")
            count = _rows(connection, "SELECT COUNT(*) FROM serp_observations WHERE audit_id=?", (data.audit_id,))
            output.append(("Observações SERP", str(count[0][0] if count else 0), "SERP", "Contagem"))
            if "query" in cols:
                distinct = _rows(connection, "SELECT COUNT(DISTINCT query) FROM serp_observations WHERE audit_id=?", (data.audit_id,))
                output.append(("Termos observados", str(distinct[0][0] if distinct else 0), "SERP", "Contagem"))
            if _table_exists(connection, "serp_results") and "observation_id" in _columns(connection, "serp_results"):
                result_cols = _columns(connection, "serp_results")
                result = _rows(connection, "SELECT COUNT(*) FROM serp_results r JOIN serp_observations o ON o.observation_id=r.observation_id WHERE o.audit_id=?", (data.audit_id,))
                output.append(("Resultados SERP persistidos", str(result[0][0] if result else 0), "SERP", "Contagem"))
                if "position" in result_cols:
                    positions = _rows(connection, "SELECT MIN(r.position),MAX(r.position) FROM serp_results r JOIN serp_observations o ON o.observation_id=r.observation_id WHERE o.audit_id=?", (data.audit_id,))
                    if positions and positions[0][0] is not None:
                        output.append(("Faixa de posições observada", f"{positions[0][0]}–{positions[0][1]}", "SERP", "Métrica"))
        gsc_tables = [table for table in data.tables if table.casefold().startswith("gsc_")]
        gsc_total = sum(_audit_count(connection, table, data.audit_id) for table in gsc_tables)
        if gsc_total:
            output.append(("Registros GSC persistidos", str(gsc_total), "Google Search Console", "Contagem"))
        return output
    finally:
        connection.close()


def _catalog_metrics(database: Path, data: _ReportData, catalog_id: str) -> list[tuple[str, str, str, str]]:
    if catalog_id in {"CAT-01", "CAT-03"}:
        result = []
        for row in data.scores:
            dimension = str(row.get("dimension") or "")
            if _DIMENSION_CONTEXT.get(dimension) == catalog_id:
                result.append((_DIMENSION_LABELS.get(dimension, dimension), _score_value(row), "SARI/SCORE persistido", "Índice"))
        return result
    if catalog_id == "CAT-02":
        return [item for item in _web_metrics(database, data.audit_id) if item[0] == "Lighthouse Accessibility"]
    if catalog_id == "CAT-04":
        return _web_metrics(database, data.audit_id)
    if catalog_id == "CAT-05":
        return _serp_metrics(database, data)
    if catalog_id == "CAT-06":
        return _apdex_metrics(database, data.audit_id, experience=False)
    if catalog_id == "CAT-07":
        return _apdex_metrics(database, data.audit_id, experience=True)
    sources = _catalog_sources(database, data, catalog_id)
    return [("Registros persistidos", str(sum(count for _, count in sources)), CATALOG_BY_ID[catalog_id].label, "Contagem")] if sources else []


def _configuration_rows(data: _ReportData, catalog_id: str) -> list[Sequence[Any]]:
    item = data.catalog_items.get(catalog_id, {})
    rows: list[Sequence[Any]] = [
        ("Catálogo solicitado", "Sim" if catalog_id in data.selected else "Não", "Snapshot da AUD"),
        ("Uso de IA no plano", "Habilitado" if bool((data.configuration.get("audit_catalog") or {}).get("ai_enabled", False)) else "Desabilitado", "Snapshot da AUD"),
        ("Alvo", "; ".join(data.targets) if data.targets else "—", "Snapshot da AUD"),
    ]
    if item:
        rows.append(("Política de IA do catálogo", item.get("ai_mode", "NONE"), "Catálogo congelado"))
    if catalog_id == "CAT-05":
        search = data.configuration.get("search_intelligence")
        if isinstance(search, Mapping):
            rows.extend((
                ("Termos pesquisados", "; ".join(str(v) for v in search.get("queries", []) if str(v).strip()) or "—", "Pedido da execução"),
                ("Localidade SERP", search.get("region") or "Não definida", "Pedido da execução"),
                ("Profundidade desejada", f"Top {search.get('depth', '—')}", "Pedido da execução"),
                ("Dispositivo SERP", search.get("device", "—"), "Pedido da execução"),
                ("Análise de concorrentes", "Sim" if search.get("competitive", False) else "Não", "Pedido da execução"),
            ))
    return rows


def _catalog_body(database: Path, data: _ReportData, catalog_id: str) -> str:
    catalog = CATALOG_BY_ID[catalog_id]
    status, tone, status_detail = _catalog_status(database, data, catalog_id)
    item = data.catalog_items.get(catalog_id, {})
    sources = _catalog_sources(database, data, catalog_id)
    work = _work_for_catalog(data, catalog_id)
    metrics = _catalog_metrics(database, data, catalog_id)
    outline = _outline((("summary", "Resumo"), ("scope", "Escopo"), ("config", "Configuração"), ("execution", "Execução"), ("results", "Resultados"), ("evidence", "Evidências"), ("analysis", "Análise"), ("remediation", "Remediações"), ("technical", "Detalhes técnicos")))
    summary = _section("summary", "Resumo", f"<div class='catalog-state'><div><p>{escape(catalog.purpose)}</p><p class='muted'>{escape(catalog.expected_result)}</p></div>{_badge(status, tone)}</div><div class='metric-grid'>{_metric('Capacidades', len(catalog.capability_ids))}{_metric('Registros de domínio', sum(count for _, count in sources))}{_metric('Itens de execução', len(work))}{_metric('Métricas / índices visíveis', len(metrics))}</div>")
    capability_rows = [(capability, "Solicitada pelo CAT" if catalog_id in data.selected else "Não solicitada") for capability in catalog.capability_ids]
    scope = _section("scope", "Escopo solicitado", _table(("Capacidade", "Situação no plano"), capability_rows) + f"<div class='notice'>{escape(status_detail)}</div>")
    config = _section("config", "Configuração efetiva", _table(("Configuração", "Valor", "Origem"), _configuration_rows(data, catalog_id)) + "<p class='muted'>Esta página lê o snapshot congelado da AUD; não consulta a configuração atual da máquina.</p>")
    execution_rows = []
    for row in work:
        execution_rows.append((row.get("component", "—"), row.get("status", "—"), row.get("attempt_count", "—"), row.get("effective_result_ref", "—")))
    execution = _section("execution", "Execução", _table(("Componente", "Estado", "Tentativas", "Resultado persistido"), execution_rows, empty="Nenhum work-item específico foi persistido para este catálogo.") + f"<p>{_badge(status, tone)} {escape(status_detail)}</p>")
    result_rows = [(name, value, source, kind) for name, value, source, kind in metrics]
    results = _section("results", "Resultados", _table(("Indicador", "Valor", "Fonte", "Tipo"), result_rows, empty="Nenhum índice ou métrica específica foi materializada neste contexto. Isso não converte ausência de dados em falha do alvo."))
    evidence_html = "<div class='source-list'>" + "".join(f"<div class='source-item'><strong>{escape(table)}</strong><small>{count} registro(s) desta AUD</small></div>" for table, count in sources) + "</div>" if sources else "<div class='notice'>Nenhuma fonte persistida específica foi encontrada para este catálogo.</div>"
    evidence = _section("evidence", "Evidências", evidence_html + "<p class='muted'>As tabelas são referências de proveniência. Evidências e resultados continuam pertencendo ao audit.db e aos artefatos persistidos.</p>")
    ai_mode = str(item.get("ai_mode") or catalog.ai_mode)
    ai_enabled = bool((data.configuration.get("audit_catalog") or {}).get("ai_enabled", False))
    analysis_text = "IA não faz parte deste catálogo." if ai_mode == "NONE" else ("IA estava habilitada no plano desta AUD." if ai_enabled else "IA não foi habilitada para os enriquecimentos opcionais desta AUD.")
    analysis = _section("analysis", "Análise e interpretação", f"<div class='notice'><strong>Política:</strong> {escape(ai_mode)}. {escape(analysis_text)}</div><p>Esta superfície não cria análise nova. Quando houver conteúdo analítico persistido, ele deve permanecer identificado por origem e evidência; medições determinísticas não são reescritas pelo HTML.</p>")
    if catalog_id == "CAT-09":
        rem_body = "<p>Este catálogo é o contexto próprio das remediações persistidas. A aplicação de uma correção exige nova auditoria para produzir nova medição.</p>"
    else:
        rem_body = "<p>Correções relacionadas a este contexto são consolidadas em <a href='cat-09.html'>CAT-09 · Remediações</a>. Esta página não inventa ação quando não há achado persistido.</p>"
    remediation = _section("remediation", "Remediações", rem_body)
    tech_rows = [(table, count) for table, count in sources]
    technical = _section("technical", "Detalhes técnicos", f"<details><summary>Mostrar proveniência técnica</summary><div class='detail-body'>{_table(('Tabela / fonte', 'Registros desta AUD'), tech_rows, empty='Nenhuma tabela específica identificada.')}<p><strong>Capability IDs:</strong> <code>{escape(', '.join(catalog.capability_ids))}</code></p><p><strong>Readiness registrada no plano:</strong> {escape(str(item.get('status') or '—'))}</p><p><strong>Detalhe registrado no plano:</strong> {escape(str(item.get('detail') or '—'))}</p></div></details>")
    return _audit_hero(data, f"{catalog.id} · {catalog.label}", catalog.expected_result) + outline + summary + scope + config + execution + results + evidence + analysis + remediation + technical


def _overview_body(database: Path, data: _ReportData) -> str:
    catalog_rows = []
    for catalog in CATALOGS:
        status, tone, detail = _catalog_status(database, data, catalog.id)
        page = CATALOG_PAGE_BY_ID[catalog.id]
        catalog_rows.append((_Html(f"<a href='{escape(page.filename)}'><strong>{escape(catalog.id)} · {escape(catalog.label)}</strong></a>"), _Html(_badge(status, tone)), detail))
    index_rows: list[Sequence[Any]] = []
    for row in data.scores:
        dimension = str(row.get("dimension") or "")
        label = _DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title())
        context = "SARI" if dimension == "OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dimension, "Metodologia")
        link = "sari.html" if dimension == "OVERALL_READINESS" else (CATALOG_PAGE_BY_ID[context].filename if context in CATALOG_PAGE_BY_ID else "metrics.html")
        index_rows.append((_Html(f"<a href='{link}'>{escape(label)}</a>"), _score_value(row), row.get("device", "—"), "Índice", row.get("confidence", "—")))
    for catalog_id in ("CAT-04", "CAT-05", "CAT-06", "CAT-07"):
        for name, value, source, kind in _catalog_metrics(database, data, catalog_id):
            index_rows.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[catalog_id].filename}'>{escape(name)}</a>"), value, source, kind, "—"))
    body = _audit_hero(data, "Visão geral por catálogos", "A mesma taxonomia CAT-01…CAT-09 usada na preparação da auditoria é projetada sobre os dados persistidos, sem substituir o conjunto atual de relatórios.")
    body += _outline((("catalogs", "Catálogos"), ("indices", "Índices"), ("integrity", "Integridade")))
    body += _section("catalogs", "Catálogos da auditoria", _table(("Catálogo", "Estado", "Interpretação"), catalog_rows))
    body += _section("indices", "Índices e métricas evidentes", _table(("Índice / métrica", "Valor", "Contexto / fonte", "Tipo", "Confiança"), index_rows, empty="Nenhum índice ou métrica foi persistido ainda.") + "<p class='muted'>O catálogo completo, com definições e origem, está em <a href='metrics.html'>Índices e métricas</a>.</p>")
    integrity = "ÍNTEGRO" if data.config_hash and data.computed_hash == data.config_hash else "SNAPSHOT AUSENTE" if not data.config_hash else "HASH DIVERGENTE"
    body += _section("integrity", "Integridade e proveniência", f"<div class='metric-grid'>{_metric('Snapshot de configuração', integrity)}{_metric('Fonte de verdade', 'audit.db')}{_metric('Gerador', CATALOG_REPORT_CONTRACT_VERSION)}</div><div class='notice'>O gerador desta proposta é independente do gerador atual e não altera scoring, evidências, fulfillment ou arquivos de <code>report/</code>.</div>")
    return body


def _sari_body(data: _ReportData) -> str:
    overall = _overall_scores(data)
    cards = "".join(_metric(f"SARI · {row.get('device', 'contexto')}", _score_value(row), f"Coverage {row.get('coverage', '—')} · Confidence {row.get('confidence', '—')}") for row in overall)
    limitations: list[Sequence[Any]] = []
    for row in overall:
        raw = row.get("limitations")
        parsed = _safe_json(raw, [])
        values = parsed if isinstance(parsed, list) else ([raw] if raw else [])
        for item in values:
            limitations.append((row.get("device", "—"), item))
    versions = sorted({str(row.get("scoring_version")) for row in data.scores if row.get("scoring_version")})
    body = _audit_hero(data, "SARI · Search & AI Readiness Index", "Página sistêmica dedicada ao índice persistido, sua cobertura, confiança, dimensões e limitações. O HTML não recalcula o SARI.")
    body += _outline((("result", "Resultado"), ("composition", "Composição"), ("limitations", "Limitações"), ("method", "Método")))
    body += _section("result", "Resultado geral", f"<div class='metric-grid'>{cards or _metric('SARI', 'Sem score persistido')}</div><div class='notice'>SARI é apresentado a partir de <code>scores</code>. Coverage, Confidence, consolidação e gates devem ser lidos junto do valor, nunca substituídos por uma média visual.</div>")
    body += _section("composition", "Composição e dimensões", _score_table(data, include_overall=False))
    body += _section("limitations", "Limitações e gates persistidos", _table(("Contexto", "Limitação / gate"), limitations, empty="Nenhuma limitação serializada foi encontrada nas linhas SARI disponíveis."))
    body += _section("method", "Metodologia aplicada", f"<div class='metric-grid'>{_metric('Versão(ões) de scoring', ', '.join(versions) or '—')}{_metric('Fonte do valor', 'scores / audit.db')}{_metric('Recalcula no HTML?', 'Não')}</div><p>Pesos, fórmulas, gates e regras pertencem ao contrato de scoring persistido. Consulte <a href='methodology.html'>Metodologia e scoring</a> para a leitura metodológica e <a href='metrics.html'>Índices e métricas</a> para o dicionário.</p>")
    return body


def _execution_evidence_body(database: Path, data: _ReportData) -> str:
    rows = []
    for catalog in CATALOGS:
        status, tone, detail = _catalog_status(database, data, catalog.id)
        rows.append((catalog.id, catalog.label, "SIM" if catalog.id in data.selected else "NÃO", _Html(_badge(status, tone)), detail))
    integrity = "ÍNTEGRO" if data.config_hash and data.computed_hash == data.config_hash else "SNAPSHOT AUSENTE" if not data.config_hash else "HASH DIVERGENTE"
    technical = [(row.get("component", "—"), row.get("scope_key", "—"), row.get("status", "—"), row.get("attempt_count", "—"), row.get("effective_result_ref", "—")) for row in data.work_items]
    body = _audit_hero(data, "Evidências da execução", "O que foi solicitado, o que possui estado persistido e onde verificar tecnicamente o resultado.")
    body += _section("matrix", "Plano × execução", _table(("Catálogo", "Contexto", "Solicitado", "Estado", "Detalhe"), rows))
    body += _section("integrity", "Snapshot da execução", f"<div class='metric-grid'>{_metric('Integridade', integrity)}{_metric('Catálogos no snapshot', len(data.selected))}{_metric('Work-items persistidos', len(data.work_items))}</div><p class='muted'>Secrets não pertencem ao snapshot reutilizável e não são projetados nesta página.</p>")
    body += _section("technical", "Detalhes técnicos", f"<details><summary>Mostrar work-items persistidos</summary><div class='detail-body'>{_table(('Componente','Escopo','Estado','Tentativas','Resultado'), technical)}</div></details>")
    return body


def _safe_attempt_rows(database: Path, data: _ReportData) -> list[Sequence[Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "ai_provider_attempts") or "audit_id" not in _columns(connection, "ai_provider_attempts"):
            return []
        cols = _columns(connection, "ai_provider_attempts")
        allowed = [name for name in ("provider", "provider_code", "model", "model_code", "status", "input_tokens", "output_tokens", "estimated_cost_usd", "error_code") if name in cols]
        if not allowed:
            return []
        raw = _rows(connection, f"SELECT {','.join(allowed)} FROM ai_provider_attempts WHERE audit_id=?", (data.audit_id,))
        return [[row[name] for name in allowed] for row in raw]
    finally:
        connection.close()


def _ai_integrations_body(database: Path, data: _ReportData) -> str:
    ai_block = data.configuration.get("audit_catalog") if isinstance(data.configuration.get("audit_catalog"), Mapping) else {}
    ai_enabled = bool(ai_block.get("ai_enabled", False)) if isinstance(ai_block, Mapping) else False
    attempts = _safe_attempt_rows(database, data)
    connection = sqlite3.connect(database)
    try:
        integration_rows = []
        for table in sorted(data.tables):
            if not any(token in table.casefold() for token in ("serp", "gsc", "crux", "pagespeed", "observability", "clarity", "common_crawl", "ai_provider_attempt")):
                continue
            count = _audit_count(connection, table, data.audit_id)
            if count:
                integration_rows.append((table, count))
    finally:
        connection.close()
    body = _audit_hero(data, "IA e integrações", "Telemetria e fontes externas já persistidas. Esta página não realiza chamadas de rede nem de IA.")
    body += _section("ai", "Uso de IA", f"<div class='metric-grid'>{_metric('IA no plano', 'Habilitada' if ai_enabled else 'Não habilitada')}{_metric('Tentativas persistidas', len(attempts))}</div><div class='notice'>Resultados de IA são interpretação derivada. Métricas e scores determinísticos não são alterados por esta projeção.</div>")
    body += _section("integrations", "Integrações com dados persistidos", _table(("Fonte técnica", "Registros desta AUD"), integration_rows, empty="Nenhuma integração externa com registros audit-scoped foi encontrada."))
    if attempts:
        body += _section("attempts", "Tentativas de IA · campos seguros", _table(tuple(f"Campo {index+1}" for index in range(len(attempts[0]))), attempts))
    return body


def _methodology_body(data: _ReportData) -> str:
    versions = sorted({str(row.get("scoring_version")) for row in data.scores if row.get("scoring_version")})
    body = _audit_hero(data, "Metodologia e scoring", "Como ler índices, métricas, classificações e resultados sem confundir medição com interpretação.")
    body += _section("principles", "Princípios de leitura", "<div class='grid'><div class='card'><h3>Índice</h3><p>Resultado agregado derivado, como SARI ou Apdex.</p></div><div class='card'><h3>Métrica</h3><p>Medição direta ou quase direta, como LCP, CLS, INP, posição SERP, cliques ou impressões.</p></div><div class='card'><h3>Classificação</h3><p>Interpretação associada a índice/métrica; deve usar o contrato que produziu o dado.</p></div><div class='card'><h3>Contagem</h3><p>Quantidade de evidências, erros, URLs, resultados ou registros.</p></div></div>")
    body += _section("scoring", "Contrato de scoring persistido", f"<div class='metric-grid'>{_metric('Versão(ões)', ', '.join(versions) or '—')}{_metric('Recalcula score?', 'Não')}{_metric('Fonte', 'audit.db')}</div>{_score_table(data)}")
    body += _section("ai", "IA e determinismo", "<p>Este gerador apenas projeta o que foi persistido. IA pode aparecer como análise/advisory quando o contrato da execução a utilizou, mas não escolhe pesos nem reescreve uma medição determinística durante a renderização.</p>")
    return body


def _metrics_body(database: Path, data: _ReportData) -> str:
    rows: list[Sequence[Any]] = []
    for row in data.scores:
        dimension = str(row.get("dimension") or "")
        label = _DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title())
        context = "SARI" if dimension == "OVERALL_READINESS" else _DIMENSION_CONTEXT.get(dimension, "Metodologia")
        link = "sari.html" if dimension == "OVERALL_READINESS" else (CATALOG_PAGE_BY_ID[context].filename if context in CATALOG_PAGE_BY_ID else "methodology.html")
        rows.append((_Html(f"<a href='{link}'>{escape(label)}</a>"), "Índice", _score_value(row), row.get("device", "—"), "scores / audit.db", row.get("scoring_version", "—")))
    for catalog_id in ("CAT-04", "CAT-05", "CAT-06", "CAT-07"):
        for name, value, source, kind in _catalog_metrics(database, data, catalog_id):
            rows.append((_Html(f"<a href='{CATALOG_PAGE_BY_ID[catalog_id].filename}'>{escape(name)}</a>"), kind, value, CATALOG_BY_ID[catalog_id].label, source, "persistido"))
    definitions = (
        ("SARI", "Índice", "Readiness agregado persistido com coverage/confidence/gates; detalhado em página própria."),
        ("Lighthouse", "Índice", "Scores de laboratório por categoria quando coletados."),
        ("LCP / INP / CLS / TTFB", "Métrica", "Métricas de performance; a fonte deve distinguir laboratório e campo."),
        ("Apdex", "Índice", "Índice de satisfação calculado a partir das amostras e thresholds persistidos."),
        ("Posição SERP", "Métrica", "Posição observada em coleta SERP; não equivale à posição média do Google Search Console."),
        ("GSC", "Métricas", "Cliques, impressões, CTR e posição média, quando persistidos pela property autenticada."),
    )
    body = _audit_hero(data, "Índices e métricas", "Inventário transversal dos números persistidos, sempre ligado ao contexto onde devem ser interpretados.")
    body += _section("inventory", "Inventário desta AUD", _table(("Índice / métrica", "Tipo", "Valor", "Contexto", "Fonte", "Contrato"), rows, empty="Nenhum índice/métrica reconhecido foi persistido."))
    body += _section("dictionary", "Dicionário", _table(("Termo", "Tipo", "Como interpretar"), definitions))
    return body


def materialize_catalog_report_site(*, audit_id: str, workspace: Any) -> Path:
    """Materialize the independent ``report-catalog/`` tree and return its index."""
    report_dir = Path(workspace.root) / CATALOG_REPORT_DIR
    css_dir = report_dir / "css"
    css_dir.mkdir(parents=True, exist_ok=True)
    data = _load_data(audit_id, Path(workspace.database))
    (css_dir / "site.css").write_text(_CSS.strip() + "\n", encoding="utf-8", newline="\n")

    bodies: dict[str, str] = {
        "index.html": _overview_body(Path(workspace.database), data),
        "sari.html": _sari_body(data),
        "execution-evidence.html": _execution_evidence_body(Path(workspace.database), data),
        "ai-integrations.html": _ai_integrations_body(Path(workspace.database), data),
        "methodology.html": _methodology_body(data),
        "metrics.html": _metrics_body(Path(workspace.database), data),
    }
    for catalog in CATALOGS:
        bodies[CATALOG_PAGE_BY_ID[catalog.id].filename] = _catalog_body(Path(workspace.database), data, catalog.id)

    for page in CATALOG_REPORT_PAGES:
        (report_dir / page.filename).write_text(_shell(page, audit_id, bodies[page.filename]), encoding="utf-8", newline="\n")

    manifest = {
        "contract": CATALOG_REPORT_CONTRACT_VERSION,
        "audit_id": audit_id,
        "source_of_truth": "audit.db + secret-free execution snapshot",
        "legacy_report_dir": "report",
        "catalog_report_dir": CATALOG_REPORT_DIR,
        "pages": [{"id": page.id, "filename": page.filename, "label": page.label, "catalog_id": page.catalog_id} for page in CATALOG_REPORT_PAGES],
    }
    (report_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report_dir / "index.html"
