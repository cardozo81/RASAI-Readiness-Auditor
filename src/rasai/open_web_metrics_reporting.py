"""Read-only report for zero-cost Open Web metrics captured in device snapshots."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from rasai.open_web_metrics import OPEN_WEB_METRICS_CONTRACT_VERSION
from rasai.persistence import AuditWorkspace
from rasai import report_navigation


REPORT_FILE = "web-standards.html"


def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _load(audit_id: str, workspace: AuditWorkspace) -> list[dict[str, Any]]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not (_table_exists(connection, "page_snapshots") and _table_exists(connection, "pages")):
            return []
        snapshot_columns = _columns(connection, "page_snapshots")
        page_columns = _columns(connection, "pages")
        required_snapshot = {"snapshot_id", "page_id", "device", "browser_metadata"}
        required_page = {"page_id", "audit_id"}
        if not required_snapshot.issubset(snapshot_columns) or not required_page.issubset(page_columns):
            return []
        url_expr = "p.normalized_url" if "normalized_url" in page_columns else "ps.requested_url"
        rows = connection.execute(
            f"""SELECT ps.snapshot_id,ps.device,{url_expr} AS url,ps.browser_metadata
                FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                WHERE p.audit_id=? ORDER BY p.rowid,ps.device""",
            (audit_id,),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            metadata = _json(row["browser_metadata"], {})
            metrics = metadata.get("open_web_metrics") if isinstance(metadata, dict) else None
            if not isinstance(metrics, dict):
                metrics = {
                    "contract_version": OPEN_WEB_METRICS_CONTRACT_VERSION,
                    "state": "NOT_CAPTURED",
                    "reason": "SNAPSHOT_PREDATES_OPEN_WEB_METRICS",
                }
            result.append(
                {
                    "snapshot_id": str(row["snapshot_id"]),
                    "device": str(row["device"]),
                    "url": str(row["url"] or "-"),
                    "metrics": metrics,
                }
            )
        return result
    finally:
        connection.close()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _nested(item: dict[str, Any], section: str, field: str) -> Any:
    metrics = item.get("metrics")
    section_value = metrics.get(section) if isinstance(metrics, dict) else None
    return section_value.get(field) if isinstance(section_value, dict) else None


def _fmt_ms(value: Any) -> str:
    parsed = _number(value)
    return "-" if parsed is None else f"{parsed:.1f} ms"


def _fmt_bytes(value: Any) -> str:
    parsed = _number(value)
    if parsed is None:
        return "-"
    if parsed >= 1024 * 1024:
        return f"{parsed / (1024 * 1024):.2f} MiB"
    if parsed >= 1024:
        return f"{parsed / 1024:.1f} KiB"
    return f"{int(parsed)} B"


def _fmt_decimal(value: Any, digits: int = 3) -> str:
    parsed = _number(value)
    return "-" if parsed is None else f"{parsed:.{digits}f}"


def _range(items: Iterable[dict[str, Any]], section: str, field: str, *, suffix: str = "") -> str:
    values = [_number(_nested(item, section, field)) for item in items]
    observed = [value for value in values if value is not None]
    if not observed:
        return "não observado"
    low, high = min(observed), max(observed)
    if suffix == " ms":
        return f"{low:.1f}–{high:.1f} ms" if low != high else f"{low:.1f} ms"
    if suffix:
        return f"{low:.3f}–{high:.3f}{suffix}" if low != high else f"{low:.3f}{suffix}"
    return f"{low:.3f}–{high:.3f}" if low != high else f"{low:.3f}"


def _condition(metric: str, value: Any) -> str:
    parsed = _number(value)
    if parsed is None:
        return "não observado"
    if metric == "lcp":
        return "bom" if parsed <= 2500 else "precisa melhorar" if parsed <= 4000 else "ruim"
    if metric == "cls":
        return "bom" if parsed <= 0.1 else "precisa melhorar" if parsed <= 0.25 else "ruim"
    return "observado"


def _summary(items: list[dict[str, Any]]) -> str:
    captured = [item for item in items if item["metrics"].get("state") == "CAPTURED"]
    states = Counter(str(item["metrics"].get("state") or "UNKNOWN") for item in items)
    state_text = ", ".join(f"{key}: {value}" for key, value in sorted(states.items())) or "sem snapshots"
    return f"""
<div class='metric-grid'>
  <div class='metric'><small>Snapshots</small><strong>{len(items)}</strong></div>
  <div class='metric'><small>Capturados</small><strong>{len(captured)}</strong></div>
  <div class='metric'><small>LCP observado</small><strong>{escape(_range(captured, 'paint', 'largest_contentful_paint_ms', suffix=' ms'))}</strong></div>
  <div class='metric'><small>CLS observado</small><strong>{escape(_range(captured, 'layout', 'cumulative_layout_shift'))}</strong></div>
</div>
<p><strong>Estados:</strong> {escape(state_text)}</p>
"""


def _snapshot_table(items: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    for item in items:
        metrics = item["metrics"]
        state = str(metrics.get("state") or "UNKNOWN")
        reason = str(metrics.get("reason") or "")
        navigation = metrics.get("navigation") if isinstance(metrics.get("navigation"), dict) else {}
        paint = metrics.get("paint") if isinstance(metrics.get("paint"), dict) else {}
        layout = metrics.get("layout") if isinstance(metrics.get("layout"), dict) else {}
        responsiveness = metrics.get("responsiveness") if isinstance(metrics.get("responsiveness"), dict) else {}
        main_thread = metrics.get("main_thread") if isinstance(metrics.get("main_thread"), dict) else {}
        resources = metrics.get("resources") if isinstance(metrics.get("resources"), dict) else {}
        lcp = paint.get("largest_contentful_paint_ms")
        cls = layout.get("cumulative_layout_shift")
        rows.append(
            "<tr>"
            f"<td>{escape(item['device'])}</td>"
            f"<td><code>{escape(item['url'])}</code></td>"
            f"<td>{escape(state + ((' · ' + reason) if reason else ''))}</td>"
            f"<td>{escape(_fmt_ms(navigation.get('ttfb_from_navigation_start_ms')))}</td>"
            f"<td>{escape(_fmt_ms(paint.get('first_contentful_paint_ms')))}</td>"
            f"<td>{escape(_fmt_ms(lcp))}<br><small>{escape(_condition('lcp', lcp))}</small></td>"
            f"<td>{escape(_fmt_decimal(cls))}<br><small>{escape(_condition('cls', cls))}</small></td>"
            f"<td>{escape(_fmt_ms(responsiveness.get('max_observed_interaction_event_duration_ms')))}</td>"
            f"<td>{escape(str(main_thread.get('long_task_count', '-')))}</td>"
            f"<td>{escape(str(resources.get('count', '-')))} / {escape(str(resources.get('third_party_count', '-')))}</td>"
            "</tr>"
        )
    if not rows:
        return "<p>Nenhum snapshot disponível.</p>"
    return (
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Dispositivo</th><th>URL</th><th>Estado</th><th>TTFB</th><th>FCP</th><th>LCP</th><th>CLS</th>"
        "<th>Interação máx. observada</th><th>Long tasks</th><th>Recursos / terceiros</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _details(items: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in items:
        metrics = item["metrics"]
        if metrics.get("state") != "CAPTURED":
            continue
        navigation = metrics.get("navigation") if isinstance(metrics.get("navigation"), dict) else {}
        resources = metrics.get("resources") if isinstance(metrics.get("resources"), dict) else {}
        user_timing = metrics.get("user_timing") if isinstance(metrics.get("user_timing"), dict) else {}
        platform = metrics.get("document_platform") if isinstance(metrics.get("document_platform"), dict) else {}
        supported = metrics.get("supported_entry_types") if isinstance(metrics.get("supported_entry_types"), list) else []
        initiators = resources.get("initiator_counts") if isinstance(resources.get("initiator_counts"), dict) else {}
        initiator_text = ", ".join(f"{key}={value}" for key, value in sorted(initiators.items())) or "-"
        blocks.append(
            f"<details><summary>{escape(item['device'])} · {escape(item['url'])}</summary>"
            "<div class='grid'>"
            "<div class='page-card'><h3>Navigation Timing</h3>"
            f"<p>Protocolo: <code>{escape(str(navigation.get('next_hop_protocol') or '-'))}</code></p>"
            f"<p>DNS: {_fmt_ms(navigation.get('dns_ms'))} · conexão: {_fmt_ms(navigation.get('connect_ms'))} · TLS: {_fmt_ms(navigation.get('tls_ms'))}</p>"
            f"<p>Resposta: {_fmt_ms(navigation.get('response_download_ms'))} · load event: {_fmt_ms(navigation.get('load_event_end_ms'))}</p>"
            f"<p>Documento transferido: {_fmt_bytes(navigation.get('transfer_size_bytes'))}; Server-Timing: {escape(str(navigation.get('server_timing_metric_count', 0)))} métrica(s).</p>"
            "</div>"
            "<div class='page-card'><h3>Resource Timing</h3>"
            f"<p>{escape(str(resources.get('count', 0)))} recurso(s); {escape(str(resources.get('third_party_count', 0)))} de outra origem.</p>"
            f"<p>Transferência observável: {_fmt_bytes(resources.get('transfer_size_bytes'))}; sem visibilidade de tamanho: {escape(str(resources.get('entries_without_size_visibility', 0)))}.</p>"
            f"<p>Initiators: {escape(initiator_text)}</p>"
            "</div>"
            "<div class='page-card'><h3>User Timing</h3>"
            f"<p>Marks: {escape(str(user_timing.get('mark_count', 0)))} · measures: {escape(str(user_timing.get('measure_count', 0)))} · duração medida: {_fmt_ms(user_timing.get('measured_duration_total_ms'))}.</p>"
            "<p>Os nomes de marks/measures não são exportados para evitar vazar instrumentação interna da aplicação.</p>"
            "</div>"
            "<div class='page-card'><h3>Contexto da plataforma</h3>"
            f"<p>Standards mode: {escape(str(bool(platform.get('standards_mode'))))} · doctype: {escape(str(bool(platform.get('doctype_present'))))} · lang: {escape(str(bool(platform.get('document_language_present'))))}.</p>"
            f"<p>Charset: <code>{escape(str(platform.get('charset') or '-'))}</code> · viewport meta: {escape(str(bool(platform.get('viewport_meta_present'))))}.</p>"
            f"<p>Secure context: {escape(str(bool(platform.get('secure_context'))))} · cross-origin isolated: {escape(str(bool(platform.get('cross_origin_isolated'))))}.</p>"
            "</div>"
            "</div>"
            f"<p><strong>PerformanceEntry suportados pelo Chromium desta execução:</strong> {escape(', '.join(map(str, supported)) or '-')}</p>"
            "</details>"
        )
    return "".join(blocks) or "<p>Não há observações Open Web capturadas nesta auditoria.</p>"


def write_open_web_metrics_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    items = _load(audit_id, workspace)
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / REPORT_FILE
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    html = f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi · Open Web Metrics</title><link rel='stylesheet' href='css/site.css'></head><body>
<div class='app-shell'>{nav}<main class='app-main'>
<header class='hero'><div class='eyebrow'>Open Web · {escape(OPEN_WEB_METRICS_CONTRACT_VERSION)}</div>
<h1>Web Standards & Performance APIs</h1>
<p>Evidência complementar capturada no mesmo snapshot Chromium já usado pela auditoria. Não há nova navegação, API externa ou custo de provider. Esta página não recalcula SARI-001/SCORE-GEO-004.</p></header>
<section class='panel'><h2>Resumo da auditoria</h2>
<div class='notice'><strong>Escopo:</strong> cada linha abaixo representa uma combinação URL + dispositivo. O resumo usa faixas mínimo–máximo quando há múltiplos snapshots; não existe média implícita entre páginas ou devices.</div>
{_summary(items)}</section>
<section class='panel'><h2>Métricas observadas por URL e dispositivo</h2>
<p>TTFB/FCP/LCP/CLS vêm das APIs de performance disponíveis no Chromium da própria execução. LCP e CLS usam as bandas de referência de Core Web Vitals apenas como contexto visual; isso não transforma a coleta em CrUX, RUM ou Lighthouse.</p>
{_snapshot_table(items)}</section>
<section class='panel'><h2>Navigation, Resource, Server e User Timing</h2>{_details(items)}</section>
<section class='panel'><h2>Fronteiras metodológicas</h2>
<ul>
<li><strong>Sem “W3C score”:</strong> W3C define APIs e métricas, não um score composto oficial para esta superfície.</li>
<li><strong>INP não é inferido:</strong> Event Timing aparece apenas quando houve interação qualificável; uma navegação sintética sem interação não recebe INP artificial.</li>
<li><strong>Sem aquisição adicional:</strong> <code>additional_navigation_requests=0</code> e <code>additional_external_api_calls=0</code>.</li>
<li><strong>Sem impacto em scoring:</strong> os valores são diagnósticos complementares e permanecem fora de SARI-001/SCORE-GEO-004.</li>
<li><strong>Visibilidade de Resource Timing:</strong> recursos cross-origin podem ocultar tamanhos sem <code>Timing-Allow-Origin</code>; ausência de tamanho observável não significa recurso vazio.</li>
</ul></section>
</main></div></body></html>"""
    path.write_text(html, encoding="utf-8", newline="\n")
    return path
