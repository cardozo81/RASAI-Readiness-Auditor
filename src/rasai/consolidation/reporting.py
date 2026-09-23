"""Static HTML snapshot generation for consolidated historical reports."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Iterable
import hashlib
import json
import math

from .models import ConsolidatedData, GenerationResult, NumericSummary, RefreshResult
from rasai.catalog_report_public_labels import public_label
from rasai.report_presentation import humanize_report_html
from rasai.report_semantics import enhance_report_html

REPORT_FORMAT_VERSION = "CONS-3"

_DIMENSIONS = {
    "OVERALL_READINESS": "SARI - Índice de prontidão para Busca e IA",
    "DISCOVERY_ACCESS": "Acesso e descoberta",
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Indexabilidade e canonicalização",
    "CONTENT_EXTRACTABILITY": "Renderização e extração",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidência e confiança",
    "INTENT_COVERAGE": "Cobertura de intenção",
    "CONTENT_VALUE": "Valor de conteúdo",
    "Answerability": "Capacidade de resposta",
    "Citation Readiness": "Preparação para citação",
    "Structured Data": "Dados estruturados",
    "Evidence & Trust": "Evidência e confiança",
    "Intent Coverage": "Cobertura de intenção",
    "Entity Clarity": "Clareza de entidades",
    "Semantic Structure": "Estrutura semântica",
    "Content Value": "Valor de conteúdo",
    "Discovery & Crawler Access": "Acesso e descoberta",
    "Rendering & Extractability": "Renderização e extração",
    "Indexability": "Indexabilidade e canonicalização",
}
_CONFIDENCE = {
    "VERY_HIGH": "Muito alta",
    "HIGH": "Alta",
    "MEDIUM": "Média",
    "LOW": "Baixa",
    "VERY_LOW": "Muito baixa",
    "UNAVAILABLE": "Indisponível",
    "NOT_AVAILABLE": "Indisponível",
    "NOT_APPLICABLE": "Não aplicável",
    "NOT_DETERMINABLE": "Não determinada",
    "UNKNOWN": "Não determinada",
}
_CONSOLIDATION = {
    "CONSOLIDATED": "Consolidado",
    "PARTIAL": "Parcial",
    "NOT_CONSOLIDATED": "Não consolidado",
    "NOT_APPLICABLE": "Não aplicável",
    "COMPLETE": "Completo",
}
_SEVERITY = {"CRITICAL": "Crítica", "HIGH": "Alta", "MEDIUM": "Média", "LOW": "Baixa", "INFO": "Informativa", "UNKNOWN": "Desconhecida"}
_FINDING_CATEGORY = {
    "ACCESSIBILITY": "Acessibilidade",
    "AI_ACCESS": "Acesso por IA",
    "BEST_PRACTICES": "Boas práticas",
    "CONTENT": "Conteúdo",
    "CONTENT_SEMANTICS": "Conteúdo e semântica",
    "CONTENT_SUGGESTIONS": "Conteúdo, semântica e dados estruturados",
    "CRAWLABILITY": "Rastreamento",
    "DISCOVERY": "Descoberta",
    "FILES_DISCOVERY": "Descoberta de arquivos",
    "GEO": "Busca e IA",
    "GEO_AI_READINESS": "Busca e IA / SARI",
    "HTML": "HTML",
    "INDEXABILITY": "Indexabilidade e canonicalização",
    "INFRASTRUCTURE": "Engenharia e infraestrutura",
    "PERFORMANCE": "Desempenho",
    "SEARCH": "Busca",
    "SEARCH_AI": "Busca e IA",
    "SEARCH_RANKING": "Busca e ranqueamento",
    "SECURITY": "Segurança",
    "SEMANTICS": "Semântica",
    "SEMANTICS_STRUCTURE": "Estrutura semântica",
    "SEO": "SEO",
    "STRUCTURED_DATA": "Dados estruturados",
    "TECHNICAL": "Técnico",
    "TECHNICAL_HTML": "HTML técnico",
    "TEST": "Teste",
    "UX": "Experiência",
    "WEB_PERFORMANCE": "Desempenho Web",
    "WEB_VITAL": "Core Web Vitals",
    "WEB_VITALS": "Core Web Vitals",
    "Answerability": "Capacidade de resposta",
    "Citation Readiness": "Preparação para citação",
    "Structured Data": "Dados estruturados",
    "Evidence & Trust": "Evidência e confiança",
    "Intent Coverage": "Cobertura de intenção",
    "Entity Clarity": "Clareza de entidades",
    "Semantic Structure": "Estrutura semântica",
    "Content Value": "Valor de conteúdo",
    "Discovery & Crawler Access": "Acesso e descoberta",
    "Rendering & Extractability": "Renderização e extração",
    "Indexability": "Indexabilidade e canonicalização",
}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _request_fingerprint(data: ConsolidatedData) -> str:
    payload = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "filters": data.filters.canonical(),
        "source_fingerprint": data.source_fingerprint,
    }
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _find_existing(root: Path, fingerprint: str) -> tuple[Path, Path] | None:
    output_root = root / "consolidated"
    if not output_root.is_dir():
        return None
    for manifest in sorted(output_root.glob("CONS-*/manifest.json"), reverse=True):
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("request_fingerprint") != fingerprint:
            continue
        report = manifest.parent / "report.html"
        if report.is_file():
            return report, manifest
    return None


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}"


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _pct_points(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def _date_label(value: object) -> str:
    text = str(value or "")
    if not text:
        return "-"
    date = text[:10]
    try:
        parsed = datetime.fromisoformat(date)
        return parsed.strftime("%d/%m/%Y")
    except ValueError:
        return escape(date)


def _device(value: object) -> str:
    text = str(value or "UNKNOWN").upper()
    return {"MOBILE": "Dispositivo móvel", "DESKTOP": "Desktop", "BOTH": "Dispositivo móvel + Desktop"}.get(text, text.title())


def _dimension(value: object) -> str:
    text = str(value or "UNKNOWN")
    if text == "OVERALL_READINESS":
        return "SARI - Índice de prontidão para Busca e IA"
    return _DIMENSIONS.get(text) or public_label(text) or text.replace("_", " ").title()


def _audit_href(value: object) -> str:
    audit_id = str(value or "").strip()
    return f"../../{audit_id}/report-catalog/index.html" if audit_id.startswith("AUD-") else ""


def _audit_link(value: object) -> str:
    audit_id = str(value or "").strip()
    href = _audit_href(audit_id)
    if not href:
        return escape(audit_id or "-")
    return (
        f"<a class='audit-link' href='{escape(href, quote=True)}' target='_blank' "
        f"rel='noopener noreferrer'>{escape(audit_id)}</a>"
    )


def _confidence(value: object) -> str:
    text = str(value or "UNKNOWN").upper()
    return _CONFIDENCE.get(text, "Não determinada")


def _consolidation(value: object) -> str:
    text = str(value or "UNKNOWN").upper()
    return _CONSOLIDATION.get(text, text.replace("_", " ").title())


def _number(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_tone(value: object) -> str:
    number = _number(value)
    if number is None:
        return "neutral"
    if number >= 75:
        return "good"
    if number >= 60:
        return "warn"
    if number >= 40:
        return "low"
    return "bad"


def _apdex_tone(value: object) -> str:
    number = _number(value)
    if number is None:
        return "neutral"
    if number >= 0.85:
        return "good"
    if number >= 0.70:
        return "warn"
    return "bad"


def _performance_tone(name: object, value: object) -> str:
    number = _number(value)
    if number is None:
        return "neutral"
    label = str(name or "").casefold()
    if label.startswith("lighthouse "):
        return "good" if number >= 90 else "warn" if number >= 50 else "bad"
    if "lcp de campo" in label:
        return "good" if number <= 2500 else "warn" if number <= 4000 else "bad"
    if "inp de campo" in label:
        return "good" if number <= 200 else "warn" if number <= 500 else "bad"
    if "cls de campo" in label:
        return "good" if number <= 0.1 else "warn" if number <= 0.25 else "bad"
    return "neutral"


def _result_value_html(value: object, *, tone: str, digits: int = 2) -> str:
    safe = tone if tone in {"good", "warn", "low", "bad", "neutral"} else "neutral"
    rendered = _fmt(_number(value), digits)
    return f"<strong class='result-value {safe}'>{escape(rendered)}</strong>"


def _state_text_html(value: object) -> str:
    label = str(value or "-")
    key = label.casefold()
    neutral = (
        "automático", "não aplicável", "não determinado", "não determinada",
        "não determinável", "não solicitado", "não solicitada", "não elegível",
    )
    if any(key == item or key.startswith(item + " ") for item in neutral):
        tone = "neutral"
    elif key in {"consolidado", "concluído", "completo", "aprovado", "válido", "disponível"}:
        tone = "good"
    elif key in {"parcial", "não consolidado", "atenção"}:
        tone = "warn"
    elif key in {"não aprovado", "falhou", "erro", "bloqueado"}:
        tone = "bad"
    else:
        return escape(label)
    return f"<span class='state-text {tone}'>{escape(label)}</span>"


def _count_tone(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if raw in {"PASS", "GOOD", "SUCCESS", "CONSOLIDATED", "SATISFIED"}:
        return "good"
    if raw in {"WARNING", "NEEDS_IMPROVEMENT", "PARTIAL", "TOLERATING", "MEDIUM"}:
        return "warn"
    if raw in {"FAIL", "POOR", "CRITICAL", "HIGH", "FRUSTRATED"}:
        return "bad"
    if raw in {"NOT_APPLICABLE", "NOT_DETERMINABLE", "UNKNOWN", "NOT_REQUESTED", "DISABLED"}:
        return "neutral"
    return None


def _human_counts(values: dict[str, int], labels: dict[str, str] | None = None) -> str:
    if not values:
        return "-"
    total = sum(max(0, int(value)) for value in values.values())
    pieces: list[str] = []
    for key, count in sorted(values.items(), key=lambda item: (-int(item[1]), str(item[0]))):
        raw_key = str(key)
        label_map = labels or {}
        label = (
            label_map.get(raw_key)
            or label_map.get(raw_key.upper())
            or next((value for candidate, value in label_map.items() if str(candidate).casefold() == raw_key.casefold()), None)
            or raw_key.replace("_", " ").title()
        )
        suffix = f" · {count / total * 100:.0f}%" if total else ""
        tone = _count_tone(raw_key)
        css = f" chip state-count {tone}" if tone else "chip"
        pieces.append(f"<span class='{css.strip()}'><strong>{escape(label)}</strong> {int(count)}{suffix}</span>")
    return "".join(pieces)


def _latest(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    material = list(rows)
    if not material:
        return None
    return max(material, key=lambda row: str(row.get("event_time") or row.get("calculated_at") or ""))


def _latest_score_row(data: ConsolidatedData, device: str, dimension: str) -> dict[str, Any] | None:
    return _latest(
        row for row in data.score_history
        if str(row.get("device") or "").upper() == device.upper()
        and str(row.get("dimension") or "") == dimension
    )


def _compatible_score_rows(data: ConsolidatedData, device: str, dimension: str) -> list[dict[str, Any]]:
    rows = [
        row for row in data.score_history
        if str(row.get("device") or "").upper() == device.upper()
        and str(row.get("dimension") or "") == dimension
        and _number(row.get("value")) is not None
    ]
    rows.sort(key=lambda row: str(row.get("event_time") or row.get("calculated_at") or ""))
    if not rows:
        return []
    latest = rows[-1]
    version = str(latest.get("scoring_version") or "UNKNOWN")
    universe = str(latest.get("url_universe") or "UNKNOWN")
    return [
        row for row in rows
        if str(row.get("scoring_version") or "UNKNOWN") == version
        and str(row.get("url_universe") or "UNKNOWN") == universe
    ]


def _stats_advanced_rows(label: str, stats: NumericSummary, *, coverage: float | None = None) -> str:
    if stats.count <= 1:
        return ""
    return (
        "<tr>"
        f"<td>{escape(label)}</td><td>{stats.count}</td><td>{_fmt(stats.initial)}</td><td>{_fmt(stats.current)}</td>"
        f"<td>{_fmt(stats.mean)}</td><td>{_fmt(stats.median)}</td><td>{_fmt(stats.minimum)}</td>"
        f"<td>{_fmt(stats.maximum)}</td><td>{_fmt(stats.change_absolute)}</td>"
        f"<td>{_pct_points(stats.change_percent)}</td><td>{_pct(coverage)}</td></tr>"
    )


def _svg_line_chart(
    *,
    title: str,
    rows: list[dict[str, Any]],
    primary_field: str,
    primary_label: str,
    secondary_field: str | None = None,
    secondary_label: str | None = None,
    fixed_0_100: bool = False,
) -> str:
    points: list[tuple[str, float, float | None]] = []
    for row in rows:
        primary = _number(row.get(primary_field))
        if primary is None:
            continue
        secondary = _number(row.get(secondary_field)) if secondary_field else None
        if secondary_field == "coverage" and secondary is not None:
            secondary *= 100.0
        points.append((_date_label(row.get("event_time") or row.get("calculated_at")), primary, secondary))
    if len(points) < 2:
        return ""

    width, height = 920, 270
    left, right, top, bottom = 52, 24, 24, 54
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [item[1] for item in points] + [item[2] for item in points if item[2] is not None]
    if fixed_0_100:
        y_min, y_max = 0.0, 100.0
    else:
        y_min = min(0.0, min(values))
        y_max = max(values)
        if math.isclose(y_min, y_max):
            y_max = y_min + 1.0
        else:
            pad = (y_max - y_min) * 0.1
            y_max += pad
    def x_at(index: int) -> float:
        return left + (plot_w * index / max(1, len(points) - 1))
    def y_at(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    primary_coords = " ".join(f"{x_at(i):.1f},{y_at(item[1]):.1f}" for i, item in enumerate(points))
    secondary_coords = " ".join(
        f"{x_at(i):.1f},{y_at(item[2]):.1f}" for i, item in enumerate(points) if item[2] is not None
    )
    grid: list[str] = []
    for step in range(5):
        value = y_min + (y_max - y_min) * step / 4
        y = y_at(value)
        grid.append(f"<line x1='{left}' y1='{y:.1f}' x2='{width-right}' y2='{y:.1f}' class='grid-line'/>")
        grid.append(f"<text x='{left-8}' y='{y+4:.1f}' text-anchor='end' class='axis-label'>{value:.0f}</text>")
    labels: list[str] = []
    label_every = max(1, math.ceil(len(points) / 8))
    for i, item in enumerate(points):
        if i % label_every == 0 or i == len(points) - 1:
            labels.append(f"<text x='{x_at(i):.1f}' y='{height-20}' text-anchor='middle' class='axis-label'>{escape(item[0])}</text>")
    dots = "".join(
        f"<circle cx='{x_at(i):.1f}' cy='{y_at(item[1]):.1f}' r='3.5' class='dot primary-dot'><title>{escape(item[0])}: {item[1]:.2f}</title></circle>"
        for i, item in enumerate(points)
    )
    second_dots = "" if not secondary_coords else "".join(
        f"<circle cx='{x_at(i):.1f}' cy='{y_at(item[2]):.1f}' r='3' class='dot secondary-dot'><title>{escape(item[0])}: {secondary_label or 'Série 2'} {item[2]:.1f}</title></circle>"
        for i, item in enumerate(points) if item[2] is not None
    )
    legend = f"<span class='legend primary-legend'>{escape(primary_label)}</span>"
    if secondary_coords and secondary_label:
        legend += f"<span class='legend secondary-legend'>{escape(secondary_label)}</span>"
    qualifier = "Variação entre dois pontos; não caracteriza tendência." if len(points) == 2 else f"Série histórica descritiva com {len(points)} pontos comparáveis."
    return f"""
    <article class='chart-card'>
      <div class='chart-heading'><div><h3>{escape(title)}</h3><p>{escape(qualifier)}</p></div><div class='legend-row'>{legend}</div></div>
      <div class='chart-scroll'><svg viewBox='0 0 {width} {height}' role='img' aria-label='{escape(title)}'>
        {''.join(grid)}
        <polyline points='{primary_coords}' class='trend-line primary-line'/>{dots}
        {f"<polyline points='{secondary_coords}' class='trend-line secondary-line'/>{second_dots}" if secondary_coords else ''}
        {''.join(labels)}
      </svg></div>
    </article>
    """


def _historical_mode(data: ConsolidatedData) -> tuple[str, str]:
    count = len(data.audits)
    if count <= 1:
        return "Snapshot", "Há somente uma auditoria no universo filtrado. Média, mediana e variação temporal não acrescentam evidência e são ocultadas por padrão."
    if count == 2:
        return "Comparação de dois pontos", "Dois pontos permitem medir variação, mas não sustentam uma conclusão de tendência."
    return "Série histórica descritiva", f"Há {count} auditorias no universo filtrado. Tendências são descritivas e não demonstram causalidade."


def _render_executive(data: ConsolidatedData) -> str:
    mode, mode_note = _historical_mode(data)
    bullets: list[str] = [f"<li><strong>Base histórica:</strong> {escape(mode)}. {escape(mode_note)}</li>"]
    for device in sorted({str(row.get('device') or '') for row in data.score_history if row.get('device')}):
        overall = _latest_score_row(data, device, "OVERALL_READINESS")
        if overall and _number(overall.get("value")) is not None:
            state = _consolidation(overall.get("consolidation_status"))
            score_label = "SARI" if str(overall.get("consolidation_status") or "").upper() == "CONSOLIDATED" else "pontuação parcial de readiness"
            bullets.append(
                f"<li><strong>{escape(_device(device))}:</strong> {escape(score_label)} {_fmt(_number(overall.get('value')))} / 100, "
                f"cobertura {_pct(_number(overall.get('coverage')))}, confiança {escape(_confidence(overall.get('confidence')))} e estado {escape(state)}.</li>"
            )
        latest_audit_id = str(overall.get("audit_id") or "") if overall else ""
        dimensions = [
            row for row in data.score_history
            if overall is not None
            and str(row.get("audit_id") or "") == latest_audit_id
            and str(row.get("device") or "").upper() == device.upper()
            and str(row.get("dimension") or "") != "OVERALL_READINESS"
            and _number(row.get("value")) is not None
        ]
        if dimensions:
            latest_by_dimension: dict[str, dict[str, Any]] = {}
            for row in dimensions:
                key = str(row.get("dimension"))
                current = latest_by_dimension.get(key)
                if current is None or str(row.get("event_time") or "") > str(current.get("event_time") or ""):
                    latest_by_dimension[key] = row
            weakest = min(latest_by_dimension.values(), key=lambda row: float(row["value"]))
            bullets.append(
                f"<li><strong>Ponto de atenção {escape(_device(device))}:</strong> menor dimensão mensurada no estado atual: "
                f"{escape(_dimension(weakest.get('dimension')))} ({_fmt(_number(weakest.get('value')))} / 100).</li>"
            )
    for perf in data.performance:
        perf_metric = next((item for item in perf.metrics if item.name == "Lighthouse Performance"), None)
        if perf_metric and perf_metric.statistics.current is not None:
            bullets.append(
                f"<li><strong>Desempenho {escape(_device(perf.device))}:</strong> Desempenho Lighthouse atual {_fmt(perf_metric.statistics.current)} / 100. "
                f"Métricas Core Web Vitals: {_human_counts(perf.cwv_counts)}.</li>"
            )
    for apdex in data.apdex:
        if apdex.small_groups and not apdex.final_groups:
            bullets.append(
                f"<li><strong>Apdex {escape(_device(apdex.device))}:</strong> {_fmt(apdex.weighted_apdex, 3)} com {apdex.valid_samples} amostras válidas, "
                "mas somente grupos classificados como amostra pequena; resultado diagnóstico, não conclusão robusta.</li>"
            )
        elif apdex.final_groups:
            bullets.append(
                f"<li><strong>Apdex {escape(_device(apdex.device))}:</strong> {_fmt(apdex.weighted_apdex, 3)} com {apdex.valid_samples} amostras válidas em grupo(s) final(is); "
                "a leitura permanece condicionada ao mesmo perfil sintético e ao mesmo limiar T.</li>"
            )
    return f"<section id='summary'><h2>Leitura para decisão</h2><ul class='decision-list'>{''.join(bullets)}</ul></section>"


def _render_score_trends(data: ConsolidatedData) -> str:
    devices = sorted({str(row.get("device") or "") for row in data.score_history if row.get("device")})
    charts: list[str] = []
    for device in devices:
        rows = _compatible_score_rows(data, device, "OVERALL_READINESS")
        chart = _svg_line_chart(
            title=f"Evolução do SARI - {_device(device)}",
            rows=rows,
            primary_field="value",
            primary_label="SARI",
            secondary_field="coverage",
            secondary_label="Cobertura",
            fixed_0_100=True,
        )
        if chart:
            charts.append(chart)
    if charts:
        return "<section id='evolution'><h2>Evolução</h2><p>Os gráficos utilizam apenas pontos comparáveis da versão de método e do universo de URLs mais recentes. Mudanças incompatíveis são excluídas da linha e permanecem documentadas nas limitações.</p>" + "".join(charts) + "</section>"
    mode, note = _historical_mode(data)
    return f"<section id='evolution'><h2>Evolução</h2><p class='empty'><strong>{escape(mode)}.</strong> {escape(note)} Não é desenhado gráfico de evolução com menos de dois pontos comparáveis.</p></section>"


def _render_dimension_matrix(data: ConsolidatedData) -> str:
    devices = sorted({str(row.get("device") or "") for row in data.score_history if row.get("device")})
    blocks: list[str] = []
    for device in devices:
        overall = _compatible_score_rows(data, device, "OVERALL_READINESS")
        if len(overall) < 2:
            continue
        latest = overall[-1]
        version = str(latest.get("scoring_version") or "UNKNOWN")
        universe = str(latest.get("url_universe") or "UNKNOWN")
        audit_order = [(str(row.get("audit_id")), str(row.get("event_time") or "")) for row in overall]
        audit_ids = [item[0] for item in audit_order]
        by_key: dict[tuple[str, str], dict[str, Any]] = {}
        dimensions: set[str] = set()
        for row in data.score_history:
            if str(row.get("device") or "").upper() != device.upper():
                continue
            if str(row.get("scoring_version") or "UNKNOWN") != version or str(row.get("url_universe") or "UNKNOWN") != universe:
                continue
            dimension = str(row.get("dimension") or "UNKNOWN")
            if dimension == "OVERALL_READINESS" or str(row.get("audit_id")) not in audit_ids:
                continue
            dimensions.add(dimension)
            by_key[(dimension, str(row.get("audit_id")))] = row
        header = "".join(f"<th>{escape(_date_label(event))}<small>{_audit_link(audit_id)}</small></th>" for audit_id, event in audit_order)
        body: list[str] = []
        for dimension in sorted(dimensions, key=_dimension):
            cells: list[str] = []
            for audit_id in audit_ids:
                row = by_key.get((dimension, audit_id))
                value = _number(row.get("value")) if row else None
                if value is None:
                    cells.append("<td class='heat na'>-</td>")
                else:
                    tone = _score_tone(value)
                    level = {"good": "high", "warn": "mid", "low": "low", "bad": "critical"}.get(tone, "na")
                    cells.append(f"<td class='heat {level}'>{_fmt(value)}</td>")
            body.append(f"<tr><th>{escape(_dimension(dimension))}</th>{''.join(cells)}</tr>")
        blocks.append(
            f"<article class='panel'><h3>{escape(_device(device))}</h3><div class='table-wrap matrix-wrap'><table class='matrix'><thead><tr><th>Dimensão</th>{header}</tr></thead><tbody>{''.join(body)}</tbody></table></div></article>"
        )
    if not blocks:
        return ""
    return "<section id='dimensions-history'><h2>Matriz histórica das dimensões</h2><p>Cada coluna é uma auditoria metodologicamente comparável. A cor é apenas auxílio visual; o valor numérico persistido prevalece.</p>" + "".join(blocks) + "</section>"


def _render_scores(data: ConsolidatedData) -> str:
    if not data.scores:
        return "<section id='scores'><h2>SARI e dimensões de Busca e IA</h2><p class='empty'>Nenhuma pontuação comparável persistida para o filtro.</p></section>"
    rows: list[str] = []
    advanced: list[str] = []
    notes: list[str] = []
    methods: set[str] = set()
    for item in data.scores:
        methods.update(item.scoring_versions)
        latest = _latest_score_row(data, item.device, item.dimension)
        value = _number(latest.get("value")) if latest else item.statistics.current
        coverage = _number(latest.get("coverage")) if latest else item.average_coverage
        confidence = _confidence(latest.get("confidence")) if latest else _human_counts(item.confidence_counts, _CONFIDENCE)
        status = _consolidation(latest.get("consolidation_status")) if latest else _human_counts(item.consolidation_counts, _CONSOLIDATION)
        method = str(latest.get("scoring_version") or ", ".join(item.scoring_versions)) if latest else ", ".join(item.scoring_versions)
        rows.append(
            "<tr>"
            f"<td>{escape(_device(item.device))}</td><td>{escape(_dimension(item.dimension))}</td>"
            f"<td>{_result_value_html(value, tone=_score_tone(value))}</td><td>{_pct(coverage)}</td><td>{_state_text_html(confidence)}</td>"
            f"<td>{_state_text_html(status)}</td><td>{item.statistics.count}</td><td>{escape(method)}</td></tr>"
        )
        advanced_row = _stats_advanced_rows(f"{_device(item.device)} · {_dimension(item.dimension)}", item.statistics, coverage=item.average_coverage)
        if advanced_row:
            advanced.append(advanced_row)
        if item.limitation:
            notes.append(f"<li><strong>{escape(_device(item.device))} / {escape(_dimension(item.dimension))}:</strong> {escape(item.limitation)}</li>")
    method_text = ", ".join(sorted(methods)) or "-"
    advanced_html = ""
    if advanced:
        advanced_html = f"""
        <details class='details'><summary>Exibir estatísticas históricas avançadas</summary>
          <p>Média, mediana, mínimo e máximo usam todas as observações elegíveis do grupo comparável. Nenhum extremo é removido automaticamente.</p>
          <div class='table-wrap'><table><thead><tr><th>Série</th><th>N</th><th>Inicial</th><th>Atual</th><th>Média</th><th>Mediana</th><th>Mínimo</th><th>Máximo</th><th>Variação abs.</th><th>Variação %</th><th>Cobertura média</th></tr></thead><tbody>{''.join(advanced)}</tbody></table></div>
        </details>"""
    else:
        advanced_html = "<p class='notice info'><strong>Snapshot:</strong> há somente um valor comparável por série; estatísticas redundantes de média/mediana/mínimo/máximo foram ocultadas.</p>"
    notes_html = f"<ul class='notes'>{''.join(notes)}</ul>" if notes else ""
    return f"""
    <section id='scores'><div class='section-title'><div><h2>SARI e dimensões de Busca e IA</h2><p>Ausência de dado não é convertida em zero. Valores atuais são apresentados primeiro; estatísticas históricas ficam sob demanda.</p></div><div class='method-badge'><small>Versão do método de pontuação</small><strong>{escape(method_text)}</strong></div></div>
    <div class='table-tools'><label>Filtrar dimensões <input type='search' data-table-filter='score-table' placeholder='Ex.: indexação, Mobile'></label></div>
    <div class='table-wrap bounded'><table id='score-table'><thead><tr><th>Dispositivo</th><th>Dimensão</th><th>Atual</th><th>Cobertura</th><th>Confiança</th><th>Estado</th><th>N</th><th>Versão do método</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    {advanced_html}{notes_html}</section>
    """


def _render_performance(data: ConsolidatedData) -> str:
    if not data.performance:
        return "<section id='performance'><h2>Desempenho Web</h2><p class='empty'>Nenhuma observação de Desempenho Web persistida para o filtro.</p></section>"
    blocks: list[str] = []
    for item in data.performance:
        rows: list[str] = []
        advanced: list[str] = []
        for metric in item.metrics:
            tone = _performance_tone(metric.name, metric.statistics.current)
            current = (
                _result_value_html(metric.statistics.current, tone=tone)
                if tone != "neutral"
                else escape(_fmt(metric.statistics.current))
            )
            rows.append(
                f"<tr><td>{escape(metric.name)}</td><td>{escape(metric.unit)}</td><td>{current}</td><td>{metric.statistics.count}</td></tr>"
            )
            detail = _stats_advanced_rows(metric.name, metric.statistics)
            if detail:
                advanced.append(detail)
        advanced_html = ""
        if advanced:
            advanced_html = f"<details class='details'><summary>Exibir estatísticas históricas de desempenho</summary><div class='table-wrap'><table><thead><tr><th>Métrica</th><th>N</th><th>Inicial</th><th>Atual</th><th>Média</th><th>Mediana</th><th>Mínimo</th><th>Máximo</th><th>Variação abs.</th><th>Variação %</th><th>Cobertura</th></tr></thead><tbody>{''.join(advanced)}</tbody></table></div></details>"
        else:
            advanced_html = "<p class='subtle'>Snapshot: não há série temporal suficiente para estatísticas históricas desta seção.</p>"
        blocks.append(f"""
        <article class='panel'><h3>{escape(_device(item.device))}</h3>
        <div class='metric-grid'><div><small>Observações</small><strong>{item.observations}</strong></div><div><small>URLs</small><strong>{item.urls}</strong></div><div><small>Core Web Vitals</small><div class='chips'>{_human_counts(item.cwv_counts)}</div></div><div><small>Fonte / escopo de campo</small><div class='chips'>{_human_counts(item.source_scopes)}</div></div></div>
        <div class='table-wrap'><table><thead><tr><th>Métrica</th><th>Unidade</th><th>Atual</th><th>N</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>{advanced_html}</article>
        """)
    return "<section id='performance'><h2>Desempenho Web</h2><p>Métricas de laboratório e dados de campo permanecem identificados separadamente; não são tratados como equivalentes.</p>" + "".join(blocks) + "</section>"


def _render_apdex(data: ConsolidatedData) -> str:
    if not data.apdex:
        return "<section id='apdex'><h2>Apdex sintético</h2><p class='empty'>Nenhum resumo de Apdex sintético persistido para o filtro.</p></section>"
    blocks: list[str] = []
    for item in data.apdex:
        metric_rows: list[str] = []
        advanced: list[str] = []
        for metric in item.duration_metrics:
            metric_rows.append(f"<tr><td>{escape(metric.name)}</td><td>{escape(metric.unit)}</td><td>{_fmt(metric.statistics.current)}</td><td>{metric.statistics.count}</td></tr>")
            detail = _stats_advanced_rows(metric.name, metric.statistics)
            if detail:
                advanced.append(detail)
        notices: list[str] = []
        if item.small_groups and not item.final_groups:
            notices.append(
                f"<p class='notice warning'><strong>Amostra pequena:</strong> o Apdex {_fmt(item.weighted_apdex, 3)} foi calculado com {item.valid_samples} amostras válidas, mas nenhum grupo foi classificado como final. Use como diagnóstico, não como conclusão robusta.</p>"
            )
        if item.limitation:
            notices.append(f"<p class='notice warning'>{escape(item.limitation)}</p>")
        advanced_html = ""
        if advanced:
            advanced_html = f"<details class='details'><summary>Exibir estatísticas históricas do Apdex</summary><div class='table-wrap'><table><thead><tr><th>Métrica</th><th>N</th><th>Inicial</th><th>Atual</th><th>Média</th><th>Mediana</th><th>Mínimo</th><th>Máximo</th><th>Variação abs.</th><th>Variação %</th><th>Cobertura</th></tr></thead><tbody>{''.join(advanced)}</tbody></table></div></details>"
        blocks.append(f"""
        <article class='panel'><h3>{escape(_device(item.device))}</h3>
        <div class='metric-grid'><div><small>Apdex ponderado por amostra válida</small>{_result_value_html(item.weighted_apdex, tone=_apdex_tone(item.weighted_apdex), digits=3)}</div><div><small>Amostras válidas</small><strong>{item.valid_samples}</strong></div><div><small>Amostras inválidas</small><strong>{item.invalid_samples}</strong></div><div><small>URLs</small><strong>{item.urls}</strong></div><div><small>Perfil sintético</small><strong>{escape(', '.join(item.profile_ids))}</strong></div><div><small>T (limiar)</small><strong>{escape(', '.join(_fmt(value, 3) + ' s' for value in item.thresholds))}</strong></div><div><small>Grupos com amostra pequena</small><strong>{item.small_groups}</strong></div><div><small>Grupos finais</small><strong>{item.final_groups}</strong></div></div>
        {''.join(notices)}
        <div class='table-wrap'><table><thead><tr><th>Métrica</th><th>Unidade</th><th>Atual</th><th>N</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div>{advanced_html}</article>
        """)
    return "<section id='apdex'><h2>Apdex sintético</h2><p>A agregação ocorre somente entre perfil e T compatíveis. O Apdex consolidado é ponderado pelo número de amostras válidas.</p>" + "".join(blocks) + "</section>"


def _finding_trend_rows(data: ConsolidatedData) -> list[dict[str, Any]]:
    audits = {str(row.get("audit_id")): row for row in data.audits}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data.finding_history:
        grouped[str(row.get("audit_id"))].append(row)
    output: list[dict[str, Any]] = []
    for audit_id, rows in grouped.items():
        audit = audits.get(audit_id, {})
        output.append({
            "audit_id": audit_id,
            "event_time": audit.get("event_time") or rows[0].get("event_time"),
            "value": len(rows),
            "url_count": int(audit.get("url_count") or 0),
            "affected": len({str(row.get("page_id")) for row in rows if row.get("page_id")}),
            "per_url": (len(rows) / int(audit.get("url_count") or 0)) if int(audit.get("url_count") or 0) > 0 else None,
        })
    output.sort(key=lambda row: str(row.get("event_time") or ""))
    return output


def _render_findings(data: ConsolidatedData) -> str:
    finding = data.findings
    trend = _finding_trend_rows(data)
    chart = _svg_line_chart(
        title="Evolução de ocorrências por URL auditada",
        rows=trend,
        primary_field="per_url",
        primary_label="Ocorrências por URL",
    ) if len(trend) >= 2 else ""
    caution = "<p class='subtle'>A série usa ocorrências por URL auditada para reduzir o viés de mudança de escopo. O volume bruto continua disponível como contexto e não deve ser comparado isoladamente entre auditorias com universos diferentes.</p>" if trend else ""
    return f"""
    <section id='findings'><h2>Ocorrências persistidas</h2>
    <p>As contagens descrevem o histórico observado e não recalculam o SARI.</p>
    <div class='metric-grid findings-metric-grid'><div><small>Ocorrências</small><strong>{finding.observations}</strong></div><div><small>Páginas afetadas</small><strong>{finding.affected_pages}</strong></div><div><small>Severidades</small><div class='chips'>{_human_counts(finding.severity_counts, _SEVERITY)}</div></div><div><small>Categorias</small><div class='chips'>{_human_counts(finding.category_counts, _FINDING_CATEGORY)}</div></div></div>
    {chart}{caution}</section>
    """


def _render_reliability(data: ConsolidatedData) -> str:
    methods = sorted({str(row.get("scoring_version") or "UNKNOWN") for row in data.score_history})
    rulesets = sorted({str(row.get("ruleset_version") or "UNKNOWN") for row in data.audits})
    comparable = len(methods) <= 1 and len(rulesets) <= 1
    mode, mode_note = _historical_mode(data)
    confidence_items: list[str] = []
    for device in sorted({str(row.get("device") or "") for row in data.score_history if row.get("device")}):
        latest = _latest_score_row(data, device, "OVERALL_READINESS")
        if latest:
            confidence_items.append(f"{_device(device)}: {_confidence(latest.get('confidence'))} ({_pct(_number(latest.get('coverage')))})")
    apdex_text = "Não coletado"
    if data.apdex:
        if any(item.final_groups > 0 for item in data.apdex):
            apdex_text = "Há grupo(s) final(is) persistido(s); verificar perfil, T e número de amostras."
        else:
            apdex_text = "Limitado: somente grupo(s) com amostra pequena no universo selecionado."
    return f"""
    <section id='reliability'><h2>Confiabilidade analítica do consolidado</h2>
    <p>Esta matriz não é um novo score. Ela separa fidelidade da fonte, comparabilidade e suficiência da base para evitar falsa precisão.</p>
    <div class='reliability-grid'>
      <div><small>Fidelidade às fontes</small><strong>Alta</strong><p>Dados lidos dos SQLite persistidos em modo somente leitura; a consolidação não reexecuta APIs nem o motor de pontuação.</p></div>
      <div><small>Comparabilidade metodológica</small><strong>{'Alta' if comparable else 'Limitada'}</strong><p>{escape('Uma única versão de método/regras no universo selecionado.' if comparable else 'Há mais de uma versão de método ou conjunto de regras; séries incompatíveis são segmentadas/excluídas da agregação.')}</p></div>
      <div><small>Base histórica</small><strong>{escape(mode)}</strong><p>{escape(mode_note)}</p></div>
      <div><small>Confiança do SARI</small><strong>{escape(' · '.join(confidence_items) or 'Indisponível')}</strong><p>É a confiança persistida pelo RASAi; representa força/cobertura da conclusão, não qualidade do website.</p></div>
      <div><small>Robustez do Apdex</small><strong>{escape(apdex_text)}</strong><p>Apdex só é agregado entre perfil e T compatíveis.</p></div>
      <div><small>Validação externa do SCORE-GEO</small><strong>Não estabelecida como preditor</strong><p>O método é interno e reproduzível, mas não é uma métrica oficial de Google/OpenAI nem prova ranking, tráfego ou citação por sistemas generativos.</p></div>
    </div></section>
    """


def _render_methodology(data: ConsolidatedData) -> str:
    methods = sorted({str(row.get("scoring_version") or "UNKNOWN") for row in data.score_history})
    method_value = ", ".join(methods) or "Não disponível"
    limitations = "".join(f"<li>{escape(item)}</li>" for item in data.limitations) or "<li>Nenhuma limitação adicional registrada pelo consolidador.</li>"
    current_method = "SCORE-GEO-004" in methods
    prior_development_methods = [method for method in methods if method not in {"SCORE-GEO-004", "UNKNOWN"}]
    if current_method:
        score_explanation = """
        <h3>Como o SCORE-GEO-004 é interpretado</h3>
        <ol>
          <li>Regras aplicáveis produzem resultados persistidos e fatores versionados; ausência de evidência não é convertida silenciosamente em falha.</li>
          <li>A pontuação de cada dimensão usa <code>soma(peso × fator) / soma dos pesos efetivamente avaliados × 100</code>.</li>
          <li>Cobertura mede a fração aplicável efetivamente avaliada; Confiança qualifica a força/completude da medição.</li>
          <li>Dimensão legitimamente não aplicável sai do denominador. Dimensão aplicável sem medição suficiente pode bloquear a consolidação do Overall.</li>
          <li>O Overall usa igual peso entre dimensões aplicáveis com medição suficiente e não incorpora Lighthouse, Core Web Vitals, Acessibilidade ou Apdex.</li>
        </ol>
        """
        if prior_development_methods:
            score_explanation += (
                "<p class='notice warning'><strong>Dados de desenvolvimento não comparáveis:</strong> o universo selecionado também contém "
                + escape(", ".join(prior_development_methods))
                + ". Esses contratos anteriores de desenvolvimento são preservados por rastreabilidade e não são tratados como série equivalente ao SCORE-GEO-004.</p>"
            )
    else:
        score_explanation = (
            f"<p>Versão(ões) persistida(s) encontrada(s): <strong>{escape(method_value)}</strong>. "
            "O consolidado preserva esses dados de desenvolvimento sem recalcular e sem presumir equivalência com o contrato vigente SCORE-GEO-004.</p>"
        )
    return f"""
    <section id='method'><h2>Metodologia, cálculos e base técnica</h2>
    <div class='method-grid'>
      <div><small>Fonte de verdade</small><strong>AUD-*/audit.db</strong><p>O índice <code>.rasai/consolidated-index.db</code> é cache derivado e reconstruível.</p></div>
      <div><small>Versão do método de pontuação</small><strong>{escape(method_value)}</strong><p>É a versão que efetivamente produziu os valores persistidos; não é uma métrica concorrente ou opção de mercado.</p></div>
      <div><small>Chamadas externas</small><strong>Somente IA para interpretação longitudinal</strong><p>O consolidado não recoleta a URL e não chama PageSpeed, CrUX ou outras fontes de aquisição. A IA recebe somente evidências já persistidas e não altera cálculos determinísticos.</p></div>
      <div><small>Política de extremos</small><strong>Sem descarte automático</strong><p>Nenhuma observação é removida apenas por ser mínima, máxima ou distante da média.</p></div>
    </div>
    {score_explanation}
    <h3>Estatística histórica</h3>
    <ul>
      <li><strong>Média:</strong> média aritmética das observações elegíveis e metodologicamente comparáveis.</li>
      <li><strong>Mediana:</strong> valor central das observações elegíveis; preserva a leitura mesmo quando há extremos.</li>
      <li><strong>Mínimo/Máximo:</strong> extremos observados são preservados, não aparados.</li>
      <li><strong>Estado inicial/atual em métricas por URL:</strong> usa o valor válido mais antigo/mais recente de cada URL e depois calcula a média transversal, evitando que uma URL auditada mais vezes represente sozinha o domínio.</li>
      <li><strong>Pontuação histórica:</strong> só agrega mesma versão do método e mesmo universo de URLs comparável. Filtro parcial de URL não reutiliza pontuação calculada sobre páginas excluídas.</li>
      <li><strong>Apdex:</strong> somente perfil e T compatíveis; o índice consolidado é ponderado pelo número de amostras válidas.</li>
      <li><strong>Dados ausentes:</strong> nunca são convertidos em zero.</li>
      <li><strong>Interpolação:</strong> não existe; gráficos usam somente observações realmente persistidas.</li>
    </ul>
    <h3>Base técnica e interpretação</h3>
    <p>O SCORE-GEO é um método interno de readiness do RASAi. Sua aritmética é determinística e rastreável, mas sua validade externa como preditor de ranking/citação não está estabelecida. Lighthouse/Core Web Vitals e Apdex mantêm suas metodologias próprias e não são incorporados silenciosamente ao SCORE-GEO.</p>
    <ul class='references'>
      <li><strong>Especificação interna:</strong> <code>docs/specification/19_SCORE_APPLICABILITY_READINESS_MINIMUMS.md</code>.</li>
      <li><strong>Google Search:</strong> <a href='https://developers.google.com/search/docs/fundamentals/ai-optimization-guide'>Optimizing your website for generative AI features on Google Search</a>.</li>
      <li><strong>Métricas Core Web Vitals:</strong> <a href='https://web.dev/articles/vitals'>Web Vitals</a>.</li>
      <li><strong>Apdex:</strong> <a href='https://www.apdex.org/'>Apdex Alliance</a>.</li>
    </ul>
    <h3>Limitações detectadas nesta consolidação</h3><ul>{limitations}</ul>
    </section>
    """


def _render_audits(data: ConsolidatedData) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{_audit_link(row.get('audit_id'))}</td>"
        f"<td>{escape(_date_label(row.get('event_time')))}</td>"
        f"<td>{escape(str(row.get('project_name') or ''))}</td>"
        f"<td>{escape(str(row.get('auditor_version') or ''))}</td>"
        f"<td>{escape(str(row.get('ruleset_version') or ''))}</td>"
        f"<td>{escape(', '.join(_device(item) for item in json.loads(row.get('devices_json') or '[]')) if str(row.get('devices_json') or '').startswith('[') else _device(row.get('devices_json')))}</td>"
        f"<td>{int(row.get('url_count') or 0)}</td></tr>"
        for row in data.audits
    )
    return f"""
    <section id='sources'><h2>Auditorias consideradas</h2>
    <p>Esta lista define a proveniência do consolidado. Use pesquisa e paginação para grandes históricos.</p>
    <div class='table-tools audit-tools'><label>Pesquisar <input id='audit-search' type='search' placeholder='ID, projeto, versão...'></label><label>Linhas por página <select id='audit-page-size'><option>25</option><option>50</option><option>100</option></select></label><span id='audit-page-status' class='subtle'></span></div>
    <div class='table-wrap bounded audits-wrap'><table id='audit-table'><thead><tr><th>ID da auditoria</th><th>Data efetiva</th><th>Projeto</th><th>Versão do auditor</th><th>Versão das regras</th><th>Dispositivos</th><th>URLs</th></tr></thead><tbody>{rows}</tbody></table></div>
    <div class='pager'><button type='button' id='audit-prev'>Anterior</button><button type='button' id='audit-next'>Próxima</button></div></section>
    """


def _render_html(data: ConsolidatedData, generated_at: str, request_fingerprint: str) -> str:
    filters = data.filters.canonical()
    mode, _ = _historical_mode(data)
    return f"""<!doctype html>
<html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>RASAi - Relatório Consolidado</title>
<style>
:root{{--bg:#f6f8fb;--surface:#fff;--ink:#172033;--secondary-ink:#475467;--muted:#667085;--light-muted:#6c7789;--line:#e2e7ef;--blue:#3157c8;--blue2:#91a5ce;--green:#187a45;--green-soft:#edf8f0;--amber:#9a6200;--amber-soft:#fff8e9;--orange:#9a5b13;--red:#b42318;--cyan:#087a8c;--red-soft:#fff1f0;--soft:#f2f6ff;--nav:#111827;--radius:14px;--shadow:0 1px 3px rgba(16,24,40,.06)}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}a{{color:var(--blue)}}header{{background:var(--nav);color:white;padding:22px 28px}}header h1{{margin:0;font-size:1.6rem;line-height:1.2}}header p{{margin:.35rem 0 0;color:#cbd5e1;max-width:1000px}}nav{{position:sticky;top:0;z-index:20;background:rgba(246,248,251,.96);backdrop-filter:blur(7px);border-bottom:1px solid var(--line);padding:8px max(18px,calc((100% - 1500px)/2 + 18px));display:flex;gap:6px;overflow:auto}}nav a{{white-space:nowrap;text-decoration:none;border:1px solid var(--line);background:#fff;border-radius:999px;padding:5px 9px;font-size:.74rem;color:#46536a}}nav a:hover,nav a:focus{{background:#f2f6ff;border-color:#bdc8da;color:#274690}}main{{margin:auto;padding:26px}}section,.panel,.chart-card{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin:0 0 16px;box-shadow:var(--shadow)}}.panel,.chart-card{{margin-top:14px}}h2{{margin:0 0 8px;font-size:1.25rem}}h3{{margin:16px 0 8px}}p{{margin:.4rem 0 1rem}}.subtle,.empty{{color:var(--muted)}}.metric-grid,.reliability-grid,.method-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.metric-grid>div,.reliability-grid>div,.method-grid>div{{background:#fbfcfe;border:1px solid var(--line);border-radius:10px;padding:11px}}.metric-grid>div{{display:flex;flex-direction:column;min-height:96px;gap:5px}}.metric-grid>div>small:first-child{{font-size:.76rem;font-weight:600;line-height:1.25;letter-spacing:.01em;margin:0 0 8px;color:var(--muted)}}.metric-grid>div>strong{{display:block;margin-top:auto;font-size:1rem;font-weight:700;line-height:1.2;color:var(--ink);font-variant-numeric:tabular-nums}}.reliability-grid>div p,.method-grid>div p{{font-size:.92rem;color:var(--muted);margin:.35rem 0 0}}small{{display:block;color:var(--muted);margin-bottom:5px}}strong{{overflow-wrap:anywhere}}.section-title{{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}}.method-badge{{min-width:220px;background:var(--soft);border-radius:7px;padding:10px 12px}}.table-wrap{{overflow:auto;margin-top:12px;border:1px solid var(--line);border-radius:10px;background:#fff}}.bounded{{max-height:570px}}table{{border-collapse:collapse;width:100%;min-width:760px;font-size:.83rem}}th,td{{padding:9px 10px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top}}td{{color:var(--ink)}}thead th{{background:#f8fafc;color:#4b5565;position:sticky;top:0;z-index:2;text-transform:uppercase;letter-spacing:.03em;font-size:.69rem}}tbody tr:hover{{background:#fbfcfe}}.table-tools{{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin:12px 0 4px}}.table-tools label{{font-size:.9rem;color:var(--muted)}}input,select,button{{font:inherit;border:1px solid var(--line);border-radius:6px;padding:7px 9px;background:white;color:var(--ink)}}input[type=search]{{min-width:240px}}button{{cursor:pointer}}button:disabled{{opacity:.45;cursor:default}}.pager{{display:flex;justify-content:flex-end;gap:8px;margin-top:10px}}.notice{{border:1px solid #cbd8f5;background:#f2f6ff;border-radius:10px;padding:11px 13px}}.notice.info{{background:#f2f6ff;border-color:#cbd8f5}}.notice.warning{{background:var(--amber-soft);border-color:#ecd09d}}.notice.bad{{background:var(--red-soft);border-color:#efb7b2}}.notice.good{{background:var(--green-soft);border-color:#b9dec5}}.notice.warning>strong{{color:var(--amber)}}.notice.bad>strong{{color:var(--red)}}.notice.good>strong{{color:var(--green)}}.notes{{padding-left:20px}}.decision-list{{padding-left:20px}}.decision-list li{{margin:.45rem 0}}.chips{{display:flex;gap:9px;flex-wrap:wrap}}.chip{{display:inline-flex;gap:4px;align-items:center;background:transparent;border-radius:0;padding:0;font-size:.83rem;color:var(--secondary-ink)}}.state-count.good strong{{color:var(--green)}}.state-count.warn strong{{color:var(--amber)}}.state-count.bad strong{{color:var(--red)}}.state-count.neutral strong{{color:var(--secondary-ink);font-weight:600}}.details,main details{{margin:14px 0;border:1px solid var(--line);border-radius:9px;background:#fbfcfd;overflow:hidden;padding:0}}main details>summary{{cursor:pointer;font-weight:650;padding:9px 11px;background:#fbfcfd;list-style:none;display:flex;align-items:center;gap:8px;text-align:left}}main details>summary::-webkit-details-marker{{display:none}}main details>summary::before{{content:'›';display:inline-block;font-size:1.25rem;line-height:1;transition:transform .15s ease}}main details[open]>summary::before{{transform:rotate(90deg)}}main details[open]>summary{{border-bottom:1px solid var(--line)}}main details>summary~*{{margin-left:12px;margin-right:12px}}main details>.table-wrap{{margin-bottom:12px}}.audit-link{{font-weight:700;text-decoration:none;text-underline-offset:2px}}.audit-link:hover{{text-decoration:underline}}code{{word-break:break-all;background:#f3f5f8;padding:1px 4px;border-radius:4px}}.chart-card{{padding:14px 16px}}.chart-heading{{display:flex;justify-content:space-between;align-items:flex-start;gap:14px}}.chart-heading h3{{margin:0}}.chart-heading p{{color:var(--muted);margin:.25rem 0 0}}.chart-scroll{{overflow:auto}}svg{{width:100%;min-width:720px;height:auto}}.grid-line{{stroke:#e2e7ef;stroke-width:1}}.axis-label{{fill:#718096;font-size:11px}}.trend-line{{fill:none;stroke-width:2.5}}.primary-line{{stroke:var(--blue)}}.secondary-line{{stroke:var(--green)}}.dot{{stroke:white;stroke-width:1.5}}.primary-dot{{fill:var(--blue)}}.secondary-dot{{fill:var(--green)}}.legend-row{{display:flex;gap:12px;flex-wrap:wrap}}.legend:before{{content:'';display:inline-block;width:18px;height:3px;border-radius:2px;margin-right:5px;vertical-align:middle}}.primary-legend:before{{background:var(--blue)}}.secondary-legend:before{{background:var(--green)}}.matrix th small{{font-weight:400;margin-top:2px}}.heat{{text-align:center;font-variant-numeric:tabular-nums;background:transparent}}.heat.high{{color:var(--green);font-weight:700}}.heat.mid{{color:var(--amber);font-weight:700}}.heat.low{{color:var(--orange);font-weight:700}}.heat.critical{{color:var(--red);font-weight:700}}.heat.na{{color:var(--secondary-ink);font-weight:400;background:transparent}}.metric.signal-positive,.metric.signal-warning,.metric.signal-negative{{background:#fbfcfe!important;border:1px solid var(--line)!important}}.metric.signal-positive>strong{{color:var(--green)}}.metric.signal-warning>strong{{color:var(--amber)}}.metric.signal-negative>strong{{color:var(--red)}}.state-text.good{{color:var(--green)}}.state-text.warn{{color:var(--amber)}}.state-text.bad{{color:var(--red)}}.state-text.neutral{{color:var(--secondary-ink);font-weight:400}}.result-value{{font-weight:700;color:var(--ink)}}.result-value.good{{color:var(--green)}}.result-value.warn{{color:var(--amber)}}.result-value.low{{color:var(--orange)}}.result-value.bad{{color:var(--red)}}.result-value.neutral{{color:var(--ink)}}.no-cost-value{{color:var(--light-muted);font-weight:400}}.result-tag{{display:inline;font-size:inherit;font-weight:700;background:transparent;padding:0;border-radius:0}}.result-tag.good{{color:var(--green)}}.result-tag.warn{{color:var(--amber)}}.result-tag.bad{{color:var(--red)}}tr.result-state-warn,tr.result-state-bad{{background:transparent}}tr.result-state-good>td:first-child,tr.result-state-warn>td:first-child,tr.result-state-bad>td:first-child{{box-shadow:none}}.references li{{margin:.35rem 0}}footer{{color:var(--muted);padding:0 4px 30px;font-size:.74rem}}@media(max-width:760px){{main{{padding:16px}}header{{padding:18px}}.section-title,.chart-heading{{display:block}}.method-badge{{margin-top:10px}}input[type=search]{{min-width:180px;width:100%}}}}
</style></head><body>
<header><h1>RASAi - Relatório Consolidado</h1><p>Relatório longitudinal estático baseado em indicadores e evidências persistidas · {escape(mode)}</p></header>
<nav aria-label='Navegação do relatório'><a href='#summary'>Resumo</a><a href='#scores'>SARI</a><a href='#evolution'>Evolução</a><a href='#performance'>Desempenho</a><a href='#apdex'>Apdex</a><a href='#findings'>Ocorrências</a><a href='#reliability'>Confiabilidade</a><a href='#sources'>Auditorias</a><a href='#method'>Metodologia</a></nav>
<main>
<section id='scope'><h2>Escopo observado</h2><div class='metric-grid'>
<div><small>Auditorias consideradas</small><strong>{len(data.audits)}</strong></div><div><small>URLs únicas</small><strong>{data.unique_urls}</strong></div>
<div><small>Primeira observação real</small><strong>{escape(_date_label(data.date_min))}</strong></div><div><small>Última observação real</small><strong>{escape(_date_label(data.date_max))}</strong></div>
<div><small>Domínios</small><strong>{escape(', '.join(filters['domains']) or 'todos')}</strong></div><div><small>Dispositivos</small><strong>{escape(', '.join(_device(value) for value in filters['devices']) or 'todos')}</strong></div>
<div><small>Período solicitado</small><strong>{escape(str(filters['date_from'] or 'início'))} → {escape(str(filters['date_to'] or 'fim'))}</strong></div><div><small>URLs filtradas explicitamente</small><strong>{len(filters['urls']) if filters['urls'] else 'todas as elegíveis'}</strong></div>
</div></section>
{_render_executive(data)}
{_render_scores(data)}
{_render_score_trends(data)}
{_render_dimension_matrix(data)}
{_render_performance(data)}
{_render_apdex(data)}
{_render_findings(data)}
{_render_reliability(data)}
{_render_audits(data)}
{_render_methodology(data)}
<footer>Gerado em {escape(generated_at)} · formato {REPORT_FORMAT_VERSION} · fingerprint {escape(request_fingerprint)}</footer>
</main>
<script>
(function(){{
  function normalize(value){{return (value||'').toLocaleLowerCase('pt-BR');}}
  document.querySelectorAll('[data-table-filter]').forEach(function(input){{
    var table=document.getElementById(input.dataset.tableFilter); if(!table)return;
    input.addEventListener('input',function(){{var q=normalize(input.value); table.querySelectorAll('tbody tr').forEach(function(row){{row.hidden=q && !normalize(row.textContent).includes(q);}});}});
  }});
  var table=document.getElementById('audit-table'), search=document.getElementById('audit-search'), size=document.getElementById('audit-page-size'), prev=document.getElementById('audit-prev'), next=document.getElementById('audit-next'), status=document.getElementById('audit-page-status');
  if(table&&search&&size&&prev&&next&&status){{
    var page=0;
    function refresh(){{
      var q=normalize(search.value), per=parseInt(size.value,10)||25;
      var rows=Array.from(table.querySelectorAll('tbody tr'));
      var eligible=rows.filter(function(row){{return !q||normalize(row.textContent).includes(q);}});
      var pages=Math.max(1,Math.ceil(eligible.length/per)); if(page>=pages)page=pages-1; if(page<0)page=0;
      rows.forEach(function(row){{row.hidden=true;}}); eligible.slice(page*per,page*per+per).forEach(function(row){{row.hidden=false;}});
      status.textContent=eligible.length+' auditoria(s) · página '+(page+1)+' de '+pages;
      prev.disabled=page<=0; next.disabled=page>=pages-1;
    }}
    search.addEventListener('input',function(){{page=0;refresh();}}); size.addEventListener('change',function(){{page=0;refresh();}}); prev.addEventListener('click',function(){{page--;refresh();}}); next.addEventListener('click',function(){{page++;refresh();}}); refresh();
  }}
}})();
</script></body></html>"""


def write_report(*, audits_root: Path, data: ConsolidatedData, refresh: RefreshResult) -> GenerationResult:
    fingerprint = _request_fingerprint(data)
    existing = _find_existing(audits_root, fingerprint)
    if existing is not None:
        report_path, manifest_path = existing
        return GenerationResult(
            report_dir=report_path.parent,
            report_path=report_path,
            manifest_path=manifest_path,
            reused=True,
            request_fingerprint=fingerprint,
            refresh=refresh,
        )

    now = datetime.now().astimezone()
    cons_id = now.strftime("CONS-%Y%m%d-%H%M%S-%f")[:-3]
    output = audits_root / "consolidated" / cons_id
    output.mkdir(parents=True, exist_ok=False)
    generated_at = now.isoformat()
    report_path = output / "report.html"
    manifest_path = output / "manifest.json"
    methods = sorted({str(row.get("scoring_version") or "UNKNOWN") for row in data.score_history})
    mode, mode_note = _historical_mode(data)
    manifest = {
        "cons_id": cons_id,
        "report_format_version": REPORT_FORMAT_VERSION,
        "generated_at": generated_at,
        "request_fingerprint": fingerprint,
        "source_fingerprint": data.source_fingerprint,
        "filters": data.filters.canonical(),
        "summary": {
            "audits": len(data.audits),
            "unique_urls": data.unique_urls,
            "date_min": data.date_min,
            "date_max": data.date_max,
            "historical_mode": mode,
            "historical_mode_note": mode_note,
            "scoring_versions": methods,
        },
        "aggregation_policy": {
            "missing_data": "never_zero",
            "outliers": "no_automatic_removal",
            "score": "same_scoring_version_and_url_universe",
            "performance_current_initial": "mean_of_latest_earliest_valid_value_per_url",
            "apdex": "same_profile_and_threshold_weighted_by_valid_samples",
            "interpolation": "none",
        },
        "source_audits": [
            {
                "audit_id": row.get("audit_id"),
                "db_path": row.get("db_path"),
                "source_fingerprint": row.get("source_fingerprint"),
                "event_time": row.get("event_time"),
                "auditor_version": row.get("auditor_version"),
                "ruleset_version": row.get("ruleset_version"),
                "url_count": row.get("url_count"),
            }
            for row in data.audits
        ],
        "limitations": list(data.limitations),
        "refresh": {
            "discovered": refresh.discovered,
            "indexed": refresh.indexed,
            "reused": refresh.reused,
            "removed": refresh.removed,
            "issues": [asdict(item) for item in refresh.issues],
        },
    }
    rendered = _render_html(data, generated_at, fingerprint)
    rendered = enhance_report_html(rendered, page_name="consolidated.html", report_dir=output)
    rendered = humanize_report_html(rendered, page_name="consolidated.html")
    report_path.write_text(rendered, encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return GenerationResult(
        report_dir=output,
        report_path=report_path,
        manifest_path=manifest_path,
        reused=False,
        request_fingerprint=fingerprint,
        refresh=refresh,
    )
