"""Relatório dedicado do M26 — Observed Generative Visibility."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any

from searchgeo import report_navigation
from searchgeo.m26_visibility import wilson_interval
from searchgeo.persistence import AuditWorkspace

M26_REPORT_FILE = "ai-visibility.html"
M26_NAV_LABEL = "Visibilidade em IA"

_OFFICIAL_REFERENCES = (
    (
        "Bing Webmaster Tools — Introducing AI Performance",
        "https://blogs.bing.com/webmaster/February-2026/Introducing-AI-Performance-in-Bing-Webmaster-Tools-Public-Preview",
        "Define Total Citations, Average Cited Pages, grounding queries, atividade por URL e tendências no AI Performance.",
    ),
    (
        "Bing — Elevating the Role of Grounding on the AI Web",
        "https://blogs.bing.com/search/February-2026/Elevating-the-Role-of-Grounding-on-the-AI-Web",
        "Contextualiza grounding, citações e participação do conteúdo em respostas de IA.",
    ),
)


def enrich_m26_report_site(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    original_nav = report_navigation.NAV_ITEMS
    try:
        _register_navigation()
        data = _load(audit_id, workspace)
        path = report_dir / M26_REPORT_FILE
        path.write_text(_page(data, report_dir), encoding="utf-8", newline="\n")
        report_navigation.normalize_report_navigation(report_dir)
        return path
    finally:
        report_navigation.NAV_ITEMS = original_nav


def _register_navigation() -> None:
    if any(filename == M26_REPORT_FILE for _, filename in report_navigation.NAV_ITEMS):
        return
    items = list(report_navigation.NAV_ITEMS)
    insertion = next(
        (index for index, value in enumerate(items) if value[1] == "ai-usage.html"),
        len(items),
    )
    items.insert(insertion, (M26_NAV_LABEL, M26_REPORT_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def _load(audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        imports = _many(
            connection,
            "SELECT * FROM generative_visibility_imports WHERE audit_id=? ORDER BY period_end DESC,imported_at DESC,import_id",
            (audit_id,),
        )
        pages = _many(connection, "SELECT * FROM generative_visibility_page_citations WHERE audit_id=? ORDER BY import_id,citations DESC,url", (audit_id,))
        queries = _many(connection, "SELECT * FROM generative_visibility_grounding_queries WHERE audit_id=? ORDER BY import_id,COALESCE(citations,-1) DESC,query_text", (audit_id,))
        trend = _many(connection, "SELECT * FROM generative_visibility_trend WHERE audit_id=? ORDER BY import_id,observed_date", (audit_id,))
        runs = _many(connection, "SELECT * FROM generative_visibility_query_runs WHERE audit_id=? ORDER BY import_id,observed_at,query_run_id", (audit_id,))
        return {"imports": imports, "pages": pages, "queries": queries, "trend": trend, "runs": runs}
    finally:
        connection.close()


def _many(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[sqlite3.Row]:
    try:
        return list(connection.execute(sql, params).fetchall())
    except sqlite3.OperationalError:
        return []


def _page(data: dict[str, Any], report_dir: Path) -> str:
    nav = report_navigation.render_report_navigation(report_dir, M26_REPORT_FILE)
    imports = data["imports"]
    if not imports:
        body = """
        <header class='hero'><div class='eyebrow'>M26 · outcome observado</div><h1>Observed Generative Visibility</h1>
        <p class='lead'>Nenhum dataset de visibilidade generativa foi importado para esta auditoria.</p></header>
        <section class='panel'><h2>Readiness ≠ Visibility</h2><p>Esta página é deliberadamente separada do SGRI/SCORE-GEO. Ausência de dados observados não reduz o readiness.</p></section>
        """
        return _shell(nav, body)

    sections = "".join(_import_section(item, data) for item in imports)
    latest = imports[0]
    body = f"""
    <header class='hero'>
      <div class='eyebrow'>M26 · outcome observado · non-scoring</div>
      <h1>Observed Generative Visibility</h1>
      <p class='lead'>Resultados observados/importados sobre participação e citação em superfícies de IA. Estes dados <strong>não compõem SGRI-001/SCORE-GEO-002</strong> e não são convertidos em um “GEO Score”.</p>
      <div class='metric-grid'>
        {_metric('Datasets importados', len(imports))}
        {_metric('Período mais recente', f"{latest['period_start']} → {latest['period_end']}")}
        {_metric('Fonte declarada', latest['source_label'])}
        {_metric('Método de captura', latest['capture_method'])}
        {_metric('Contrato', latest['format_version'])}
      </div>
    </header>
    <section class='panel notice-critical'>
      <h2>Readiness ≠ Visibility</h2>
      <p><strong>Readiness</strong> descreve condições técnicas/semânticas inferidas pela auditoria. <strong>Observed Generative Visibility</strong> descreve o que foi efetivamente observado numa fonte ou protocolo. Correlação entre ambos é matéria de validação empírica futura; esta página não presume causalidade.</p>
      <p>Contagem de citações não é ranking, autoridade, posição nem probabilidade de citação futura. Métricas declaradas como reportadas por terceiros são preservadas sem recomputação equivalente.</p>
      <p><strong>Proveniência:</strong> M26 é import-first. A fonte e o método de captura são declarados no artifact fornecido ao SearchGEO; nesta versão o SearchGEO não autentica o portal externo nem afirma que realizou coleta direta.</p>
    </section>
    {sections}
    {_references()}
    <footer class='footer'>M26 é import-first, auditável e non-scoring. O SearchGEO não faz scraping de portais de webmaster nem inventa endpoint de API para esta coleta.</footer>
    """
    return _shell(nav, body)


def _import_section(item: sqlite3.Row, data: dict[str, Any]) -> str:
    import_id = str(item["import_id"])
    pages = [row for row in data["pages"] if str(row["import_id"]) == import_id]
    queries = [row for row in data["queries"] if str(row["import_id"]) == import_id]
    trend = [row for row in data["trend"] if str(row["import_id"]) == import_id]
    runs = [row for row in data["runs"] if str(row["import_id"]) == import_id]
    valid = [row for row in runs if str(row["status"]) == "VALID"]
    cited = sum(bool(row["cited"]) for row in valid)
    interval = wilson_interval(cited, len(valid))
    rate = (cited / len(valid)) if valid else None
    cited_pages = len({str(row["url"]) for row in pages if int(row["citations"] or 0) > 0})
    engines = sorted({str(row["engine"]) for row in valid})

    reported_total = item["source_total_citations"]
    reported_average = item["source_average_cited_pages"]
    metrics = [
        _metric("Fonte declarada", item["source_label"]),
        _metric("Método de captura", item["capture_method"]),
        _metric("Período", f"{item['period_start']} → {item['period_end']}"),
        _metric("URLs citadas observadas", cited_pages if pages else "—"),
    ]
    if reported_total is not None:
        metrics.append(_metric("Total Citations · fonte", int(reported_total)))
    if reported_average is not None:
        metrics.append(_metric("Average Cited Pages · fonte", f"{float(reported_average):g}"))
    if valid:
        metrics.extend((
            _metric("Query-runs válidos", len(valid)),
            _metric("Runs com citação", cited),
            _metric("Citation Presence Rate", f"{rate*100:.1f}%"),
            _metric("IC Wilson 95%", f"{interval[0]*100:.1f}%–{interval[1]*100:.1f}%" if interval else "—"),
        ))

    page_rows = "".join(
        f"<tr><td class='mono'>{escape(str(row['url']))}</td><td>{int(row['citations'])}</td><td>{escape(str(row['observed_date'] or 'período'))}</td></tr>"
        for row in pages[:100]
    ) or "<tr><td colspan='3'>Sem observação por URL.</td></tr>"
    query_rows = "".join(
        f"<tr><td>{escape(str(row['query_text']))}</td><td>{'—' if row['citations'] is None else int(row['citations'])}</td><td class='mono'>{escape(str(row['url'] or '—'))}</td><td>{escape(str(row['observed_date'] or 'período'))}</td></tr>"
        for row in queries[:100]
    ) or "<tr><td colspan='4'>Sem grounding queries importadas.</td></tr>"
    trend_rows = "".join(
        f"<tr><td>{escape(str(row['observed_date']))}</td><td>{int(row['citations'])}</td></tr>"
        for row in trend
    ) or "<tr><td colspan='2'>Sem série temporal importada.</td></tr>"
    run_rows = "".join(_run_row(row) for row in runs[:200]) or "<tr><td colspan='7'>Sem query-runs controlados.</td></tr>"
    engine_note = ", ".join(engines) if engines else "não aplicável"
    artifact = escape(str(item["artifact_path"]))
    sha = escape(str(item["artifact_sha256"]))
    metadata = _json(item["metadata"])
    metadata_text = escape(json.dumps(metadata, ensure_ascii=False, sort_keys=True)) if metadata else "{}"

    return f"""
    <section class='panel' id='{escape(import_id)}'>
      <div class='kicker'>{escape(str(item['source_type']))}</div>
      <h2>{escape(str(item['source_label']))} · {escape(str(item['period_start']))} → {escape(str(item['period_end']))}</h2>
      <div class='metric-grid'>{''.join(metrics)}</div>
      <p class='intro'><strong>Market/language:</strong> {escape(str(item['market'] or '—'))} / {escape(str(item['language'] or '—'))}. <strong>Engines nos query-runs válidos:</strong> {escape(engine_note)}.</p>
      <div class='notice'><strong>Proveniência declarada:</strong> método <code>{escape(str(item['capture_method']))}</code> · artifact <code>{artifact}</code> · SHA-256 <code>{sha}</code> · importado em {escape(str(item['imported_at']))}. Metadata: <code>{metadata_text}</code>. O SearchGEO preserva esta declaração, mas não a converte em prova de coleta autenticada no sistema externo.</div>
      <h3>Atividade por URL</h3>
      <div class='table-wrap'><table><thead><tr><th>URL</th><th>Citações</th><th>Data</th></tr></thead><tbody>{page_rows}</tbody></table></div>
      <h3>Grounding queries</h3>
      <div class='table-wrap'><table><thead><tr><th>Query</th><th>Citações</th><th>URL</th><th>Data</th></tr></thead><tbody>{query_rows}</tbody></table></div>
      <h3>Tendência importada</h3>
      <div class='table-wrap'><table><thead><tr><th>Data</th><th>Citações</th></tr></thead><tbody>{trend_rows}</tbody></table></div>
      <h3>Query-runs controlados</h3>
      <p>Quando há runs válidos, <strong>Citation Presence Rate = runs válidos que citaram o origin auditado / total de runs válidos</strong>. Runs INVALID são excluídos do denominador. O intervalo mostrado é Wilson 95% e não transforma a taxa em previsão.</p>
      <div class='table-wrap'><table><thead><tr><th>Engine/surface</th><th>Query</th><th>Timestamp</th><th>Status</th><th>Citado</th><th>URLs</th><th>Rank observado</th></tr></thead><tbody>{run_rows}</tbody></table></div>
    </section>
    """


def _run_row(row: sqlite3.Row) -> str:
    cited_urls = _json_list(row["cited_urls"])
    cited = "—" if row["cited"] is None else ("SIM" if bool(row["cited"]) else "NÃO")
    rank = "—" if row["source_rank"] is None else f"{int(row['source_rank'])} ({escape(str(row['ranking_semantics'] or 'sem semântica'))})"
    surface = f" / {row['surface']}" if row["surface"] else ""
    return (
        "<tr>"
        f"<td>{escape(str(row['engine']))}{escape(surface)}</td>"
        f"<td>{escape(str(row['query_text']))}</td>"
        f"<td>{escape(str(row['observed_at']))}</td>"
        f"<td>{escape(str(row['status']))}</td>"
        f"<td>{cited}</td>"
        f"<td class='mono'>{escape(', '.join(cited_urls) or '—')}</td>"
        f"<td>{rank}</td>"
        "</tr>"
    )


def _references() -> str:
    rows = "".join(
        f"<li><a href='{escape(url, quote=True)}' target='_blank' rel='noopener'>{escape(title)} ↗</a> — {escape(note)}</li>"
        for title, url, note in _OFFICIAL_REFERENCES
    )
    return f"<section class='panel'><div class='kicker'>Referências</div><h2>Fundamentação pública</h2><ul>{rows}</ul></section>"


def _metric(label: Any, value: Any) -> str:
    return f"<div class='metric'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"


def _json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _shell(nav: str, body: str) -> str:
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Observed Generative Visibility · SearchGEO</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'>{body}</main></body></html>"""