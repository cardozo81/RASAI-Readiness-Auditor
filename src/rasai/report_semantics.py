"""Semantic presentation layer for generated RASAi HTML reports.

This module does not change persisted findings, scores, Lighthouse/CrUX data or
Apdex calculations. It only reconciles final HTML with persisted evidence and
adds domain-specific visual states so that important results are not presented
as visually equivalent to neutral telemetry.
"""
from __future__ import annotations

from html import escape, unescape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.indicator_provenance import enrich_indicator_provenance_html


SEMANTIC_CSS = r"""
/* rasai-result-semantics-v1 */
.metric.result-state-good,.metric.result-state-warn,.metric.result-state-bad,.metric.result-state-neutral{position:relative;overflow:hidden;border-left:4px solid transparent}
.metric.result-state-good{background:var(--soft-green);border-left-color:var(--green)}
.metric.result-state-warn{background:var(--soft-amber);border-left-color:var(--amber)}
.metric.result-state-bad{background:var(--soft-red);border-left-color:var(--red)}
.metric.result-state-neutral{background:var(--soft-blue);border-left-color:var(--blue)}
.metric.metric-primary{min-height:82px;padding:13px 14px}.metric.metric-primary strong{font-size:1.08rem;line-height:1.25}
.result-tag{display:inline-flex;align-items:center;width:max-content;max-width:100%;margin-top:6px;padding:2px 7px;border-radius:999px;font-size:.68rem;line-height:1.35;font-weight:720;letter-spacing:.015em;text-transform:uppercase}
.result-tag.good{background:rgba(95,150,116,.14);color:#3f7452}.result-tag.warn{background:rgba(182,138,80,.15);color:#855f2c}.result-tag.bad{background:rgba(191,111,112,.14);color:#98494c}.result-tag.neutral{background:rgba(101,127,198,.13);color:#4d65a0}
tr.result-state-good>td:first-child{box-shadow:inset 3px 0 0 var(--green)}tr.result-state-warn>td:first-child{box-shadow:inset 3px 0 0 var(--amber)}tr.result-state-bad>td:first-child{box-shadow:inset 3px 0 0 var(--red)}tr.result-state-neutral>td:first-child{box-shadow:inset 3px 0 0 var(--blue)}
tr.result-state-warn{background:var(--soft-amber)}tr.result-state-bad{background:var(--soft-red)}tr.result-state-neutral{background:var(--soft-blue)}
.semantic-legend{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 2px;color:var(--muted);font-size:.76rem}.semantic-legend .result-tag{margin:0}
.result-cell{font-weight:650}.result-cell .result-tag{margin-top:0}.result-cell.good{background:rgba(95,150,116,.08)}.result-cell.warn{background:rgba(182,138,80,.10)}.result-cell.bad{background:rgba(191,111,112,.10)}
.priority-tag{display:inline-flex;align-items:center;margin-left:7px;padding:2px 7px;border-radius:999px;font-size:.66rem;font-weight:720;letter-spacing:.015em;text-transform:uppercase;vertical-align:middle}.priority-tag.high{background:var(--soft-red);color:#98494c}.priority-tag.medium{background:var(--soft-amber);color:#855f2c}.priority-tag.review{background:var(--soft-blue);color:#4d65a0}
details.priority-high{border-left:4px solid var(--red);background:var(--soft-red)}details.priority-medium{border-left:4px solid var(--amber);background:var(--soft-amber)}
.score-confidence-note{margin-top:12px}.score-confidence-note ul{margin:.5rem 0 0;padding-left:1.15rem}.score-confidence-note li+li{margin-top:.22rem}
.apdex-threshold-note{margin-top:12px}.apdex-threshold-note code{font-weight:650}.apdex-card.apdex-conflict{box-shadow:0 7px 20px rgba(182,138,80,.08),inset 3px 0 0 rgba(182,138,80,.72)}
.indicator-tier-label{margin:.85rem 0 .45rem;color:var(--muted);font-size:.72rem;font-weight:760;text-transform:uppercase;letter-spacing:.07em}.indicator-tier-supporting{margin-top:1.1rem}.indicator-primary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(360px,100%),1fr));gap:12px;align-items:stretch}.indicator-grid{grid-template-columns:repeat(4,minmax(0,1fr));align-items:stretch}.indicator-card{display:flex;flex-direction:column;min-width:0}.indicator-card.indicator-primary{min-height:0}.indicator-card h3{font-size:1rem;line-height:1.25;min-height:2.5em}.indicator-primary h3{min-height:auto}.indicator-card .intro{font-size:.88rem;max-width:100%}.indicator-score{font-size:clamp(1.5rem,2vw,1.9rem)!important;line-height:1.06;overflow-wrap:normal;word-break:normal;white-space:nowrap}.indicator-values{display:flex;gap:12px;flex-wrap:wrap;margin:.45rem 0}.indicator-device{display:flex;flex-direction:column;gap:2px;min-width:92px}.indicator-device small{color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.04em}.indicator-device strong{font-size:clamp(1.5rem,2vw,1.9rem);line-height:1.06;white-space:nowrap}.indicator-condition{display:inline-flex;width:max-content;max-width:100%;margin:.35rem 0 .2rem;padding:3px 8px;border-radius:999px;font-size:.7rem;font-weight:760;line-height:1.35}.indicator-card.condition-expected{border-top:4px solid var(--green);background:var(--soft-green)}.indicator-card.condition-near{border-top:4px solid var(--amber);background:var(--soft-amber)}.indicator-card.condition-below{border-top:4px solid #a96f38;background:rgba(169,111,56,.08)}.indicator-card.condition-critical{border-top:4px solid var(--red);background:var(--soft-red)}.indicator-card.condition-neutral{border-top:4px solid var(--blue);background:var(--soft-blue)}.condition-expected .indicator-condition{background:rgba(95,150,116,.16);color:#3f7452}.condition-near .indicator-condition{background:rgba(182,138,80,.18);color:#855f2c}.condition-below .indicator-condition{background:rgba(169,111,56,.17);color:#815126}.condition-critical .indicator-condition{background:rgba(191,111,112,.18);color:#98494c}.condition-neutral .indicator-condition{background:rgba(101,127,198,.15);color:#4d65a0}

.score-condition-tag{display:inline-flex;margin-left:7px;padding:2px 7px;border-radius:999px;font-size:.66rem;font-weight:760;line-height:1.3;vertical-align:middle;white-space:nowrap}.score-condition-tag.expected{background:rgba(95,150,116,.16);color:#3f7452}.score-condition-tag.near{background:rgba(182,138,80,.18);color:#855f2c}.score-condition-tag.below{background:rgba(169,111,56,.18);color:#815126}.score-condition-tag.critical{background:rgba(191,111,112,.18);color:#98494c}.score-condition-tag.neutral{background:rgba(101,127,198,.14);color:#4d65a0}
tr.score-condition-expected{background:rgba(95,150,116,.06)}tr.score-condition-near{background:rgba(182,138,80,.08)}tr.score-condition-below{background:rgba(169,111,56,.08)}tr.score-condition-critical{background:rgba(191,111,112,.08)}tr.score-condition-neutral{background:rgba(101,127,198,.06)}
tr.score-condition-expected>td:first-child{box-shadow:inset 4px 0 0 var(--green)}tr.score-condition-near>td:first-child{box-shadow:inset 4px 0 0 var(--amber)}tr.score-condition-below>td:first-child{box-shadow:inset 4px 0 0 #a96f38}tr.score-condition-critical>td:first-child{box-shadow:inset 4px 0 0 var(--red)}tr.score-condition-neutral>td:first-child{box-shadow:inset 4px 0 0 var(--blue)}
.score-condition-legend{display:flex;gap:8px;flex-wrap:wrap;margin:9px 0 12px}.score-condition-legend .score-condition-tag{margin-left:0}
.apdex-class{display:inline-flex;padding:2px 8px;border-radius:999px;font-size:.7rem;font-weight:760;white-space:nowrap}.apdex-class-satisfied{background:rgba(95,150,116,.16);color:#3f7452}.apdex-class-tolerating{background:rgba(205,161,60,.18);color:#7b5a10}.apdex-class-frustrated{background:rgba(191,111,112,.18);color:#98494c}.apdex-class-excluded{background:#eef0f3;color:#596274}
@media(max-width:1120px){.indicator-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.indicator-grid,.indicator-primary-grid{grid-template-columns:1fr}.result-tag,.priority-tag{white-space:normal}.priority-tag{margin-left:0;margin-top:4px}}
"""

_METRIC_RE = re.compile(
    r"<div\s+class=(?P<q>['\"])(?P<classes>[^'\"]*\bmetric\b[^'\"]*)(?P=q)>"
    r"<small>(?P<label>.*?)</small><strong>(?P<value>.*?)</strong></div>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_DIMENSION_ROW_RE = re.compile(
    r"<tr(?P<attrs>[^>]*)><td>(?P<dimension>[^<]+)</td><td>(?P<score>[^<]*)</td>"
    r"<td>(?P<coverage>[^<]*)</td><td>(?P<confidence>[^<]*)</td><td>(?P<consolidation>[^<]*)</td></tr>",
    flags=re.IGNORECASE,
)
_DETAILS_RE = re.compile(r"<details(?P<attrs>[^>]*)><summary>(?P<summary>.*?)</summary>(?P<body>.*?)</details>", flags=re.IGNORECASE | re.DOTALL)
_ARTICLE_RE = re.compile(r"<article\s+class=(?P<q>['\"])(?P<classes>[^'\"]*\bapdex-card\b[^'\"]*)(?P=q)>(?P<body>.*?)</article>", flags=re.IGNORECASE | re.DOTALL)
_PROFILE_RE = re.compile(r"<p class=['\"]intro['\"]><strong>Perfil sintético:</strong>.*?</p>", flags=re.IGNORECASE | re.DOTALL)
_TABLE_ROW_RE = re.compile(r"<tr(?P<attrs>[^>]*)>(?P<body>.*?)</tr>", flags=re.IGNORECASE | re.DOTALL)
_TABLE_CELL_RE = re.compile(r"<td(?P<attrs>[^>]*)>(?P<body>.*?)</td>", flags=re.IGNORECASE | re.DOTALL)
_ACTIONABLE_GOOD = {"pass", "aprovado", "success", "concluído", "consolidado"}
_ACTIONABLE_WARN = {"warning", "alerta", "partial", "parcial", "degraded", "degradado", "not_consolidated", "não consolidado", "concluído com limitações", "complete_with_limitations"}
_ACTIONABLE_BAD = {"fail", "failed", "não aprovado", "reprovado", "error", "erro", "falhou", "blocked", "bloqueado"}


def enhance_report_html(html: str, *, page_name: str, report_dir: Path) -> str:
    """Add semantic visual states without changing persisted measurement values."""
    html = _decorate_metrics(html, page_name)
    html = _translate_readiness_table_headers(html)
    # Domain-specific semantics must run before the generic table decorator.
    # Otherwise a generic terminal state such as "Consolidado" can mask a more
    # important condition such as low confidence/coverage.
    if page_name in {"readiness.html", "mobile.html", "desktop.html"}:
        html = _enhance_score_page(html)
    elif page_name == "accessibility.html":
        html = _enhance_accessibility(html)
    elif page_name == "ai-usage.html":
        html = _enhance_ai_usage(html)
    elif page_name == "apdex.html":
        html = _enhance_apdex(html, report_dir)
    elif page_name == "web-performance.html":
        html = _enhance_web_performance(html)
    html = _decorate_actionable_rows(html)
    return enrich_indicator_provenance_html(html, page_name=page_name)


def _decorate_metrics(html: str, page_name: str) -> str:
    def replace(match: re.Match[str]) -> str:
        classes = _remove_state_classes(match.group("classes"))
        label_html = match.group("label")
        value_html = match.group("value")
        label = _plain(label_html)
        value = _plain(value_html)
        state, state_label, primary = _metric_state(page_name, label, value)
        if state is None:
            return match.group(0)
        class_list = classes.split()
        class_list.append(f"result-state-{state}")
        if primary and "metric-primary" not in class_list:
            class_list.append("metric-primary")
        tag = f"<span class='result-tag {state}'>{escape(state_label)}</span>" if state_label else ""
        return (
            f"<div class='{escape(' '.join(class_list), quote=True)}'>"
            f"<small>{label_html}</small><strong>{value_html}</strong>{tag}</div>"
        )

    return _METRIC_RE.sub(replace, html)


def _metric_state(page_name: str, label: str, value: str) -> tuple[str | None, str, bool]:
    # Only metric labels explicitly listed below receive result semantics. Metadata, provenance,
    # scopes, sources and integrity counters must remain neutral unless a specific contract says otherwise.
    key = label.casefold().strip()
    normalized = value.casefold().strip()

    if page_name == "accessibility.html":
        if key in {"falhas automatizadas", "ocorrências automatizadas"}:
            number = _first_number(value)
            if number is None:
                return "neutral", "Sem leitura", True
            return ("neutral", "Nenhuma ocorrência registrada", True) if number == 0 else ("bad", "Correção necessária", True)
        if key == "lighthouse médio":
            return _lighthouse_score_state(value, primary=True)
        if key == "conformidade wcag":
            return "neutral", "Requer avaliação humana", True

    if page_name == "web-performance.html":
        if key == "performance":
            return _lighthouse_score_state(value, primary=True)
        if key == "cwv":
            if normalized == "pass":
                return "good", "Aprovado no p75", True
            if normalized == "fail":
                return "bad", "Não aprovado no p75", True
            if normalized in {"unavailable", "incomplete", "-", "-", "n/a", "não disponível", "nao disponivel"}:
                return "neutral", "Dados de campo indisponíveis", True
        if key == "lcp p75":
            return _threshold_state(value, good=2500.0, needs=4000.0, primary=True)
        if key == "inp p75":
            return _threshold_state(value, good=200.0, needs=500.0, primary=True)
        if key == "cls p75":
            return _threshold_state(value, good=0.1, needs=0.25, primary=True)
        if key in {"lcp lab", "tbt lab", "cls lab", "fcp lab", "speed index"}:
            return "warn", "Diagnóstico de laboratório", False

    if page_name == "apdex.html":
        if key == "apdex":
            score = _first_number(value)
            if score is None:
                return "neutral", "Sem amostra", True
            if score >= 0.94:
                return "good", "Excelente no T configurado", True
            if score >= 0.85:
                return "good", "Bom no T configurado", True
            if score >= 0.70:
                return "warn", "Regular no T configurado", True
            if score >= 0.50:
                return "bad", "Ruim no T configurado", True
            return "bad", "Inaceitável no T configurado", True
        if key == "coef. variação":
            number = _first_number(value)
            if number is not None and number >= 25:
                return "warn", "Variabilidade elevada no teste", False

    if page_name == "ai-usage.html":
        if key == "status" and normalized == "no_eligible_findings":
            return "neutral", "Sem finding textual elegível", True
        if key == "status da sessão" and normalized == "success":
            return "good", "Execução concluída", False

    if key == "status":
        if normalized == "success":
            return "good", "Concluído", False
        if normalized in {"partial", "complete_with_limitations"}:
            return "warn", "Com limitações", False
        if normalized in {"fail", "failed", "degraded", "error"}:
            return "bad", "Falha", False
    return None, "", False


def _lighthouse_score_state(value: str, *, primary: bool) -> tuple[str, str, bool]:
    number = _first_number(value)
    if number is None:
        return "neutral", "Indisponível", primary
    if number >= 90:
        return "good", "Bom (90-100)", primary
    if number >= 50:
        return "warn", "Precisa melhorar (50-89)", primary
    return "bad", "Ruim (0-49)", primary


def _threshold_state(value: str, *, good: float, needs: float, primary: bool) -> tuple[str, str, bool]:
    number = _first_number(value)
    if number is None:
        return "neutral", "Indisponível", primary
    if number <= good:
        return "good", "Bom", primary
    if number <= needs:
        return "warn", "Precisa melhorar", primary
    return "bad", "Ruim", primary


def _score_condition(score_text: str, confidence: str, consolidation: str) -> tuple[str, str]:
    consolidation_key = consolidation.casefold().strip()
    confidence_key = confidence.casefold().strip()
    if consolidation_key in {"não aplicável", "nao aplicavel"}:
        return "neutral", "Não aplicável"
    value = _first_number(score_text)
    if value is None:
        return "neutral", "Sem medição conclusiva"
    if value < 40:
        return "critical", "Crítico"
    if value < 75:
        return "below", "Abaixo do esperado"
    if consolidation_key != "consolidado" or confidence_key == "baixa":
        return "near", "Quase no esperado"
    return "expected", "Dentro do esperado"


def _enhance_score_page(html: str) -> str:
    low_rows: list[tuple[str, str]] = []

    def row_replace(match: re.Match[str]) -> str:
        dimension = unescape(match.group("dimension")).strip()
        score = match.group("score").strip()
        coverage = match.group("coverage").strip()
        confidence = unescape(match.group("confidence")).strip()
        consolidation = unescape(match.group("consolidation")).strip()
        attrs = _strip_result_state(match.group("attrs"))
        state, label = _score_condition(score, confidence, consolidation)
        if confidence.casefold() == "baixa":
            low_rows.append((dimension, coverage))
        if dimension.casefold() == "dados estruturados" and consolidation.casefold() == "não aplicável":
            coverage = "-"
            confidence = "Não aplicável"
        coverage_number = _first_number(coverage)
        if state == "near" and coverage_number is not None and coverage_number < 80:
            label = "Quase no esperado · Cobertura insuficiente"
        elif state == "near" and confidence.casefold() == "baixa":
            label = "Quase no esperado · Confiança baixa"
        tag = f" <span class='score-condition-tag {state}'>{escape(label)}</span>"
        legacy_state = {"expected": "good", "near": "warn", "below": "warn", "critical": "bad", "neutral": "neutral"}[state]
        return (
            f"<tr{attrs} class='score-condition-{state} result-state-{legacy_state}'><td>{escape(dimension)}</td>"
            f"<td>{score}{tag}</td><td>{coverage}</td><td>{escape(confidence)}</td><td>{escape(consolidation)}</td></tr>"
        )

    html = _DIMENSION_ROW_RE.sub(row_replace, html)
    if "score-condition-legend" not in html:
        legend = (
            "<div class='score-condition-legend' aria-label='Legenda de condição do score'>"
            "<span class='score-condition-tag expected'>Dentro do esperado</span>"
            "<span class='score-condition-tag near'>Quase no esperado</span>"
            "<span class='score-condition-tag below'>Abaixo do esperado</span>"
            "<span class='score-condition-tag critical'>Crítico</span>"
            "<span class='score-condition-tag neutral'>Sem medição / não aplicável</span></div>"
        )
        html = re.sub(r"(<h2>Dimensões[^<]*</h2>)", r"\1" + legend, html, count=1, flags=re.IGNORECASE)
    if "score-confidence-note" not in html and "Confiança baixa" in html:
        items = "".join(f"<li><strong>{escape(name)}</strong>: coverage {escape(coverage)}.</li>" for name, coverage in low_rows)
        detail = (
            "<div class='notice warn score-confidence-note'><strong>Por que a confiança está baixa?</strong> "
            "Confidence mede completude/cobertura da avaliação, não a qualidade do site. "
            "Ela aumenta quando regras aplicáveis deixam de ficar UNKNOWN/ERROR e passam a ter resultado e evidência suficientes."
            + (f"<ul>{items}</ul>" if items else "")
            + "<span class='result-tag warn'>Não elevar artificialmente</span></div>"
        )
        html = html.replace("</header>", "</header>" + detail, 1)
    if "Dados estruturados" in html and "structured-data-absence-note" not in html:
        note = (
            "<div class='notice structured-data-absence-note'><strong>Dados estruturados: ausência é uma lacuna leve, não falha de coleta.</strong> "
            "Estado observado <strong>Opcional / não detectado</strong> não significa que a dimensão inteira saiu do SARI: quando nenhum JSON-LD é observado, BR-GEO-034 permanece aplicável e recebe WARNING com fator reduzido; regras de tipos/consistência sem markup podem ficar NOT_APPLICABLE. "
            "JSON-LD válido e coerente pode melhorar a dimensão; markup inválido ou contraditório pode reduzi-la.</div>"
        )
        scorecard_end = html.find("</section>", html.find("Dimensões"))
        if scorecard_end >= 0:
            html = html[:scorecard_end] + note + html[scorecard_end:]
        else:
            html += note
    return html


def _enhance_accessibility(html: str) -> str:
    audit_ids = set(re.findall(r"Audit(?: Lighthouse)?:</strong>\s*<code>([^<]+)</code>", html, flags=re.IGNORECASE))
    total_match = re.search(r"<small>Falhas automatizadas</small><strong>([0-9]+)</strong>", html, flags=re.IGNORECASE)
    total = int(total_match.group(1)) if total_match else None
    html = html.replace("<small>Falhas automatizadas</small>", "<small>Ocorrências automatizadas</small>")
    if "accessibility-count-note" not in html:
        count_text = (f"Nesta coleta: {total} ocorrência(s) em {len(audit_ids)} audit(s) reprovado(s). " if total is not None and audit_ids else "")
        note = (
            "<div class='notice accessibility-count-note'><strong>Leitura das ocorrências automatizadas.</strong> "
            + count_text
            + "Um mesmo audit pode gerar mais de uma ocorrência em elementos/nós diferentes. "
            "Conformidade WCAG permanece não determinada porque automação não substitui avaliação humana dos critérios aplicáveis.</div>"
        )
        html = html.replace("</header>", "</header>" + note, 1)
    return _prioritize_accessibility_details(html)


def _prioritize_accessibility_details(html: str) -> str:
    high_audits = {"image-alt", "link-name", "button-name", "label", "aria-dialog-name", "aria-required-attr", "aria-required-children", "color-contrast"}

    def replace(match: re.Match[str]) -> str:
        body = match.group("body")
        summary = match.group("summary")
        attrs = _strip_priority_class(match.group("attrs"))
        audit_match = re.search(r"Audit(?: Lighthouse)?:</strong>\s*<code>([^<]+)</code>", body, flags=re.IGNORECASE)
        audit_id = audit_match.group(1).strip().casefold() if audit_match else ""
        if audit_id not in high_audits:
            return match.group(0)
        if "priority-tag" not in summary:
            summary += " <span class='priority-tag high'>Prioridade alta</span>"
        return f"<details{attrs} class='priority-high'><summary>{summary}</summary>{body}</details>"

    return _DETAILS_RE.sub(replace, html)


def _enhance_ai_usage(html: str) -> str:
    if "NO_ELIGIBLE_FINDINGS" not in html or "m20-no-eligible-note" in html:
        return html
    note = (
        "<div class='notice m20-no-eligible-note'><strong>NO_ELIGIBLE_FINDINGS é um estado esperado, não erro.</strong> "
        "A remediação textual por IA só é chamada para findings de conteúdo/semântica elegíveis. Findings técnicos, como canonical, "
        "continuam na remediação determinística e não geram chamada textual nem custo Sugestões e remediação de conteúdo por IA.</div>"
    )
    marker = "<section id='remediation-ai-telemetry'"
    pos = html.find(marker)
    if pos >= 0:
        section_end = html.find("</section>", pos)
        if section_end >= 0:
            section_end += len("</section>")
            html = html[:section_end] + note + html[section_end:]
    return html


def _enhance_apdex(html: str, report_dir: Path) -> str:
    html = _reconcile_apdex_profiles(html, report_dir)
    html = html.replace(
        '<div class="notice"><strong>Correlação com campo</strong>',
        '<div class="notice warn"><strong>Correlação com campo</strong>',
    ).replace(
        "<div class='notice'><strong>Correlação com campo</strong>",
        "<div class='notice warn'><strong>Correlação com campo</strong>",
    )
    if "apdex-threshold-note" not in html:
        threshold = _extract_apdex_threshold(html)
        threshold_text = f"<code>T={threshold:g}s</code>" if threshold is not None else "o T configurado"
        note = (
            "<div class='notice warn apdex-threshold-note'><strong>Apdex é relativo ao threshold configurado.</strong> "
            f"Um Apdex alto significa que as amostras atenderam {threshold_text}; não significa, isoladamente, que a página seja rápida em termos absolutos. "
            "Quando CrUX/Core Web Vitals ou Lighthouse apontam degradação, trate o conflito de sinais explicitamente e revise se T representa o objetivo operacional desejado.</div>"
        )
        marker = "<section class='panel'><div class='kicker'>Visão executiva</div>"
        pos = html.find(marker)
        html = html[:pos] + note + html[pos:] if pos >= 0 else html.replace("</header>", "</header>" + note, 1)
    if "CrUX/Core Web Vitals também não aprovou" in html and "apdex-conflict" not in html:
        html = html.replace("page-card apdex-card", "page-card apdex-card apdex-conflict")
    return html


def _extract_apdex_threshold(html: str) -> float | None:
    match = re.search(r"<small>T</small><strong>([0-9]+(?:\.[0-9]+)?)\s*s</strong>", html, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    match = re.search(r"<small>Apdex</small><strong>[0-9.]+\s*\[([0-9.]+)\]", html, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def _reconcile_apdex_profiles(html: str, report_dir: Path) -> str:
    profiles = _persisted_apdex_profiles(report_dir)
    if not profiles:
        return html

    def replace_article(match: re.Match[str]) -> str:
        body = match.group("body")
        device_match = re.search(r"<span class=['\"]badge['\"]>(MOBILE|DESKTOP)</span>", body, flags=re.IGNORECASE)
        url_match = re.search(r"<h3 class=['\"]page-url['\"]>(.*?)</h3>", body, flags=re.IGNORECASE | re.DOTALL)
        if not device_match or not url_match:
            return match.group(0)
        device = device_match.group(1).upper()
        url = unescape(_plain(url_match.group(1))).strip()
        profile = profiles.get((url, device))
        if not profile:
            return match.group(0)
        profile_text = _profile_text(profile)
        corrected = _PROFILE_RE.sub(
            f"<p class='intro'><strong>Perfil sintético:</strong> {escape(profile_text)}</p>",
            body,
            count=1,
        )
        classes = match.group("classes")
        return f"<article class='{escape(classes, quote=True)}'>{corrected}</article>"

    return _ARTICLE_RE.sub(replace_article, html)


def _persisted_apdex_profiles(report_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    database = report_dir.parent / "audit.db"
    if not database.is_file():
        return {}
    try:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        run = connection.execute("SELECT configuration FROM synthetic_apdex_runs LIMIT 1").fetchone()
        rows = connection.execute("SELECT url,device,profile_id FROM synthetic_apdex_summaries").fetchall()
    except sqlite3.Error:
        return {}
    finally:
        try:
            connection.close()
        except UnboundLocalError:
            pass
    if run is None:
        return {}
    try:
        configuration = json.loads(str(run["configuration"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        configuration = {}
    if not isinstance(configuration, dict):
        return {}
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        device = str(row["device"]).upper()
        selected = configuration.get("mobile_profile" if device == "MOBILE" else "desktop_profile")
        if not isinstance(selected, dict):
            selected = {"profile_id": row["profile_id"]}
        result[(str(row["url"]), device)] = selected
    return result


def _profile_text(profile: dict[str, Any]) -> str:
    viewport = profile.get("viewport") if isinstance(profile.get("viewport"), dict) else {}
    return (
        f"{profile.get('profile_id', '-')} · CPU {profile.get('cpu_slowdown', '-')}× · "
        f"RTT {profile.get('rtt_ms', '-')} ms · down {profile.get('download_kbps', '-')} Kbps · "
        f"up {profile.get('upload_kbps', '-')} Kbps · viewport {viewport.get('width', '-')}×{viewport.get('height', '-')} · "
        "BrowserContext novo · cache OFF · randomização NONE · UA efetivo resolvido em runtime; UA do perfil é template"
    )


def _enhance_web_performance(html: str) -> str:
    if "web-vitals-range-legend" not in html:
        legend = (
            "<div class='semantic-legend web-vitals-range-legend'><strong>Faixas Core Web Vitals (p75):</strong> "
            "<span class='result-tag good'>Bom: LCP ≤2,5s · INP ≤200ms · CLS ≤0,1</span>"
            "<span class='result-tag warn'>Precisa melhorar: LCP ≤4s · INP ≤500ms · CLS ≤0,25</span>"
            "<span class='result-tag bad'>Ruim: acima dessas faixas</span></div>"
        )
        marker = "<h4>Core Web Vitals · dados reais CrUX</h4>"
        html = html.replace(marker, marker + legend, 1)
    return _prioritize_performance_details(html)


def _prioritize_performance_details(html: str) -> str:
    high_categories = {
        "JAVASCRIPT_MAIN_THREAD", "RENDER_BLOCKING", "LCP", "LAYOUT_SHIFT",
        "CRITICAL_REQUEST_CHAIN", "NETWORK_DEPENDENCY", "SERVER_RESPONSE",
    }
    medium_categories = {"IMAGE_DELIVERY", "UNUSED_CODE", "CACHE", "THIRD_PARTY", "DOM_SIZE", "FONT"}

    def replace(match: re.Match[str]) -> str:
        body = match.group("body")
        summary = match.group("summary")
        attrs = _strip_priority_class(match.group("attrs"))
        category_match = re.search(r"<strong>Categoria:</strong>\s*([^·<]+)", body, flags=re.IGNORECASE)
        category = category_match.group(1).strip().upper() if category_match else ""
        duration = _largest_ms(body)
        priority: str | None = None
        if category in high_categories or (duration is not None and duration >= 1000):
            priority = "high"
        elif category in medium_categories or (duration is not None and duration >= 250):
            priority = "medium"
        if priority is None:
            return match.group(0)
        if "priority-tag" not in summary:
            label = "Prioridade alta" if priority == "high" else "Prioridade média"
            summary += f" <span class='priority-tag {priority}'>{label}</span>"
        return f"<details{attrs} class='priority-{priority}'><summary>{summary}</summary>{body}</details>"

    return _DETAILS_RE.sub(replace, html)


def _largest_ms(text: str) -> float | None:
    values = [float(item) for item in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*ms\b", _plain(text), flags=re.IGNORECASE)]
    return max(values) if values else None



def _merge_class_attr(attrs: str, class_name: str) -> str:
    match = re.search(r"\sclass=(?P<q>['\"])(?P<classes>[^'\"]*)(?P=q)", attrs, flags=re.IGNORECASE)
    if match is None:
        return attrs.rstrip() + f" class='{class_name}'"
    classes = match.group("classes").split()
    for requested in class_name.split():
        if requested not in classes:
            classes.append(requested)
    replacement = f" class={match.group('q')}{' '.join(classes)}{match.group('q')}"
    return attrs[: match.start()] + replacement + attrs[match.end() :]


def _decorate_actionable_rows(html: str) -> str:
    """Give actionable result cells a consistent semantic state across reports."""
    def replace_row(match: re.Match[str]) -> str:
        # A domain-specific row state has precedence over generic terminal values.
        # This keeps e.g. LOW confidence + CONSOLIDATED visually warning, not green.
        if re.search(r"\bresult-state-(?:good|warn|bad|neutral)\b", match.group("attrs")):
            return match.group(0)
        body = match.group("body")
        cells = list(_TABLE_CELL_RE.finditer(body))
        if not cells:
            return match.group(0)
        selected: tuple[re.Match[str], str] | None = None
        rank = {"good": 1, "warn": 2, "bad": 3}
        current_rank = 0
        for cell in cells:
            value = _plain(cell.group("body")).casefold().strip()
            state = None
            if value in _ACTIONABLE_BAD:
                state = "bad"
            elif value in _ACTIONABLE_WARN:
                state = "warn"
            elif value in _ACTIONABLE_GOOD:
                state = "good"
            if state is not None and rank[state] > current_rank:
                selected = (cell, state)
                current_rank = rank[state]
        if selected is None:
            return match.group(0)
        cell, state = selected
        cell_body = cell.group("body")
        cell_attrs = _merge_class_attr(cell.group("attrs"), f"result-cell {state}")
        if "result-tag" not in cell_body:
            cell_body = f"<span class='result-tag {state}'>{cell_body}</span>"
        replacement = f"<td{cell_attrs}>{cell_body}</td>"
        body = body[: cell.start()] + replacement + body[cell.end() :]
        row_attrs = _strip_result_state(match.group("attrs"))
        row_attrs = _merge_class_attr(row_attrs, f"result-state-{state}")
        return f"<tr{row_attrs}>{body}</tr>"

    return _TABLE_ROW_RE.sub(replace_row, html)


def _translate_readiness_table_headers(html: str) -> str:
    return html.replace(
        "<th>Dimensão</th><th>Score</th><th>Coverage</th><th>Confidence</th><th>Consolidação</th>",
        "<th>Dimensão</th><th>Pontuação</th><th>Cobertura</th><th>Confiança</th><th>Consolidação</th>",
    )

def _plain(value: str) -> str:
    return unescape(_TAG_RE.sub("", value)).strip()


def _first_number(value: str) -> float | None:
    match = re.search(r"-?[0-9]+(?:[.,][0-9]+)?", _plain(value))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def _remove_state_classes(classes: str) -> str:
    kept = [item for item in classes.split() if not item.startswith("result-state-") and item != "metric-primary"]
    return " ".join(kept)


def _strip_result_state(attrs: str) -> str:
    attrs = re.sub(r"\s+class=(['\"])[^'\"]*result-state-[^'\"]*\1", "", attrs, flags=re.IGNORECASE)
    return attrs.rstrip()


def _strip_priority_class(attrs: str) -> str:
    attrs = re.sub(r"\s+class=(['\"])[^'\"]*priority-(?:high|medium)[^'\"]*\1", "", attrs, flags=re.IGNORECASE)
    return attrs.rstrip()
