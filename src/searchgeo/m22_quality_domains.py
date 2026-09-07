"""Acessibilidade automatizada e diagnósticos Web domain-separated accessibility and performance diagnostics.

Acessibilidade automatizada e diagnósticos Web reuses persisted PageSpeed/Lighthouse artifacts collected by Web Performance externo. It does
not call external services, does not mutate SCORE-GEO-002, and does not promote
an automated Lighthouse accessibility result to a WCAG conformance claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from searchgeo.persistence import AuditWorkspace
from searchgeo.report_navigation import render_report_navigation

ACCESSIBILITY_FILE = "accessibility.html"
PERFORMANCE_FILE = "web-performance.html"

_ACCESSIBILITY_REFERENCES: tuple[tuple[str, str, str], ...] = (
    (
        "WCAG 2.2 — W3C Recommendation",
        "https://www.w3.org/TR/WCAG22/",
        "Norma W3C usada como referência de acessibilidade; a auditoria automatizada não equivale a uma declaração de conformidade WCAG.",
    ),
    (
        "WCAG 2.2 — 4.1.2 Name, Role, Value",
        "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value",
        "Exige que componentes de interface exponham nome e papel programaticamente determináveis; inclui regras de teste para nomes acessíveis de botões, links e campos.",
    ),
    (
        "Lighthouse accessibility score",
        "https://developer.chrome.com/docs/lighthouse/accessibility/scoring",
        "Documenta que o score é uma média ponderada de auditorias automatizadas e que auditorias manuais não entram no score.",
    ),
    (
        "Lighthouse overview",
        "https://developer.chrome.com/docs/lighthouse/overview",
        "Define Lighthouse como ferramenta automatizada e recomenda usar auditorias reprovadas como indicadores de melhoria.",
    ),
)

_PERFORMANCE_REFERENCES: tuple[tuple[str, str, str], ...] = (
    (
        "Chrome Performance Insights",
        "https://developer.chrome.com/docs/performance/insights",
        "Catálogo oficial de diagnósticos como render blocking, LCP, árvore de dependências, JavaScript, imagens, DOM e terceiros.",
    ),
    (
        "Render-blocking requests",
        "https://developer.chrome.com/docs/performance/insights/render-blocking",
        "Documenta recursos que bloqueiam a renderização inicial e podem atrasar LCP.",
    ),
    (
        "Network dependency tree",
        "https://developer.chrome.com/docs/performance/insights/network-dependency-tree",
        "Documenta cadeias de dependência críticas e estratégias para reduzir caminho crítico e bytes críticos.",
    ),
    (
        "Lighthouse Performance Scoring",
        "https://developer.chrome.com/docs/lighthouse/performance/performance-scoring",
        "Metodologia oficial do score de laboratório do Lighthouse.",
    ),
    (
        "Core Web Vitals",
        "https://web.dev/articles/vitals",
        "Referência oficial para LCP, INP e CLS e interpretação de experiência de campo.",
    ),
    (
        "Apdex Technical Specification v1.1",
        "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf",
        "Define Apdex a partir de amostras de tempo de resposta e de um threshold T explícito; F = 4T.",
    ),
)

_A11Y_REFERENCE_BY_AUDIT: dict[str, tuple[str, str]] = {
    "button-name": (
        "WCAG 2.2 4.1.2 — Name, Role, Value",
        "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value",
    ),
    "link-name": (
        "WCAG 2.2 4.1.2 — Name, Role, Value",
        "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value",
    ),
    "label": (
        "WCAG 2.2 4.1.2 — Name, Role, Value",
        "https://www.w3.org/WAI/WCAG22/Understanding/name-role-value",
    ),
    "aria-allowed-attr": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "aria-conditional-attr": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "aria-prohibited-attr": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "aria-required-attr": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "aria-roles": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "aria-valid-attr-value": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "aria-valid-attr": ("WAI-ARIA 1.2", "https://www.w3.org/TR/wai-aria-1.2/"),
    "image-alt": (
        "WCAG 2.2 1.1.1 — Non-text Content",
        "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content",
    ),
    "html-has-lang": (
        "WCAG 2.2 3.1.1 — Language of Page",
        "https://www.w3.org/WAI/WCAG22/Understanding/language-of-page",
    ),
    "html-lang-valid": (
        "WCAG 2.2 3.1.1 — Language of Page",
        "https://www.w3.org/WAI/WCAG22/Understanding/language-of-page",
    ),
    "document-title": (
        "WCAG 2.2 2.4.2 — Page Titled",
        "https://www.w3.org/WAI/WCAG22/Understanding/page-titled",
    ),
    "color-contrast": (
        "WCAG 2.2 1.4.3 — Contrast (Minimum)",
        "https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum",
    ),
}

_PERFORMANCE_KEYWORDS = (
    "render-block", "critical-request", "network-dependency", "largest-contentful", "lcp",
    "layout-shift", "unused-javascript", "unused-css", "duplicated-javascript",
    "legacy-javascript", "bootup-time", "mainthread", "forced-reflow", "server-response",
    "document-latency", "image-delivery", "optimized-image", "responsive-image",
    "offscreen-image", "text-compression", "font-display", "third-party", "dom-size", "cache",
)
_METRIC_AUDITS = frozenset({
    "first-contentful-paint", "largest-contentful-paint", "speed-index", "total-blocking-time",
    "cumulative-layout-shift", "interactive", "max-potential-fid",
})
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^\)]+\)")
_MARKDOWN_CODE_RE = re.compile(r"`([^`]+)`")


@dataclass(frozen=True, slots=True)
class NodeEvidence:
    selector: str | None
    snippet: str | None
    label: str | None
    explanation: str | None
    url: str | None
    wasted_ms: float | None
    wasted_bytes: float | None
    total_bytes: float | None
    duration_ms: float | None


@dataclass(frozen=True, slots=True)
class AccessibilityIssue:
    lighthouse_audit_id: str
    title: str
    description: str
    score: float | None
    evidence: NodeEvidence
    reference_title: str | None
    reference_url: str | None


@dataclass(frozen=True, slots=True)
class PerformanceDiagnostic:
    lighthouse_audit_id: str
    title: str
    description: str
    score: float | None
    display_value: str | None
    evidence: NodeEvidence
    category: str


@dataclass(frozen=True, slots=True)
class ContextDiagnostics:
    normalized_url: str
    device: str
    accessibility_score: float | None
    accessibility_issues: tuple[AccessibilityIssue, ...]
    manual_accessibility_audits: int
    performance_diagnostics: tuple[PerformanceDiagnostic, ...]
    source_artifact: str | None
    source_status: str


def enrich_m22_domain_reports(*, audit_id: str, workspace: AuditWorkspace) -> Path:
    """Project Web Performance externo raw artifacts into separate A11Y and Performance domains."""
    report_dir = workspace.root / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    contexts = _load_contexts(audit_id, workspace)

    accessibility_path = report_dir / ACCESSIBILITY_FILE
    accessibility_path.write_text(_accessibility_page(contexts, report_dir), encoding="utf-8", newline="\n")

    performance_path = report_dir / PERFORMANCE_FILE
    if performance_path.is_file():
        html = performance_path.read_text(encoding="utf-8")
        if "m22-performance-diagnostics" not in html:
            section = _performance_diagnostics_section(contexts)
            anchor = "<section class='panel'><div class='kicker'>Operação externa</div>"
            html = html.replace(anchor, section + anchor, 1) if anchor in html else html.replace("</main>", section + "</main>", 1)
        performance_path.write_text(html, encoding="utf-8", newline="\n")

    index_path = report_dir / "index.html"
    if index_path.is_file():
        html = index_path.read_text(encoding="utf-8")
        if "m22-accessibility-summary" not in html:
            summary = _accessibility_index_summary(contexts)
            marker = "<section id='m21-performance-summary'"
            position = html.find(marker)
            if position >= 0:
                html = html[:position] + summary + html[position:]
            else:
                html = html.replace("</main>", summary + "</main>", 1)
        index_path.write_text(html, encoding="utf-8", newline="\n")

    references_path = report_dir / "references.html"
    if references_path.is_file():
        html = references_path.read_text(encoding="utf-8")
        if "m22-domain-methodology" not in html:
            html = html.replace("</main>", _references_section() + "</main>", 1)
        references_path.write_text(html, encoding="utf-8", newline="\n")
    return accessibility_path


def _load_contexts(audit_id: str, workspace: AuditWorkspace) -> tuple[ContextDiagnostics, ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            rows = list(connection.execute(
                """SELECT o.*,p.normalized_url FROM web_performance_observations o
                   JOIN pages p ON p.page_id=o.page_id WHERE o.audit_id=?
                   ORDER BY p.normalized_url,o.device,o.observation_id""",
                (audit_id,),
            ).fetchall())
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return ()
            raise
    finally:
        connection.close()

    contexts: list[ContextDiagnostics] = []
    for row in rows:
        artifact_ref = str(row["pagespeed_artifact_reference"] or "") or None
        payload = _read_artifact(workspace, artifact_ref)
        if payload is None:
            issues, manual, performance, source_status = (), 0, (), "ARTIFACT_UNAVAILABLE"
        else:
            issues, manual = extract_accessibility_issues(payload)
            performance = extract_performance_diagnostics(payload)
            source_status = "LIGHTHOUSE_ARTIFACT"
        contexts.append(ContextDiagnostics(
            normalized_url=str(row["normalized_url"]),
            device=str(row["device"]),
            accessibility_score=_float(row["accessibility_score"]),
            accessibility_issues=issues,
            manual_accessibility_audits=manual,
            performance_diagnostics=performance,
            source_artifact=artifact_ref,
            source_status=source_status,
        ))
    return tuple(contexts)


def _read_artifact(workspace: AuditWorkspace, reference: str | None) -> dict[str, Any] | None:
    if not reference:
        return None
    root = workspace.root.resolve()
    path = (workspace.root / reference).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def extract_accessibility_issues(payload: dict[str, Any]) -> tuple[tuple[AccessibilityIssue, ...], int]:
    """Return only automated Lighthouse accessibility failures plus manual count."""
    result = _lighthouse_result(payload)
    audits = result.get("audits") if isinstance(result.get("audits"), dict) else {}
    category = _category(result, "accessibility")
    refs = category.get("auditRefs") if isinstance(category.get("auditRefs"), list) else []
    failures: list[AccessibilityIssue] = []
    manual_count = 0
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        audit_id = str(ref.get("id") or "").strip()
        audit = audits.get(audit_id)
        if not audit_id or not isinstance(audit, dict):
            continue
        mode = str(audit.get("scoreDisplayMode") or "").casefold()
        if mode == "manual":
            manual_count += 1
            continue
        score = _float(audit.get("score"))
        if score is None or score >= 1.0:
            continue
        title = str(audit.get("title") or audit_id)
        description = _plain_text(audit.get("description"))
        evidence = _detail_evidence(audit.get("details"), max_items=30)
        if not evidence:
            evidence = (NodeEvidence(None, None, None, _plain_text(audit.get("explanation")) or None, None, None, None, None, None),)
        reference = _A11Y_REFERENCE_BY_AUDIT.get(audit_id)
        for item in evidence:
            failures.append(AccessibilityIssue(
                lighthouse_audit_id=audit_id,
                title=title,
                description=description,
                score=score,
                evidence=item,
                reference_title=reference[0] if reference else None,
                reference_url=reference[1] if reference else None,
            ))
            if len(failures) >= 200:
                return tuple(failures), manual_count
    return tuple(failures), manual_count


def extract_performance_diagnostics(payload: dict[str, Any]) -> tuple[PerformanceDiagnostic, ...]:
    """Extract evidence-bearing Lighthouse performance opportunities/insights."""
    result = _lighthouse_result(payload)
    audits = result.get("audits") if isinstance(result.get("audits"), dict) else {}
    category = _category(result, "performance")
    refs = category.get("auditRefs") if isinstance(category.get("auditRefs"), list) else []
    ref_ids = {str(ref.get("id")) for ref in refs if isinstance(ref, dict) and ref.get("id")}
    diagnostics: list[PerformanceDiagnostic] = []
    for audit_id, audit in audits.items():
        if not isinstance(audit_id, str) or not isinstance(audit, dict) or audit_id in _METRIC_AUDITS:
            continue
        if ref_ids and audit_id not in ref_ids and not _is_performance_diagnostic_id(audit_id):
            continue
        if not _is_performance_diagnostic_id(audit_id):
            continue
        mode = str(audit.get("scoreDisplayMode") or "").casefold()
        if mode in {"manual", "not-applicable", "error"}:
            continue
        score = _float(audit.get("score"))
        evidence = _detail_evidence(audit.get("details"), max_items=30)
        informative = mode in {"informative", "numeric"}
        if score is not None and score >= 1.0 and not informative:
            continue
        if score is not None and score >= 1.0 and not evidence:
            continue
        if score is None and not evidence and mode != "informative":
            continue
        if not evidence:
            evidence = (NodeEvidence(None, None, None, _plain_text(audit.get("explanation")) or None, None, None, None, None, None),)
        for item in evidence:
            diagnostics.append(PerformanceDiagnostic(
                lighthouse_audit_id=audit_id,
                title=str(audit.get("title") or audit_id),
                description=_plain_text(audit.get("description")),
                score=score,
                display_value=_string(audit.get("displayValue")),
                evidence=item,
                category=_performance_category(audit_id),
            ))
            if len(diagnostics) >= 250:
                return tuple(diagnostics)
    return tuple(diagnostics)


def _lighthouse_result(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("lighthouseResult")
    return result if isinstance(result, dict) else {}


def _category(result: dict[str, Any], name: str) -> dict[str, Any]:
    categories = result.get("categories")
    if not isinstance(categories, dict):
        return {}
    category = categories.get(name)
    return category if isinstance(category, dict) else {}


def _is_performance_diagnostic_id(audit_id: str) -> bool:
    lowered = audit_id.casefold()
    return any(keyword in lowered for keyword in _PERFORMANCE_KEYWORDS)


def _performance_category(audit_id: str) -> str:
    value = audit_id.casefold()
    if "render-block" in value: return "RENDER_BLOCKING"
    if "critical-request" in value or "network-dependency" in value: return "CRITICAL_PATH"
    if "lcp" in value or "largest-contentful" in value: return "LCP"
    if "layout-shift" in value: return "LAYOUT_STABILITY"
    if "javascript" in value or "bootup" in value or "mainthread" in value or "forced-reflow" in value: return "JAVASCRIPT_MAIN_THREAD"
    if "css" in value: return "CSS"
    if "image" in value: return "IMAGES"
    if "font" in value: return "FONTS"
    if "third-party" in value: return "THIRD_PARTY"
    if "server" in value or "document-latency" in value: return "SERVER_DOCUMENT"
    if "dom-size" in value: return "DOM"
    if "cache" in value: return "CACHE"
    return "OTHER"


def _detail_evidence(details: Any, *, max_items: int) -> tuple[NodeEvidence, ...]:
    if not isinstance(details, (dict, list)):
        return ()
    candidates: list[dict[str, Any]] = []
    _collect_detail_dicts(details, candidates, max_items=max_items * 4)
    evidence: list[NodeEvidence] = []
    seen: set[tuple[Any, ...]] = set()
    for item in candidates:
        node = item.get("node") if isinstance(item.get("node"), dict) else {}
        selector = _first_string(node.get("selector"), item.get("selector"))
        snippet = _first_string(node.get("snippet"), item.get("snippet"))
        label = _first_string(node.get("nodeLabel"), item.get("nodeLabel"), node.get("label"), item.get("label"))
        explanation = _first_string(node.get("explanation"), item.get("explanation"), item.get("failureSummary"))
        url = _find_url(item)
        wasted_ms = _first_float(item, "wastedMs", "wastedTime", "wastedTimeMs")
        wasted_bytes = _first_float(item, "wastedBytes")
        total_bytes = _first_float(item, "totalBytes", "transferSize", "resourceSize")
        duration_ms = _first_float(item, "duration", "durationMs")
        if not any(value is not None for value in (selector, snippet, label, explanation, url, wasted_ms, wasted_bytes, total_bytes, duration_ms)):
            continue
        signature = (selector, snippet, label, explanation, url, wasted_ms, wasted_bytes, total_bytes, duration_ms)
        if signature in seen:
            continue
        seen.add(signature)
        evidence.append(NodeEvidence(selector, snippet, label, explanation, url, wasted_ms, wasted_bytes, total_bytes, duration_ms))
        if len(evidence) >= max_items:
            break
    return tuple(evidence)


def _collect_detail_dicts(value: Any, output: list[dict[str, Any]], *, max_items: int) -> None:
    if len(output) >= max_items:
        return
    if isinstance(value, dict):
        interesting = {"node", "selector", "snippet", "nodeLabel", "explanation", "failureSummary", "url", "wastedMs", "wastedBytes", "totalBytes", "duration", "durationMs"}
        if interesting.intersection(value):
            output.append(value)
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                _collect_detail_dicts(nested, output, max_items=max_items)
                if len(output) >= max_items:
                    return
    elif isinstance(value, list):
        for nested in value:
            if isinstance(nested, (dict, list)):
                _collect_detail_dicts(nested, output, max_items=max_items)
                if len(output) >= max_items:
                    return


def _find_url(item: dict[str, Any]) -> str | None:
    direct = item.get("url")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    for key in ("request", "source", "entity"):
        nested = item.get(key)
        if isinstance(nested, dict):
            candidate = nested.get("url")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _first_float(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _float(item.get(key))
        if value is not None:
            return value
    return None


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _accessibility_page(contexts: tuple[ContextDiagnostics, ...], report_dir: Path) -> str:
    total_issues = sum(len(context.accessibility_issues) for context in contexts)
    scored = [context.accessibility_score for context in contexts if context.accessibility_score is not None]
    average = sum(scored) / len(scored) if scored else None
    with_artifact = sum(context.source_status == "LIGHTHOUSE_ARTIFACT" for context in contexts)
    cards = "".join(_accessibility_context_card(context) for context in contexts)
    if not cards:
        cards = "<p class='intro'>Nenhum contexto Lighthouse persistido. Habilite Web Performance para coletar a auditoria automatizada de acessibilidade.</p>"
    references = "".join(
        f"<li><a href='{escape(url, quote=True)}' target='_blank' rel='noopener'>{escape(title)}</a> — {escape(description)}</li>"
        for title, url, description in _ACCESSIBILITY_REFERENCES
    )
    nav = render_report_navigation(report_dir, ACCESSIBILITY_FILE)
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Acessibilidade — SearchGEO Readiness Auditor</title><link rel='stylesheet' href='css/site.css'></head><body>{nav}<main class='app-main'><header class='hero'><div class='eyebrow'>Acessibilidade automatizada e diagnósticos Web · domínio independente</div><h1>Acessibilidade automatizada</h1><p class='lead'>Diagnóstico separado do domínio GEO e da Web Performance. Reutiliza somente evidência Lighthouse persistida pelo Web Performance externo; não altera SCORE-GEO-002 e não declara conformidade WCAG.</p><div class='metric-grid'>{_metric('Contextos com artifact', f'{with_artifact}/{len(contexts)}')}{_metric('Falhas automatizadas', total_issues)}{_metric('Lighthouse médio', f'{average:.0f}/100' if average is not None else 'NÃO DISPONÍVEL')}{_metric('Conformidade WCAG', 'NÃO DETERMINADA')}</div></header><section class='panel'><div class='kicker'>Fronteira de domínio</div><h2>Como interpretar</h2><div class='notice warn'><strong>Não é certificação de acessibilidade.</strong> O Lighthouse automatiza parte dos checks. Auditorias manuais e validação humana continuam necessárias para uma conclusão de conformidade WCAG.</div><p class='intro'>Selector e trecho HTML são exibidos somente quando o próprio artifact Lighthouse fornece essa evidência. Ausência de selector é mostrada como “não fornecido pela fonte”; o SearchGEO não inventa um alvo DOM.</p><p class='intro'>O uso de <code>aria-label</code> não é uma correção universal. Nomes acessíveis podem vir de texto nativo, <code>label</code>, <code>aria-labelledby</code> ou outras relações válidas; a recomendação deve preservar a semântica HTML mais adequada ao controle.</p></section><section class='panel'><div class='kicker'>Resultados</div><h2>Findings automatizados por página e dispositivo</h2>{cards}</section><section class='panel'><div class='kicker'>Referências oficiais</div><h2>Base documental</h2><ul>{references}</ul></section><footer class='footer'>Acessibilidade automatizada e diagnósticos Web Acessibilidade é uma projeção de evidência persistida. Nenhuma falha ou score desta página entra automaticamente no Score GEO.</footer></main></body></html>\n"""


def _accessibility_context_card(context: ContextDiagnostics) -> str:
    if context.source_status != "LIGHTHOUSE_ARTIFACT":
        body = "<div class='notice'>Artifact Lighthouse indisponível para este contexto. Nenhuma conclusão de acessibilidade é produzida.</div>"
    elif not context.accessibility_issues:
        body = "<div class='notice good'><strong>Nenhuma falha automatizada persistida.</strong> Isso não elimina a necessidade dos checks manuais do Lighthouse/WCAG.</div>"
    else:
        body = "".join(_accessibility_issue_card(issue) for issue in context.accessibility_issues)
    return f"""<article class='page-card'><div class='finding-head'><div><span class='badge'>{escape(context.device)}</span> <span class='badge info'>LIGHTHOUSE</span></div><span class='badge'>{len(context.accessibility_issues)} falha(s)</span></div><h3 class='page-url'>{escape(context.normalized_url)}</h3><div class='metric-grid'>{_metric('Accessibility score', f'{context.accessibility_score:.0f}/100' if context.accessibility_score is not None else '—')}{_metric('Checks manuais declarados', context.manual_accessibility_audits)}{_metric('Artifact', context.source_artifact or '—')}</div>{body}</article>"""


def _accessibility_issue_card(issue: AccessibilityIssue) -> str:
    evidence = issue.evidence
    selector = evidence.selector or "NÃO FORNECIDO PELO LIGHTHOUSE"
    snippet = f"<pre>{escape(evidence.snippet)}</pre>" if evidence.snippet else "<p class='intro'>Trecho HTML não fornecido pelo Lighthouse para esta ocorrência.</p>"
    explanation = f"<p><strong>Explicação da ocorrência:</strong> {escape(evidence.explanation)}</p>" if evidence.explanation else ""
    recommendation = _a11y_recommendation(issue.lighthouse_audit_id)
    reference = (
        f"<a href='{escape(issue.reference_url, quote=True)}' target='_blank' rel='noopener'>{escape(issue.reference_title or 'referência')}</a>"
        if issue.reference_url else "Referência específica WCAG não mapeada; consultar Lighthouse Accessibility e WCAG 2.2 na seção de referências."
    )
    return f"""<details><summary>{escape(issue.title)} · <code>A11Y-LH-{escape(issue.lighthouse_audit_id)}</code></summary><div class='detail-body'><p><strong>Audit Lighthouse:</strong> <code>{escape(issue.lighthouse_audit_id)}</code></p><p>{escape(issue.description)}</p><p><strong>Selector observado:</strong> <code>{escape(selector)}</code></p>{snippet}{explanation}<p><strong>Sugestão:</strong> {escape(recommendation)}</p><p><strong>Referência:</strong> {reference}</p></div></details>"""


def _a11y_recommendation(audit_id: str) -> str:
    if audit_id in {"button-name", "link-name", "label"}:
        return "Fornecer um nome acessível programaticamente determinável usando semântica HTML nativa sempre que possível; usar aria-label/aria-labelledby somente quando apropriado ao contexto e revalidar o nome computado."
    if audit_id.startswith("aria-"):
        return "Corrigir role, estado ou propriedade ARIA conforme WAI-ARIA. Não adicionar ARIA para substituir semântica HTML nativa válida sem necessidade."
    if audit_id == "image-alt":
        return "Definir alternativa textual adequada à finalidade da imagem; imagens decorativas exigem tratamento diferente de imagens informativas."
    if audit_id in {"html-has-lang", "html-lang-valid"}:
        return "Declarar uma linguagem de página válida e coerente com o conteúdo principal."
    if audit_id == "document-title":
        return "Fornecer um título de página que identifique o tópico ou propósito da página."
    if audit_id == "color-contrast":
        return "Ajustar cores de primeiro plano/fundo para atender ao critério de contraste aplicável e reexecutar a medição."
    return "Corrigir a condição específica indicada pelo audit automatizado e reexecutar Lighthouse; quando o critério exigir julgamento humano, encaminhar para revisão manual de acessibilidade."


def _performance_diagnostics_section(contexts: tuple[ContextDiagnostics, ...]) -> str:
    total = sum(len(context.performance_diagnostics) for context in contexts)
    cards = "".join(_performance_context_card(context) for context in contexts if context.performance_diagnostics)
    if not cards:
        cards = "<p class='intro'>Nenhum diagnóstico técnico de performance com evidência detalhada foi extraído dos artifacts Lighthouse disponíveis.</p>"
    refs = "".join(
        f"<li><a href='{escape(url, quote=True)}' target='_blank' rel='noopener'>{escape(title)}</a> — {escape(description)}</li>"
        for title, url, description in _PERFORMANCE_REFERENCES
    )
    return f"""<section id='m22-performance-diagnostics' class='panel'><div class='kicker'>Acessibilidade automatizada e diagnósticos Web · diagnóstico técnico</div><h2>Recursos, primeira renderização e caminho crítico</h2><p class='intro'>Esta seção permanece no domínio Web Performance. Ela projeta oportunidades/insights já presentes no artifact Lighthouse e preserva URL, selector, snippet e economia estimada somente quando fornecidos pela fonte.</p><div class='metric-grid'>{_metric('Diagnósticos detalhados', total)}{_metric('Apdex', 'NÃO CALCULADO')}</div><div class='notice warn'><strong>Apdex não é inferido de Lighthouse/CrUX.</strong> A especificação Apdex exige um conjunto de amostras de tempo de resposta transacional e um threshold T explícito; PageSpeed request duration, LCP, INP e uma execução lab isolada não são substitutos metodologicamente equivalentes.</div>{cards}<h3>Referências oficiais</h3><ul>{refs}</ul></section>"""


def _performance_context_card(context: ContextDiagnostics) -> str:
    diagnostics = "".join(_performance_issue_card(item) for item in context.performance_diagnostics)
    return f"""<article class='page-card'><div class='finding-head'><div><span class='badge'>{escape(context.device)}</span> <span class='badge info'>LIGHTHOUSE</span></div><span class='badge'>{len(context.performance_diagnostics)} diagnóstico(s)</span></div><h3 class='page-url'>{escape(context.normalized_url)}</h3>{diagnostics}</article>"""


def _performance_issue_card(item: PerformanceDiagnostic) -> str:
    evidence = item.evidence
    pieces = [f"<p><strong>Categoria:</strong> {escape(item.category)} · <strong>Audit:</strong> <code>{escape(item.lighthouse_audit_id)}</code></p>"]
    if item.description: pieces.append(f"<p>{escape(item.description)}</p>")
    if item.display_value: pieces.append(f"<p><strong>Valor exibido pelo Lighthouse:</strong> {escape(item.display_value)}</p>")
    if evidence.url: pieces.append(f"<p><strong>Recurso observado:</strong> <code>{escape(evidence.url)}</code></p>")
    if evidence.selector: pieces.append(f"<p><strong>Selector observado:</strong> <code>{escape(evidence.selector)}</code></p>")
    if evidence.snippet: pieces.append(f"<pre>{escape(evidence.snippet)}</pre>")
    if evidence.label: pieces.append(f"<p><strong>Elemento/label:</strong> {escape(evidence.label)}</p>")
    if evidence.explanation: pieces.append(f"<p><strong>Explicação:</strong> {escape(evidence.explanation)}</p>")
    savings = []
    if evidence.wasted_ms is not None: savings.append(f"economia potencial {evidence.wasted_ms:.0f} ms")
    if evidence.wasted_bytes is not None: savings.append(f"economia potencial {evidence.wasted_bytes:.0f} bytes")
    if evidence.total_bytes is not None: savings.append(f"tamanho observado {evidence.total_bytes:.0f} bytes")
    if evidence.duration_ms is not None: savings.append(f"duração observada {evidence.duration_ms:.0f} ms")
    if savings: pieces.append(f"<p><strong>Dados quantitativos:</strong> {escape(' · '.join(savings))}</p>")
    pieces.append(f"<p><strong>Tratamento:</strong> {escape(_performance_recommendation(item.category))}</p>")
    return f"<details><summary>{escape(item.title)} · {escape(item.category)}</summary><div class='detail-body'>{''.join(pieces)}</div></details>"


def _performance_recommendation(category: str) -> str:
    return {
        "RENDER_BLOCKING": "Avaliar adiamento de recursos não necessários à primeira renderização, redução de CSS/JS crítico e inlining somente quando tecnicamente seguro. Não remover um recurso apenas por aparecer nesta lista.",
        "CRITICAL_PATH": "Reduzir profundidade/bytes de cadeias críticas, antecipar recursos realmente críticos e adiar dependências não necessárias à renderização inicial.",
        "LCP": "Tratar a subparte LCP apontada pela evidência — descoberta, prioridade, recurso, render delay ou elemento — sem presumir uma única causa quando o Lighthouse não a comprovar.",
        "LAYOUT_STABILITY": "Inspecionar os elementos apontados como contribuintes de layout shift e estabilizar dimensões/fluxo sem ocultar conteúdo necessário.",
        "JAVASCRIPT_MAIN_THREAD": "Reduzir trabalho de JavaScript/main thread indicado pelo audit, remover código não usado quando comprovado e dividir trabalho longo quando aplicável.",
        "CSS": "Reduzir CSS não utilizado ou custos identificados pelo audit, preservando estilos necessários à primeira renderização.",
        "IMAGES": "Otimizar entrega, dimensão, formato e prioridade das imagens apontadas, especialmente quando relacionadas ao LCP.",
        "FONTS": "Revisar carregamento/exibição de fontes para evitar bloqueio ou atraso de texto conforme o insight observado.",
        "THIRD_PARTY": "Quantificar o custo do terceiro apontado e reduzir, adiar ou isolar somente quando compatível com requisitos funcionais/negócio.",
        "SERVER_DOCUMENT": "Investigar latência do documento/resposta e decompor rede, servidor e dependências antes de atribuir causa à aplicação.",
        "DOM": "Reduzir complexidade/tamanho DOM quando o próprio audit indicar impacto, preservando semântica e funcionalidade.",
        "CACHE": "Revisar política de cache dos recursos apontados considerando mutabilidade e requisitos de invalidação.",
    }.get(category, "Usar o diagnóstico Lighthouse como evidência inicial, validar a causa técnica no contexto da aplicação e reexecutar a medição após a mudança.")


def _accessibility_index_summary(contexts: tuple[ContextDiagnostics, ...]) -> str:
    failures = sum(len(context.accessibility_issues) for context in contexts)
    scored = [context.accessibility_score for context in contexts if context.accessibility_score is not None]
    average = sum(scored) / len(scored) if scored else None
    return f"""<section id='m22-accessibility-summary' class='panel'><div class='kicker'>Domínio independente</div><h2>Acessibilidade</h2><p class='intro'>Auditoria Lighthouse automatizada, separada do Score GEO e da Web Performance. Não equivale a conformidade WCAG.</p><div class='metric-grid'>{_metric('Falhas automatizadas', failures)}{_metric('Lighthouse médio', f'{average:.0f}/100' if average is not None else 'NÃO DISPONÍVEL')}{_metric('Conformidade WCAG', 'NÃO DETERMINADA')}</div><p><a href='{ACCESSIBILITY_FILE}'>Abrir diagnóstico de acessibilidade →</a></p></section>"""


def _references_section() -> str:
    a11y_rows = "".join(f"<tr><td>Acessibilidade</td><td>{escape(title)}</td><td><a href='{escape(url, quote=True)}' target='_blank' rel='noopener'>abrir fonte</a></td><td>{escape(description)}</td></tr>" for title, url, description in _ACCESSIBILITY_REFERENCES)
    perf_rows = "".join(f"<tr><td>Performance</td><td>{escape(title)}</td><td><a href='{escape(url, quote=True)}' target='_blank' rel='noopener'>abrir fonte</a></td><td>{escape(description)}</td></tr>" for title, url, description in _PERFORMANCE_REFERENCES)
    return f"""<section id='m22-domain-methodology' class='panel'><div class='kicker'>Acessibilidade automatizada e diagnósticos Web · fronteiras de domínio</div><h2>Acessibilidade × Performance × GEO</h2><p class='intro'>Os três domínios compartilham apenas evidência quando tecnicamente útil. Score, findings e conclusões permanecem separados. Interdependência é mostrada como referência causal/operacional, nunca como soma silenciosa de indicadores.</p><div class='table-wrap'><table><thead><tr><th>Domínio</th><th>Fonte</th><th>Referência</th><th>Uso autorizado</th></tr></thead><tbody>{a11y_rows}{perf_rows}</tbody></table></div><div class='notice'><strong>Apdex:</strong> não é calculado nesta versão porque Web Performance externo não coleta uma população de tempos de resposta transacionais com threshold T aprovado. Inventar T ou usar duração da API PageSpeed como tempo do usuário violaria a semântica da métrica.</div></section>"""


def _metric(label: str, value: Any) -> str:
    return f"<div class='metric'><small>{escape(str(label))}</small><strong>{escape(str(value))}</strong></div>"


def _plain_text(value: Any) -> str:
    if not isinstance(value, str): return ""
    text = _MARKDOWN_LINK_RE.sub(r"\1", value)
    text = _MARKDOWN_CODE_RE.sub(r"\1", text)
    return " ".join(text.split())


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool): return None
    try: return float(value)
    except (TypeError, ValueError): return None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
