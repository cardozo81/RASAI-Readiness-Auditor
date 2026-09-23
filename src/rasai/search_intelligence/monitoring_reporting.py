"""Longitudinal Search Intelligence report for the product control plane."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from rasai.time_contract import localize_html_timestamps

from .monitoring import SearchMonitoringRepository


REPORT_FILE = "search-intelligence.html"
_INDEX_MARKER = "<section id='search-monitoring-summary'"


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(label)}</small><strong>{escape(str(value))}</strong></div>"


def _position(run) -> str:
    value = run.snapshot.customer_position
    if value is not None:
        return f"#{value}"
    return run.snapshot.domain_status


def _change_label(run) -> str:
    if not run.changes:
        return "-"
    preferred = next(
        (
            item.status
            for item in run.changes
            if item.status in {
                "POSITION_IMPROVED", "POSITION_REGRESSED", "POSITION_UNCHANGED",
                "ENTERED_OBSERVED_DEPTH", "LEFT_OBSERVED_DEPTH", "NOT_COMPARABLE",
            }
        ),
        run.changes[0].status,
    )
    return preferred


def _timeline(runs) -> str:
    rows = []
    for run in reversed(runs):
        rows.append(
            "<tr>"
            f"<td>{escape(run.completed_at)}</td>"
            f"<td>{escape(_position(run))}</td>"
            f"<td>{escape(run.snapshot.provider)}</td>"
            f"<td>{escape(str(run.snapshot.data_mode or '-'))}</td>"
            f"<td>{escape(_change_label(run))}</td>"
            f"<td>{escape(', '.join(run.snapshot.competitor_domains_ahead) or '-')}</td>"
            f"<td>{escape(', '.join(run.snapshot.gap_codes) or '-')}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='7'>Nenhuma execução persistida.</td></tr>"


def _changes(run) -> str:
    if not run.changes:
        return "<li>Nenhuma mudança materializada.</li>"
    rendered = []
    for item in run.changes:
        delta = f"; delta={item.delta:g} {item.unit or ''}" if item.delta is not None else ""
        rendered.append(
            "<li>"
            f"<strong>{escape(item.status)}</strong> - {escape(item.label)}: "
            f"{escape(str(item.before))} → {escape(str(item.after))}{escape(delta)}"
            + (f"<br><small>{escape(item.note)}</small>" if item.note else "")
            + "</li>"
        )
    return "".join(rendered)


def _enrich_platform_index(root: Path, *, query_count: int, active: int, run_count: int) -> None:
    """Add one idempotent navigation panel when Product Platform index already exists."""
    index = root / "index.html"
    if not index.is_file():
        return
    html = index.read_text(encoding="utf-8")
    if _INDEX_MARKER in html:
        start = html.index(_INDEX_MARKER)
        end = html.find("</section>", start)
        if end >= 0:
            html = html[:start] + html[end + len("</section>"):]
    section = (
        "<section id='search-monitoring-summary' class='panel'>"
        "<div class='eyebrow'>Search Intelligence Monitoring</div>"
        "<h2>Queries observadas longitudinalmente</h2>"
        "<p>Superfície operacional do control plane, separada dos AUDs imutáveis e do scoring.</p>"
        "<div class='metrics'>"
        + _metric("Queries registradas", query_count)
        + _metric("Queries ativas", active)
        + _metric("Execuções exibidas", run_count)
        + "</div>"
        f"<p><a href='{REPORT_FILE}'>Abrir Search Intelligence Monitoring</a></p>"
        "</section>"
    )
    if "</main>" in html:
        html = html.replace("</main>", section + "</main>", 1)
    elif "</body>" in html:
        html = html.replace("</body>", section + "</body>", 1)
    else:
        html += section
    index.write_text(html, encoding="utf-8", newline="\n")


def write_search_monitoring_report(
    repository: SearchMonitoringRepository,
    output_dir: str | Path,
    *,
    property_id: str | None = None,
    environment_id: str | None = None,
) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / REPORT_FILE
    groups = []
    queries = repository.list_queries()
    if property_id:
        queries = tuple(item for item in queries if item.property_id == property_id)
    if environment_id:
        queries = tuple(item for item in queries if item.environment_id == environment_id)

    total_runs = 0
    active = sum(item.enabled for item in queries)
    for query in queries:
        runs = repository.list_runs(query.query_id, limit=20)
        total_runs += len(runs)
        latest = runs[0] if runs else None
        latest_metrics = (
            _metric("Última posição", _position(latest))
            + _metric("Última mudança", _change_label(latest))
            + _metric("Provider/data mode", f"{latest.snapshot.provider} / {latest.snapshot.data_mode or '-'}")
            + _metric("Concorrentes à frente", len(latest.snapshot.competitor_domains_ahead))
            + _metric("Gaps determinísticos", len(latest.snapshot.gap_codes))
            + _metric("Competitive AI", latest.snapshot.ai_state or "não executada")
            if latest is not None
            else _metric("Estado", "sem execução")
        )
        change_block = (
            f"<details><summary>Mudanças da execução mais recente</summary><ul>{_changes(latest)}</ul></details>"
            if latest is not None
            else ""
        )
        groups.append(
            f"""<section class='panel'><div class='eyebrow'>Registered query · {escape(query.query_id)}</div>
<h2>{escape(query.query)}</h2><p><code>{escape(query.domain_of_interest)}</code> · {escape(query.engine)} · {escape(query.country)} · {escape(query.language)} · {escape(query.device)} · depth {query.requested_depth}</p>
<div class='metrics'>{latest_metrics}</div>
<p><strong>Execução:</strong> mode={escape(query.mode)}; provider={escape(query.provider)}; competitive={query.competitive}; compare_content={query.compare_content}; ai={query.ai_competitive}. <strong>Schedule:</strong> {escape(query.schedule_id or 'manual')}.</p>
{change_block}
<div class='table'><table><thead><tr><th>Coletado em</th><th>Posição/estado</th><th>Provider</th><th>Data mode</th><th>Mudança</th><th>Domínios à frente</th><th>Gaps</th></tr></thead><tbody>{_timeline(runs)}</tbody></table></div>
</section>"""
        )

    nav = "<p><a href='index.html'>Voltar ao Product Platform</a></p>" if (root / "index.html").is_file() else ""
    body = "".join(groups) or "<section class='panel'><h2>Nenhuma query registrada</h2><p>Use <code>rasai search-monitor query add</code> para criar o primeiro contexto recorrente.</p></section>"
    html = f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Search Intelligence Monitoring - RASAi</title>
<style>body{{font-family:system-ui,sans-serif;margin:0;background:#f5f6f8;color:#17202a}}main{{max-width:1280px;margin:auto;padding:28px}}.hero,.panel{{background:white;border:1px solid #dfe3e8;border-radius:14px;padding:22px;margin:0 0 18px}}.eyebrow{{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:#59636e}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:16px 0}}.metric{{border:1px solid #e2e6ea;border-radius:10px;padding:12px}}.metric small{{display:block;color:#65707b}}.metric strong{{display:block;margin-top:4px}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #e5e8eb;vertical-align:top}}code{{overflow-wrap:anywhere}}.notice{{border-left:4px solid #707b86;padding:10px 14px;background:#f7f8fa}}</style></head><body><main>
<header class='hero'><div class='eyebrow'>SEARCH-MONITOR-001 · longitudinal control-plane projection</div><h1>Search Intelligence - monitoramento recorrente</h1><p>Timeline por query registrada. Posição, concorrentes à frente, sinais de conteúdo e Competitive AI permanecem observacionais/non-scoring. Mudanças temporais não provam causalidade de ranking.</p><div class='metrics'>{_metric('Queries registradas', len(queries))}{_metric('Queries ativas', active)}{_metric('Execuções exibidas', total_runs)}</div>{nav}</header>
<div class='notice'><strong>Separação de evidência:</strong> esta página é uma projeção longitudinal do control plane. Ela não reescreve <code>AUD-*/audit.db</code> nem altera SARI-001/SCORE-GEO-004. Raw SERP evidence e manifests de execução ficam no evidence root de monitoring.</div>
{body}
</main></body></html>"""
    html = localize_html_timestamps(html)
    path.write_text(html, encoding="utf-8", newline="\n")
    _enrich_platform_index(root, query_count=len(queries), active=active, run_count=total_runs)
    return path
