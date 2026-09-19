"""Presentation policy for the standalone quality report."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable

_INSTALLED = False

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


def _canonical_quality_shell(nav: str, body: str) -> str:
    from rasai.report_presentation import humanize_report_html

    if not nav:
        raise ValueError("quality shell requires navigation")
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


def install() -> None:
    """Install the standalone quality-report presentation policy once."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai.quality import reporting

    original_shell = reporting._shell
    original_write = reporting.write_quality_report
    if getattr(reporting, "_rasai_quality_report_presentation", False):
        _INSTALLED = True
        return

    def shell_with_presentation(nav: str, body: str) -> str:
        if not nav:
            return original_shell(nav, body)
        return _canonical_quality_shell(nav, body)

    def write_quality_report_with_presentation(*args: Any, **kwargs: Any) -> Path:
        path = original_write(*args, **kwargs)
        _rewrite_file(path, _localize_quality_html)
        return path

    reporting._shell = shell_with_presentation
    reporting.write_quality_report = write_quality_report_with_presentation
    reporting._rasai_quality_report_presentation = True

    quality_cli = sys.modules.get("rasai.quality.cli")
    if quality_cli is not None and getattr(quality_cli, "write_quality_report", None) is original_write:
        quality_cli.write_quality_report = write_quality_report_with_presentation

    _INSTALLED = True


__all__ = ["install"]
