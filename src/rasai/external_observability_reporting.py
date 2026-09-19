"""Report projections for external observational datasets.

Detailed external data remains in observability.db/artifacts.  This module only adds
clearly labelled, non-scoring panels to reports where the scope is semantically
relevant.  Repeated enrichment is idempotent through explicit HTML markers.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
import json
from pathlib import Path
from rasai.observability.store import observability_database_path
from typing import Any

from rasai.observability.external_sources import archive_rows, behavioral_rows
from rasai.observability.store import ObservabilityStore

_MARKER_OBSERVABILITY = "RASAI_EXTERNAL_OBSERVABILITY_DETAIL"
_MARKER_BEHAVIOR = "RASAI_CLARITY_BEHAVIORAL_UX"
_MARKER_ARCHIVE = "RASAI_COMMON_CRAWL_HISTORY"
_MARKER_CRUX = "RASAI_CRUX_HISTORY_PERFORMANCE"


def enrich_external_observability_reports(*, audit_workspace: str | Path) -> tuple[Path, ...]:
    workspace = Path(audit_workspace)
    report_dir = workspace / "report"
    if not report_dir.is_dir():
        return ()
    behavior = behavioral_rows(workspace)
    archive = archive_rows(workspace)
    crux = _crux_rows(workspace)
    changed: list[Path] = []

    path = report_dir / "observability.html"
    if _inject(path, _MARKER_OBSERVABILITY, _observability_panel(behavior, archive)):
        changed.append(path)

    path = report_dir / "apdex-experience.html"
    if _inject(path, _MARKER_BEHAVIOR, _behavior_panel(behavior)):
        changed.append(path)

    path = report_dir / "crawling-discovery.html"
    if _inject(path, _MARKER_ARCHIVE, _archive_panel(archive)):
        changed.append(path)

    path = report_dir / "web-performance.html"
    if _inject(path, _MARKER_CRUX, _crux_panel(crux)):
        changed.append(path)

    return tuple(dict.fromkeys(changed))


def _crux_rows(workspace: Path) -> list[dict[str, Any]]:
    if not (observability_database_path(workspace)).is_file():
        return []
    with ObservabilityStore(workspace) as store:
        return [dict(row) for row in store.crux_rows()]


def _observability_panel(behavior: list[dict[str, Any]], archive: list[dict[str, Any]]) -> str:
    if not behavior and not archive:
        return ""
    parts = [
        "<section class='panel'>",
        "<div class='kicker'>External analytics</div><h2>Behavioral UX &amp; Web history</h2>",
        "<p>Dados externos observacionais permanecem fora de SARI-001/SCORE-GEO-004. "
        "Clarity representa agregados comportamentais; Common Crawl representa presença histórica em corpus público.</p>",
        "<div class='metric-grid'>",
        _metric("Clarity observations", len(behavior)),
        _metric("Common Crawl captures", len(archive)),
        "</div>",
    ]
    if behavior:
        parts.append("<h3>Microsoft Clarity · agregados</h3>")
        parts.append("<div class='table-wrap'><table><thead><tr><th>Métrica</th><th>URL</th><th>Device</th><th>Dimensões</th><th>Valores</th></tr></thead><tbody>")
        for row in behavior[:200]:
            parts.append(_behavior_row(row))
        parts.append("</tbody></table></div>")
    if archive:
        parts.append("<h3>Common Crawl · histórico de URLs</h3>")
        parts.append("<div class='table-wrap'><table><thead><tr><th>URL</th><th>Collection</th><th>Captura</th><th>HTTP</th><th>MIME</th></tr></thead><tbody>")
        for row in archive[-200:]:
            parts.append(_archive_row(row))
        parts.append("</tbody></table></div>")
    parts.append("</section>")
    return "".join(parts)


def _behavior_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    friction_terms = (
        "rage click", "dead click", "quickback", "excessive scroll", "script error",
        "error click", "engagement", "scroll depth", "traffic",
    )
    selected = [row for row in rows if any(term in str(row.get("metric_name") or "").casefold() for term in friction_terms)]
    if not selected:
        selected = rows
    return (
        "<section class='panel'>"
        "<div class='kicker'>Observed Behavioral UX</div><h2>Microsoft Clarity</h2>"
        "<p>Agregados de comportamento real complementam o Apdex sintético; não são convertidos em Apdex, "
        "não provam causalidade e não alteram o score. URL e device só aparecem quando fornecidos pela dimensão consultada.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Métrica</th><th>URL</th><th>Device</th><th>Dimensões</th><th>Valores</th></tr></thead><tbody>"
        + "".join(_behavior_row(row) for row in selected[:80])
        + "</tbody></table></div></section>"
    )


def _archive_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("target_url") or "")].append(row)
    table_rows: list[str] = []
    for url, items in sorted(grouped.items()):
        dates = sorted(str(item.get("captured_at") or "") for item in items if item.get("captured_at"))
        collections = sorted({str(item.get("collection") or "") for item in items if item.get("collection")})
        table_rows.append(
            "<tr>"
            f"<td class='mono'>{escape(url)}</td>"
            f"<td>{len(items)}</td>"
            f"<td>{len(collections)}</td>"
            f"<td>{escape(dates[0] if dates else '-')}</td>"
            f"<td>{escape(dates[-1] if dates else '-')}</td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<div class='kicker'>Historical public crawl evidence</div><h2>Common Crawl</h2>"
        "<p>Indica somente que a URL foi observada em índices do Common Crawl. Não comprova indexação Google/Bing, "
        "ranking, disponibilidade atual nem acesso por um crawler de IA.</p>"
        "<div class='table-wrap'><table><thead><tr><th>URL</th><th>Capturas</th><th>Collections</th><th>Primeira</th><th>Mais recente</th></tr></thead><tbody>"
        + "".join(table_rows)
        + "</tbody></table></div></section>"
    )


def _crux_panel(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("target") or ""),
            str(row.get("form_factor") or "ALL"),
            str(row.get("metric") or ""),
        )
        current = latest.get(key)
        if current is None or str(row.get("period_end") or "") > str(current.get("period_end") or ""):
            latest[key] = row
    body = []
    for key in sorted(latest):
        row = latest[key]
        body.append(
            "<tr>"
            f"<td class='mono'>{escape(str(row.get('target') or '-'))}</td>"
            f"<td>{escape(str(row.get('target_scope') or '-'))}</td>"
            f"<td>{escape(str(row.get('form_factor') or 'ALL'))}</td>"
            f"<td>{escape(str(row.get('metric') or '-'))}</td>"
            f"<td>{escape(str(row.get('period_end') or '-'))}</td>"
            f"<td>{escape(_num(row.get('p75')))}</td>"
            f"<td>{escape(_pct(row.get('good_density')))}</td>"
            f"<td>{escape(_pct(row.get('poor_density')))}</td>"
            "</tr>"
        )
    return (
        "<section class='panel'>"
        "<div class='kicker'>Field history</div><h2>CrUX History</h2>"
        "<p>Série de campo por origem e form factor. Permanece separada de Lighthouse lab, CrUX current e Apdex sintético.</p>"
        "<div class='table-wrap'><table><thead><tr><th>Target</th><th>Scope</th><th>Form factor</th><th>Métrica</th><th>Período final</th><th>p75</th><th>Good</th><th>Poor</th></tr></thead><tbody>"
        + "".join(body[:40])
        + "</tbody></table></div></section>"
    )


def _behavior_row(row: dict[str, Any]) -> str:
    dimensions = _compact_json(row.get("dimensions_json"))
    values = _compact_json(row.get("values_json"))
    return (
        "<tr>"
        f"<td>{escape(str(row.get('metric_name') or '-'))}</td>"
        f"<td class='mono'>{escape(str(row.get('normalized_url') or '-'))}</td>"
        f"<td>{escape(str(row.get('device') or '-'))}</td>"
        f"<td class='mono'>{escape(dimensions)}</td>"
        f"<td class='mono'>{escape(values)}</td>"
        "</tr>"
    )


def _archive_row(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td class='mono'>{escape(str(row.get('target_url') or '-'))}</td>"
        f"<td>{escape(str(row.get('collection') or '-'))}</td>"
        f"<td>{escape(str(row.get('captured_at') or '-'))}</td>"
        f"<td>{escape(str(row.get('status') or '-'))}</td>"
        f"<td>{escape(str(row.get('mime') or '-'))}</td>"
        "</tr>"
    )


def _compact_json(raw: Any) -> str:
    if raw in (None, ""):
        return "-"
    try:
        value = json.loads(str(raw)) if isinstance(raw, str) else raw
        if isinstance(value, dict):
            return "; ".join(f"{key}={value[key]}" for key in sorted(value)) or "-"
        return str(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(raw)


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><span>{escape(label)}</span><strong>{escape(str(value))}</strong></div>"


def _num(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _inject(path: Path, marker: str, html: str) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    original = text
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    while True:
        begin = text.find(start)
        if begin < 0:
            break
        finish = text.find(end, begin + len(start))
        if finish < 0:
            break
        text = text[:begin] + text[finish + len(end):]
    if html:
        block = start + html + end
        positions = [value for value in (text.find("<footer"), text.find("</main>"), text.find("</body>")) if value >= 0]
        position = min(positions) if positions else len(text)
        text = text[:position] + block + text[position:]
    if text == original:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True
