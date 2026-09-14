"""Final public-report UX guardrails.

This module is presentation-only. It keeps machine states in persistence untouched while
ensuring the generated HTML uses the canonical shell, readable pt-BR states, predictable
navigation and non-overlapping fulfillment banners.
"""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Callable

_INSTALLED = False

_FULFILLMENT_MARKER = "<!-- RASAI_AUDIT_FULFILLMENT_STATUS -->"
_FULFILLMENT_BANNER_RE = re.compile(
    re.escape(_FULFILLMENT_MARKER)
    + r'<section class="rasai-fulfillment-banner\b.*?</section>',
    flags=re.IGNORECASE | re.DOTALL,
)
_MAIN_RE = re.compile(r"<main\b[^>]*>", flags=re.IGNORECASE)
_NAV_GROUP_RE = re.compile(
    r"<details(?P<attrs>[^>]*\brasai-nav-group\b[^>]*)>(?P<body>.*?)</details>",
    flags=re.IGNORECASE | re.DOTALL,
)
_ACTIVE_LINK_RE = re.compile(
    r"<a\b[^>]*\bclass=(?P<q>['\"])[^'\"]*\bactive\b[^'\"]*(?P=q)",
    flags=re.IGNORECASE,
)
_OPEN_ATTR_RE = re.compile(
    r"\sopen(?:\s*=\s*(?:['\"]?open['\"]?))?",
    flags=re.IGNORECASE,
)
_READER_STATUS_RE = re.compile(
    r"<section\b[^>]*class=['\"][^'\"]*\brasai-analysis-status\b[^'\"]*['\"][^>]*"
    r"data-rasai-analysis-status=['\"]true['\"][^>]*>.*?</section>",
    flags=re.IGNORECASE | re.DOTALL,
)
_READER_PATH_RE = re.compile(
    r"<section\b[^>]*class=['\"][^'\"]*\brasai-dashboard-path\b[^'\"]*['\"][^>]*"
    r"data-rasai-dashboard-path=['\"]true['\"][^>]*>.*?</section>",
    flags=re.IGNORECASE | re.DOTALL,
)
_READER_TRIGGER_RE = re.compile(
    r"<section\b[^>]*class=['\"][^'\"]*\brasai-page-transparency\b[^'\"]*['\"][^>]*"
    r"data-rasai-page-help-trigger=['\"]true['\"][^>]*>.*?</section>",
    flags=re.IGNORECASE | re.DOTALL,
)
_READER_DIALOG_RE = re.compile(
    r"<dialog\b[^>]*data-rasai-page-help=['\"]true['\"][^>]*>.*?</dialog>",
    flags=re.IGNORECASE | re.DOTALL,
)

_PUBLIC_STATE_LABELS: dict[str, str] = {
    "NO_DATA": "Sem dados utilizáveis",
    "MEASURED": "Medido",
    "PENDING": "Pendente",
    "RUNNING": "Em execução",
    "WAITING_FOR_DATA": "Aguardando dados",
    "PROCESSING": "Em processamento",
    "PARTIAL_RETRYABLE": "Parcial — reprocessamento disponível",
    "PARTIAL_BLOCKED": "Parcial — há bloqueios",
    "FAILED_RETRYABLE": "Falha recuperável",
    "FAILED_PERMANENT": "Falha permanente",
    "FAILED_FATAL": "Falha não recuperável",
    "EXPIRED_FOR_COMPLETION": "Validade expirada para conclusão",
    "PRELIMINARY": "Preliminar",
    "FINAL": "Final",
    "INCOMPLETE": "Incompleto",
    "NO_CONTEXTS": "Sem contextos elegíveis",
    "NO_PAGES": "Sem páginas elegíveis",
}

_QUALITY_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("RASAi Quality · derivado · non-scoring", "RASAi Quality · derivado · sem impacto na pontuação"),
    ("Findings acionáveis", "Achados acionáveis"),
    ("Audit health", "Saúde da auditoria"),
    ("Findings", "Achados"),
    ("Evidence HIGH", "Evidência com confiança alta"),
    ("Quality não é um novo score de readiness.", "Quality não é uma nova pontuação de readiness."),
    (
        "Audit Health descreve a qualidade/completude da coleta; Evidence Confidence descreve a força da evidência de cada finding; Operational Priority é uma heurística de decisão independente; nenhum deles recalcula SARI.",
        "Saúde da auditoria descreve a qualidade/completude da coleta; Confiança da evidência descreve a força da evidência de cada achado; Prioridade operacional é uma heurística de decisão independente; nenhum deles recalcula o SARI.",
    ),
    ("<div class='kicker'>Audit Health</div>", "<div class='kicker'>Saúde da auditoria</div>"),
    ("<div class='kicker'>Executive decision</div>", "<div class='kicker'>Decisão executiva</div>"),
    ("<div class='kicker'>Evidence Confidence</div>", "<div class='kicker'>Confiança da evidência</div>"),
    ("<div class='kicker'>Coverage Map</div>", "<div class='kicker'>Mapa de cobertura</div>"),
    (
        "<div class='kicker'>Search & AI content controls</div>",
        "<div class='kicker'>Controles de conteúdo para Search e IA</div>",
    ),
    (
        "<div class='kicker'>Recommendation Validation</div>",
        "<div class='kicker'>Validação das recomendações</div>",
    ),
    ("<th>Score</th>", "<th>Pontuação</th>"),
    ("<th>Confidence</th>", "<th>Confiança</th>"),
    ("<th>Device</th>", "<th>Dispositivo</th>"),
    ("<th>Technical</th>", "<th>Técnico</th>"),
    ("<th>Rendering</th>", "<th>Renderização</th>"),
    ("<th>Semantic/entity</th>", "<th>Semântica/entidade</th>"),
    ("<th>Answer/evidence/intent</th>", "<th>Resposta/evidência/intenção</th>"),
    ("<th>Governance</th>", "<th>Governança</th>"),
    ("Somente findings ", "Somente achados "),
    ("findings históricos/resolvidos", "achados históricos/resolvidos"),
    ("decisões do publisher", "decisões do publicador"),
    ("não altera scoring", "não altera a pontuação"),
)

_AI_VISIBILITY_OLD = (
    "Nenhum dataset/import observacional de visibilidade generativa foi materializado nesta auditoria. "
    "Esta superfície é import-first e não chama LLM para fabricar observações."
)
_AI_VISIBILITY_NEW = (
    "Nenhuma observação de visibilidade em IA foi importada ou coletada para esta auditoria. "
    "O uso dos provedores de IA durante a auditoria não gera, por si só, dados de visibilidade observada. "
    "Google Search Console convencional alimenta métricas próprias; esta superfície depende de "
    "importação/observação generativa compatível."
)

_AGENTIC_UNAVAILABLE_RE = re.compile(
    r"(<div class='metric lighthouse-score-unavailable'[^>]*>"
    r"<small>Agentic Browsing · Lighthouse experimental</small><strong>)"
    r".*?"
    r"(</strong></div>)",
    flags=re.IGNORECASE | re.DOTALL,
)
_AGENTIC_PUBLIC_MESSAGE = (
    "Não disponibilizado pela API pública PageSpeed Insights v5 usada nesta coleta · "
    "<a href='https://developers.google.com/speed/docs/insights/rest/v5/pagespeedapi/runpagespeed' "
    "target='_blank' rel='noopener'>contrato oficial</a>"
)


def _install_public_state_labels() -> None:
    from rasai import report_presentation as presentation

    presentation._PUBLIC_LABELS.update(_PUBLIC_STATE_LABELS)
    presentation._PUBLIC_TOKEN_RE = re.compile(
        r"(?<![A-Z0-9_])(" 
        + "|".join(
            re.escape(value)
            for value in sorted(presentation._PUBLIC_LABELS, key=len, reverse=True)
        )
        + r")(?![A-Z0-9_])"
    )


def _normalize_navigation_open_state(html: str) -> str:
    """Keep only the navigation group containing the active page expanded."""

    def replace(match: re.Match[str]) -> str:
        attrs = _OPEN_ATTR_RE.sub("", match.group("attrs")).rstrip()
        body = match.group("body")
        if _ACTIVE_LINK_RE.search(body):
            attrs += " open"
        return f"<details{attrs}>{body}</details>"

    return _NAV_GROUP_RE.sub(replace, html)


def _install_navigation_policy() -> None:
    from rasai import report_navigation

    original = report_navigation.render_report_navigation
    if getattr(original, "_rasai_public_ux_guard", False):
        return

    def render_with_active_group_only(*args: Any, **kwargs: Any) -> str:
        return _normalize_navigation_open_state(original(*args, **kwargs))

    render_with_active_group_only._rasai_public_ux_guard = True
    render_with_active_group_only._rasai_original = original
    report_navigation.render_report_navigation = render_with_active_group_only


def _canonical_quality_shell(nav: str, body: str) -> str:
    from rasai.report_presentation import humanize_report_html

    if not nav:
        raise ValueError("canonical quality shell requires report navigation")
    html = (
        "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>RASAi Quality</title><link rel='stylesheet' href='css/site.css'></head>"
        "<body><div class='app-shell'>"
        + nav
        + "<main class='app-main'>"
        + body
        + "</main></div></body></html>"
    )
    return humanize_report_html(html, page_name="quality.html")


def _localize_quality_html(html: str) -> str:
    for old, new in _QUALITY_REPLACEMENTS:
        html = html.replace(old, new)
    # Shared report CSS styles metric labels through <small>, not the historical
    # private Quality <span>. Limit the rewrite to the canonical metric structure.
    html = html.replace("<div class='metric'><span>", "<div class='metric'><small>")
    html = html.replace("</span><strong>", "</small><strong>")
    return html


def _rewrite_file(path: Path, transform: Callable[[str], str]) -> None:
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return
    updated = transform(html)
    if updated == html:
        return
    try:
        path.write_text(updated, encoding="utf-8", newline="\n")
    except OSError:
        return


def _install_quality_report_policy() -> None:
    from rasai.quality import reporting

    original_shell = reporting._shell
    if getattr(reporting, "_rasai_public_ux_guard", False):
        return

    def shell_with_canonical_site(nav: str, body: str) -> str:
        if not nav:
            return original_shell(nav, body)
        return _canonical_quality_shell(nav, body)

    original_write = reporting.write_quality_report

    def write_quality_report_with_public_ux(*args: Any, **kwargs: Any) -> Path:
        path = original_write(*args, **kwargs)
        _rewrite_file(path, _localize_quality_html)
        return path

    reporting._shell = shell_with_canonical_site
    reporting.write_quality_report = write_quality_report_with_public_ux
    reporting._rasai_public_ux_guard = True

    # Direct quality CLI may already have imported the writer by value.
    quality_cli = sys.modules.get("rasai.quality.cli")
    if quality_cli is not None and getattr(quality_cli, "write_quality_report", None) is original_write:
        quality_cli.write_quality_report = write_quality_report_with_public_ux


def _relocate_fulfillment_banner(html: str) -> str:
    match = _FULFILLMENT_BANNER_RE.search(html)
    if match is None:
        return html
    banner = match.group(0)
    without = html[: match.start()] + html[match.end() :]
    main = _MAIN_RE.search(without)
    if main is None:
        return html
    return without[: main.end()] + banner + without[main.end() :]


def _normalize_agentic_browsing(html: str) -> str:
    return _AGENTIC_UNAVAILABLE_RE.sub(
        lambda match: match.group(1) + _AGENTIC_PUBLIC_MESSAGE + match.group(2),
        html,
        count=1,
    )


def _finalize_report_file(path: Path) -> None:
    from rasai.report_presentation import humanize_report_html

    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return

    html = _relocate_fulfillment_banner(html)
    if path.name == "ai-visibility.html":
        html = html.replace(_AI_VISIBILITY_OLD, _AI_VISIBILITY_NEW)
    elif path.name == "web-performance.html":
        html = _normalize_agentic_browsing(html)

    html = humanize_report_html(html, page_name=path.name)
    try:
        path.write_text(html, encoding="utf-8", newline="\n")
    except OSError:
        return


def _finalize_report_directory(report_dir: Path) -> None:
    if not report_dir.is_dir():
        return
    for path in sorted(report_dir.glob("*.html")):
        _finalize_report_file(path)


def _strip_reader_blocks(html: str) -> str:
    html = _READER_STATUS_RE.sub("", html, count=1)
    html = _READER_PATH_RE.sub("", html, count=1)
    html = _READER_TRIGGER_RE.sub("", html, count=1)
    html = _READER_DIALOG_RE.sub("", html, count=1)
    return html


def _refresh_reader_experience(*, workspace: Any, audit_id: str) -> None:
    """Reproject reader status after the canonical fulfillment state is final."""
    from rasai.report_reader_experience import build_report_experience_context, enhance_report_experience

    report_dir = Path(workspace.root) / "report"
    if not report_dir.is_dir():
        return
    try:
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            context = build_report_experience_context(connection, audit_id)
        finally:
            connection.close()
    except sqlite3.Error:
        return

    for path in sorted(report_dir.glob("*.html")):
        try:
            html = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        stripped = _strip_reader_blocks(html)
        rendered = enhance_report_experience(stripped, filename=path.name, context=context)
        if rendered == html:
            continue
        try:
            path.write_text(rendered, encoding="utf-8", newline="\n")
        except OSError:
            continue


def _install_fulfillment_projection_policy() -> None:
    from rasai import audit_fulfillment

    original = audit_fulfillment.project_report_validity
    if getattr(original, "_rasai_public_ux_guard", False):
        return

    def project_report_validity_with_public_ux(*args: Any, **kwargs: Any):
        summary = original(*args, **kwargs)
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        if workspace is not None:
            _finalize_report_directory(Path(workspace.root) / "report")
            if audit_id:
                _refresh_reader_experience(workspace=workspace, audit_id=audit_id)
        return summary

    project_report_validity_with_public_ux._rasai_public_ux_guard = True
    project_report_validity_with_public_ux._rasai_original = original
    audit_fulfillment.project_report_validity = project_report_validity_with_public_ux

    # Recovery/reconciliation modules may have imported the function by value before
    # this guard is installed. Update only references that still point to the exact original.
    for module_name in (
        "rasai.audit_fulfillment_runtime",
        "rasai.audit_reprocess",
        "rasai.core_reprocessing",
        "rasai.core_reprocessing_context",
        "rasai.fulfillment_execution_contract",
    ):
        module = sys.modules.get(module_name)
        if module is not None and getattr(module, "project_report_validity", None) is original:
            module.project_report_validity = project_report_validity_with_public_ux


def install() -> None:
    """Install the final public HTML presentation contract once."""

    global _INSTALLED
    if _INSTALLED:
        return
    _install_public_state_labels()
    _install_navigation_policy()
    _install_quality_report_policy()
    _install_fulfillment_projection_policy()
    _INSTALLED = True
