"""Observed Search/AI and evidence-bound diagnostics HTML report."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
from typing import Any

from rasai import report_navigation

from .diagnostics import Diagnostic, DiagnosticBundle, analyze_workspace
from .store import ObservabilityStore

REPORT_FILE = "observability.html"
NAV_LABEL = "Search & AI observados"


def enrich_observability_report(*, audit_workspace: str | Path) -> Path:
    workspace = Path(audit_workspace)
    report_dir = workspace / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    bundle = analyze_workspace(workspace)
    data = _sidecar(workspace)
    original_nav = report_navigation.NAV_ITEMS
    try:
        _register_navigation()
        path = report_dir / REPORT_FILE
        path.write_text(_page(bundle, data, report_dir), encoding="utf-8", newline="\n")
        report_navigation.normalize_report_navigation(report_dir)
        return path
    finally:
        report_navigation.NAV_ITEMS = original_nav


def _register_navigation() -> None:
    if any(filename == REPORT_FILE for _, filename in report_navigation.NAV_ITEMS):
        return
    items = list(report_navigation.NAV_ITEMS)
    insertion = next((index for index, item in enumerate(items) if item[1] == "ai-usage.html"), len(items))
    items.insert(insertion, (NAV_LABEL, REPORT_FILE))
    report_navigation.NAV_ITEMS = tuple(items)


def _sidecar(workspace: Path) -> dict[str, list[dict[str, Any]]]:
    if not (workspace / "observability.db").is_file():
        return {"datasets": [], "search": [], "index": [], "crux": []}
    with ObservabilityStore(workspace) as store:
        return {
            "datasets": [dict(row) for row in store.datasets()],
            "search": [dict(row) for row in store.search_rows()],
            "index": [dict(row) for row in store.index_rows()],
            "crux": [dict(row) for row in store.crux_rows()],
        }


def _page(bundle: DiagnosticBundle, data: dict[str, list[dict[str, Any]]], report_dir: Path) -> str:
    nav = report_navigation.render_report_navigation(report_dir, REPORT_FILE)
    counts = Counter(item.severity for item in bundle.diagnostics if item.status not in {"ADVISORY", "COMPLETE_FOR_TOP_LEVEL_REQUIREMENTS"})
    query_counts = Counter(item["status"] for item in bundle.query_intent_alignment)
    dataset_rows = "".join(_dataset_row(item) for item in data["datasets"]) or "<tr><td colspan='6'>Nenhum dataset observacional persistido.</td></tr>"
    diagnostic_rows = "".join(_diagnostic_row(item) for item in sorted(bundle.diagnostics, key=lambda item: (-_sev(item.severity), item.domain, item.url or "", item.code))) or "<tr><td colspan='8'>Nenhum diagnóstico adicional aplicável.</td></tr>"
    matrix_rows = "".join(_matrix_row(item) for item in bundle.indexability_matrix) or "<tr><td colspan='10'>Sem páginas auditadas para a matriz.</td></tr>"
    intent_rows = "".join(_intent_row(item) for item in sorted(bundle.query_intent_alignment, key=lambda item: (-float(item.get("impressions") or 0), item["query"]))) or "<tr><td colspan='8'>Sem Search Performance com query + URL ou sem intents persistidas.</td></tr>"
    cannibal_rows = "".join(_cannibal_row(item) for item in bundle.cannibalization_candidates) or "<tr><td colspan='5'>Nenhum candidato conservador detectado.</td></tr>"
    cluster_rows = "".join(_cluster_row(item) for item in bundle.template_clusters) or "<tr><td colspan='7'>Nenhum cluster com duas ou mais ocorrências.</td></tr>"
    crux_rows = "".join(_crux_row(item) for item in data["crux"]) or "<tr><td colspan='8'>CrUX History ainda não coletado/importado.</td></tr>"
    refs = "".join(
        f"<li><a href='{escape(ref, quote=True)}' target='_blank' rel='noopener'>{escape(label)} ↗</a></li>"
        for label, ref in (
            ("Google - versões localizadas / hreflang", "https://developers.google.com/search/docs/specialty/international/localized-versions"),
            ("Google - Product structured data", "https://developers.google.com/search/docs/appearance/structured-data/product-snippet"),
            ("Google - Breadcrumb structured data", "https://developers.google.com/search/docs/appearance/structured-data/breadcrumb"),
            ("Google - Organization structured data", "https://developers.google.com/search/docs/appearance/structured-data/organization"),
            ("Google Search Console - Search Analytics API", "https://developers.google.com/webmaster-tools/v1/searchanalytics/query"),
            ("Google Search Console - URL Inspection API", "https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect"),
            ("Chrome UX Report - History API", "https://developer.chrome.com/docs/crux/history-api"),
            ("Bing Webmaster Tools - Search Performance", "https://www.bing.com/webmasters/help/search-performance-c680da36"),
        )
    )
    body = f"""
<header class='hero'>
  <div class='eyebrow'>Observed Search & AI · diagnóstico complementar · não altera SARI-001</div>
  <h1>Search & AI Observability</h1>
  <p class='lead'>Cruza evidência persistida pelo RASAi com outcomes externos observados e diagnósticos derivados. Readiness, visibilidade, indexação observada e experiência de campo permanecem metodologias separadas.</p>
  <div class='metric-grid'>
    {_metric('Datasets observados', len(data['datasets']))}
    {_metric('Registros Search Performance', len(data['search']))}
    {_metric('Observações de índice', len(data['index']))}
    {_metric('Pontos CrUX History', len(data['crux']))}
    {_metric('Diagnósticos High/Critical', counts.get('HIGH',0) + counts.get('CRITICAL',0))}
    {_metric('Cannibalization candidates', len(bundle.cannibalization_candidates))}
  </div>
</header>
<section class='panel notice'><h2>Contrato metodológico</h2><p><strong>Estes dados não entram automaticamente em SARI-001/SCORE-GEO-004.</strong> A presença de um outcome externo não prova causalidade. URL Inspection descreve a versão conhecida pelo índice e não substitui um teste live; Search Performance descreve outcomes observados; CrUX History é dado de campo agregado.</p></section>
<section class='panel'><div class='kicker'>Proveniência</div><h2>Datasets observados</h2><div class='table-wrap'><table><thead><tr><th>ID</th><th>Fonte</th><th>Captura</th><th>Período</th><th>Artifact</th><th>Coletado</th></tr></thead><tbody>{dataset_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Indexability Reality Matrix</div><h2>Declaração local × observação externa</h2><p>Diferença entre canonical declarado e canonical selecionado é mostrada como divergência observada; não é convertida automaticamente em causa de perda de tráfego.</p><div class='table-wrap'><table><thead><tr><th>URL</th><th>Device</th><th>HTTP</th><th>Meta robots</th><th>Canonical declarado</th><th>Fonte</th><th>Verdict</th><th>Indexing state</th><th>Canonical externo</th><th>Alinhamento</th></tr></thead><tbody>{matrix_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Diagnóstico evidence-bound</div><h2>Structured Data, entidades, freshness, hreflang e retrieval</h2><div class='table-wrap'><table><thead><tr><th>Sev.</th><th>Domínio</th><th>Código</th><th>Status</th><th>URL</th><th>Device</th><th>Descrição</th><th>Referência</th></tr></thead><tbody>{diagnostic_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Search outcomes × conteúdo</div><h2>Query × Intent Alignment</h2><p>O matching é lexical e conservador sobre intents já persistidas pelas BR-GEO-038/048. Ele não é “keyword score” e não substitui análise humana.</p><div class='metric-grid'>{_metric('Aligned',query_counts.get('ALIGNED',0))}{_metric('Partial',query_counts.get('PARTIAL',0))}{_metric('Unmatched',query_counts.get('UNMATCHED',0))}{_metric('Intent indisponível',query_counts.get('INTENT_NOT_AVAILABLE',0))}</div><div class='table-wrap'><table><thead><tr><th>Fonte</th><th>Surface</th><th>Query</th><th>URL</th><th>Impressions</th><th>Clicks</th><th>Overlap</th><th>Status</th></tr></thead><tbody>{intent_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Hipótese operacional</div><h2>Potential Search Cannibalization</h2><p>Somente aparece quando pelo menos duas URLs recebem cada uma ≥20% das impressões observadas para a mesma query/fonte. Isso é candidato para investigação, não prova de dano.</p><div class='table-wrap'><table><thead><tr><th>Fonte</th><th>Query</th><th>Impressions</th><th>Distribuição</th><th>Status</th></tr></thead><tbody>{cannibal_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Root cause</div><h2>Clusters de template/componente</h2><p>Findings repetidos são agrupados por regra + selector quando existe selector confiável; sem selector, o agrupamento por título é apenas um agrupamento de ocorrências, não uma afirmação de causa compartilhada.</p><div class='table-wrap'><table><thead><tr><th>Regra</th><th>Sev.</th><th>Ocorrências</th><th>URLs</th><th>Devices</th><th>Selector/assinatura</th><th>Causa compartilhada</th></tr></thead><tbody>{cluster_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Field experience</div><h2>CrUX History</h2><div class='table-wrap'><table><thead><tr><th>Target</th><th>Scope</th><th>Form factor</th><th>Métrica</th><th>Período</th><th>p75</th><th>Good</th><th>Poor</th></tr></thead><tbody>{crux_rows}</tbody></table></div></section>
<section class='panel'><div class='kicker'>Referências</div><h2>Documentação pública usada</h2><ul>{refs}</ul></section>
<footer class='footer'>Search & AI Observability é complementar e reconstruível. Fonte primária do audit permanece audit.db; dados externos ficam em observability.db + artifacts/observability.</footer>
"""
    return _shell(nav, body)


def _dataset_row(item: dict[str, Any]) -> str:
    period = " → ".join(value for value in (str(item.get("period_start") or ""), str(item.get("period_end") or "")) if value) or "-"
    return f"<tr><td class='mono'>{escape(str(item['dataset_id']))}</td><td>{escape(str(item['source_type']))}</td><td>{escape(str(item['capture_method']))}</td><td>{escape(period)}</td><td class='mono'>{escape(str(item['artifact_path']))}</td><td>{escape(str(item['collected_at']))}</td></tr>"


def _diagnostic_row(item: Diagnostic) -> str:
    ref = f"<a href='{escape(item.reference, quote=True)}' target='_blank' rel='noopener'>oficial ↗</a>" if item.reference else "-"
    return f"<tr><td>{escape(item.severity)}</td><td>{escape(item.domain)}</td><td class='mono'>{escape(item.code)}</td><td>{escape(item.status)}</td><td class='mono'>{escape(item.url or '-')}</td><td>{escape(item.device or '-')}</td><td><strong>{escape(item.title)}</strong><br>{escape(item.detail)}</td><td>{ref}</td></tr>"


def _matrix_row(item: dict[str, Any]) -> str:
    return "<tr>" + "".join(f"<td{(' class=mono' if index in {0,4,8} else '')}>{escape(str(value if value not in (None,'') else '-'))}</td>" for index, value in enumerate((item.get('url'),item.get('device'),item.get('http_status'),item.get('meta_robots'),item.get('declared_canonical'),item.get('source'),item.get('verdict'),item.get('indexing_state'),item.get('selected_canonical'),item.get('canonical_alignment')))) + "</tr>"


def _intent_row(item: dict[str, Any]) -> str:
    return f"<tr><td>{escape(str(item.get('source') or '-'))}</td><td>{escape(str(item.get('surface') or '-'))}</td><td>{escape(str(item['query']))}</td><td class='mono'>{escape(str(item['url']))}</td><td>{escape(_num(item.get('impressions')))}</td><td>{escape(_num(item.get('clicks')))}</td><td>{float(item.get('best_overlap') or 0):.2f}</td><td>{escape(str(item['status']))}</td></tr>"


def _cannibal_row(item: dict[str, Any]) -> str:
    distribution = "; ".join(f"{row['url']} ({float(row['impressions_share'])*100:.1f}%)" for row in item['urls'])
    return f"<tr><td>{escape(str(item['source']))}</td><td>{escape(str(item['query']))}</td><td>{_num(item['total_impressions'])}</td><td class='mono'>{escape(distribution)}</td><td>{escape(str(item['status']))}</td></tr>"


def _cluster_row(item: dict[str, Any]) -> str:
    urls = ", ".join(item['urls'][:8]) + (" …" if len(item['urls']) > 8 else "")
    return f"<tr><td>{escape(str(item['rule_id']))}</td><td>{escape(str(item['severity']))}</td><td>{int(item['occurrences'])}</td><td class='mono'>{escape(urls or '-')}</td><td>{escape(', '.join(item['devices']) or '-')}</td><td class='mono'>{escape(str(item['signature']))}</td><td>{'SIM' if item['probable_shared_cause'] else 'NÃO COMPROVADA'}</td></tr>"


def _crux_row(item: dict[str, Any]) -> str:
    period = f"{item.get('period_start') or '-'} → {item.get('period_end') or '-'}"
    return f"<tr><td class='mono'>{escape(str(item['target']))}</td><td>{escape(str(item['target_scope']))}</td><td>{escape(str(item.get('form_factor') or 'ALL'))}</td><td>{escape(str(item['metric']))}</td><td>{escape(period)}</td><td>{escape(_num(item.get('p75')))}</td><td>{escape(_pct(item.get('good_density')))}</td><td>{escape(_pct(item.get('poor_density')))}</td></tr>"


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"


def _num(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.2f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value)*100:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _sev(value: str) -> int:
    return {"INFO":0,"LOW":1,"MEDIUM":2,"HIGH":3,"CRITICAL":4}.get(value.upper(),0)


def _shell(nav: str, body: str) -> str:
    return f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Search & AI Observability · RASAi</title><link rel='stylesheet' href='css/site.css'></head><body><div class='app-shell'>{nav}<main class='app-main'>{body}</main></div></body></html>"
