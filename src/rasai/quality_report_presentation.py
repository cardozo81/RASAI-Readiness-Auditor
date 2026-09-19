"""Presentation policy for the standalone quality report."""
from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable

_INSTALLED = False

_QUALITY_REPLACEMENTS = (
    ("<th>Dimension</th>", "<th>Dimensão</th>"),
    ("<th>Status</th>", "<th>Estado</th>"),
    ("<th>Observed</th>", "<th>Observado</th>"),
    ("<th>Expected</th>", "<th>Esperado</th>"),
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
