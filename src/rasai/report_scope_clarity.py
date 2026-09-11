"""Multi-URL scope disclosures for static report surfaces.

The report must never leave the reader guessing whether a value belongs to one URL,
one device, or the complete audited set. This adapter is projection-only: it adds
explicit scope/aggregation language and does not recalculate any metric.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3
from typing import Any

_MARKER = "data-rasai-scope-disclosure='true'"
_INSTALLED = False


def _observed_scope(workspace: Any, audit_id: str) -> tuple[int, tuple[str, ...]]:
    connection = sqlite3.connect(workspace.database)
    try:
        pages = int(
            connection.execute(
                "SELECT COUNT(*) FROM pages WHERE audit_id=?", (audit_id,)
            ).fetchone()[0]
        )
        devices = tuple(
            str(row[0]).upper()
            for row in connection.execute(
                "SELECT DISTINCT ps.device FROM page_snapshots ps "
                "JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=? ORDER BY ps.device",
                (audit_id,),
            ).fetchall()
            if row[0]
        )
    finally:
        connection.close()
    return pages, devices


def _note(filename: str, pages: int, devices: tuple[str, ...]) -> str | None:
    device_text = ", ".join(devices) or "sem snapshot persistido"
    common = f"Universo desta auditoria: <strong>{pages} URL(s)</strong>; contexto(s): <strong>{escape(device_text)}</strong>. "
    if filename == "index.html":
        detail = (
            "No dashboard, <strong>SARI-001</strong> é agregado do universo auditado por dispositivo: os pesos dos grupos "
            "são distribuídos entre os escopos/páginas aplicáveis; portanto não é a nota de uma URL isolada nem uma média "
            "aritmética de scores por página. <strong>Core Web Vitals</strong> mostra contextos aprovados/avaliados. "
            "<strong>Lighthouse Performance, Lighthouse Accessibility e Synthetic Navigation Apdex</strong> mostram a faixa "
            "mínimo a máximo dos contextos válidos quando há mais de um; nenhuma média é criada sem rótulo explícito."
        )
    elif filename == "readiness.html":
        detail = (
            "Os valores SARI/Score desta página são <strong>agregados por dispositivo sobre todas as URLs aplicáveis</strong>. "
            "Dentro de cada scoring group, o peso metodológico é dividido entre os escopos de página aplicáveis para que "
            "aumentar o número de URLs não multiplique artificialmente o peso do grupo. Não é média simples de páginas."
        )
    elif filename in {"web-performance.html", "accessibility.html"}:
        detail = (
            "Observações e tabelas mantêm granularidade <strong>URL x dispositivo</strong>. Resumos com vários contextos usam "
            "contagem ou faixa mínimo a máximo conforme rotulado; filtros/paginação alteram apenas a visualização e não recalculam métricas."
        )
    elif filename == "apdex.html":
        detail = (
            "Cada resumo Apdex pertence a uma <strong>URL x dispositivo</strong> e é calculado a partir da população de amostras "
            "sintéticas daquele contexto. Quando a visão geral resume várias URLs, apresenta faixa entre contextos, não média implícita."
        )
    elif filename == "apdex-experience.html":
        detail = (
            "Cada card de população representa <strong>uma URL</strong>; os grupos Mobile/Desktop/Population permanecem identificados "
            "na tabela. A grade de cards é apenas layout. Nenhuma URL é combinada em média não rotulada."
        )
    elif filename in {"mobile.html", "desktop.html"}:
        detail = (
            "Esta página apresenta evidências/findings do dispositivo indicado mantendo a granularidade por URL. "
            "Scores canônicos agregados permanecem em Search & AI Readiness e não devem ser interpretados como pertencentes à primeira URL exibida."
        )
    elif filename == "context.html":
        detail = (
            "Contextos de aquisição são apresentados por URL/dispositivo. Valores globais ou de origem são identificados separadamente; "
            "não assuma que um dado sem URL visível pertence à primeira página da lista."
        )
    else:
        return None
    return (
        f"<section class='notice' {_MARKER}><strong>Escopo e agregação:</strong> "
        + common
        + detail
        + "</section>"
    )


def enrich_report_scope_clarity(*, audit_id: str, workspace: Any) -> None:
    report_dir = Path(workspace.root) / "report"
    pages, devices = _observed_scope(workspace, audit_id)
    for filename in (
        "index.html",
        "readiness.html",
        "web-performance.html",
        "accessibility.html",
        "apdex.html",
        "apdex-experience.html",
        "mobile.html",
        "desktop.html",
        "context.html",
    ):
        path = report_dir / filename
        if not path.is_file():
            continue
        html = path.read_text(encoding="utf-8")
        if _MARKER in html:
            continue
        note = _note(filename, pages, devices)
        if not note:
            continue
        if "</header>" in html:
            html = html.replace("</header>", "</header>" + note, 1)
        elif "<main" in html:
            close = html.find(">", html.find("<main"))
            if close >= 0:
                html = html[: close + 1] + note + html[close + 1 :]
            else:
                html += note
        else:
            html += note
        path.write_text(html, encoding="utf-8", newline="\n")


def install() -> None:
    """Install scope disclosure after the canonical report completion wrapper."""
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import report_completion
    from rasai.report_manifest import write_report_manifest

    original = report_completion.finalize_audit_report_site

    def finalize_with_scope(*, audit_id: str, workspace: Any, **kwargs: Any):
        base = original(audit_id=audit_id, workspace=workspace, **kwargs)
        errors = list(base.renderer_errors)
        try:
            enrich_report_scope_clarity(audit_id=audit_id, workspace=workspace)
            write_report_manifest(Path(workspace.root) / "report")
        except Exception as exc:  # report projection must remain fail-open
            errors.append(f"scope-clarity:{type(exc).__name__}:{str(exc)[:240]}")
        inspected = report_completion.inspect_audit_report_site(
            audit_id=audit_id, workspace=workspace
        )
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_scope
    _INSTALLED = True
