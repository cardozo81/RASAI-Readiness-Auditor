"""Canonical report navigation registry for all current RASAi report surfaces.

The report_navigation module owns rendering/polish. This registry installs the
complete ordered catalogue so an optional report generated later cannot
accidentally remove links to previously materialized optional pages. Items remain
conditional because report_navigation.available_navigation only renders files
that actually exist (or the current page).
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3

CANONICAL_NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("Visão geral", "index.html"),
    ("Readiness SARI", "readiness.html"),
    ("SCORE-GEO-004", "score-geo-004.html"),
    ("Relatório Mobile", "mobile.html"),
    ("Relatório Desktop", "desktop.html"),
    ("Remediações", "remediation.html"),
    ("Conteúdo e JSON-LD", "content-suggestions.html"),
    ("Rastreamento e descoberta", "crawling-discovery.html"),
    ("Acessibilidade", "accessibility.html"),
    ("Web Performance", "web-performance.html"),
    ("Apdex de navegação", "apdex.html"),
    ("Apdex de experiência", "apdex-experience.html"),
    ("Visibilidade em IA", "ai-visibility.html"),
    ("Search & AI observados", "observability.html"),
    ("Quality & decisão", "quality.html"),
    ("Uso de IA", "ai-usage.html"),
    ("Referências e metodologia", "references.html"),
)


def _ensure_single_filename(label: str, filename: str) -> None:
    """Keep exactly one navigation entry for a report filename."""
    from rasai import report_navigation

    items: list[tuple[str, str]] = []
    inserted = False
    for current_label, current_filename in report_navigation.NAV_ITEMS:
        if current_filename == filename:
            if not inserted:
                items.append((label, filename))
                inserted = True
            continue
        items.append((current_label, current_filename))
    if not inserted:
        canonical_index = next(
            (index for index, item in enumerate(CANONICAL_NAV_ITEMS) if item[1] == filename),
            len(items),
        )
        before = {item[1] for item in CANONICAL_NAV_ITEMS[:canonical_index]}
        insertion = 0
        for index, item in enumerate(items):
            if item[1] in before:
                insertion = index + 1
        items.insert(insertion, (label, filename))
    report_navigation.NAV_ITEMS = tuple(items)


def _patch_apdex_navigation() -> None:
    from rasai import m23_reporting, m25_reporting

    def register_navigation_apdex() -> None:
        _ensure_single_filename("Apdex de navegação", "apdex.html")

    def register_navigation_experience() -> None:
        _ensure_single_filename("Apdex de experiência", "apdex-experience.html")

    m23_reporting._register_apdex_navigation = register_navigation_apdex
    m25_reporting._register_navigation = register_navigation_experience


def _patch_lighthouse_traceability_message() -> None:
    from rasai import m23_reporting
    from rasai.report_presentation import public_label

    if getattr(m23_reporting, "_rasai_lighthouse_state_patch", False):
        return

    original_load = m23_reporting._load
    original_page = m23_reporting._page

    def load_with_web_run(audit_id, workspace):
        data = original_load(audit_id, workspace)
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            try:
                web_run = connection.execute(
                    "SELECT * FROM web_performance_runs WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                web_run = None
        finally:
            connection.close()
        data["web_run"] = web_run
        return data

    def lighthouse_message(data) -> str:
        if data.get("profiles"):
            return ""
        run = data.get("web_run")
        if run is None:
            return "Não disponível nesta execução: não existe estado persistido de Web Performance/Lighthouse."
        if not bool(run["enabled"]):
            return (
                "Não aplicável nesta execução: Web Performance externo estava desabilitado, "
                "portanto nenhum lighthouseResult.configSettings foi coletado."
            )
        status = public_label(str(run["status"] or "INDEFINIDO"))
        reason = str(run["reason"] or "").strip()
        suffix = f" Motivo persistido: {reason}." if reason else ""
        return (
            f"Nenhum configSettings Lighthouse utilizável foi persistido. Estado Web Performance: {status}."
            f"{suffix} Consulte Web Performance e o log operacional para a tentativa PageSpeed/Lighthouse."
        )

    def page_with_lighthouse_state(data, report_dir):
        html = original_page(data, report_dir)
        message = lighthouse_message(data)
        if message:
            html = html.replace(
                "Nenhum configSettings Lighthouse disponível.",
                escape(message),
                1,
            )
        return html

    m23_reporting._load = load_with_web_run
    m23_reporting._page = page_with_lighthouse_state
    m23_reporting._rasai_lighthouse_state_patch = True


def _patch_current_scoring_projection() -> None:
    """Keep public SARI projection aligned with the current runtime version."""
    from rasai import rasai_readiness_reporting

    rasai_readiness_reporting.COMPATIBLE_ENGINE_VERSION = "SCORE-GEO-004"


def _patch_final_branding_normalization() -> None:
    """Prevent obsolete public wording from reappearing in generated HTML."""
    from rasai import report_navigation
    from rasai.report_presentation import humanize_report_html

    if getattr(report_navigation, "_rasai_public_wording_patch", False):
        return
    original = report_navigation.normalize_report_navigation

    def normalize_with_current_wording(report_dir):
        result = original(report_dir)
        root = Path(report_dir)
        for path in root.glob("*.html"):
            try:
                html = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            updated = html.replace("Search/AI", "Search & AI")
            updated = updated.replace("SCORE-GEO-003", "SCORE-GEO-004")
            updated = updated.replace("SCORE-GEO-002", "SCORE-GEO-004")
            updated = updated.replace(
                "Média simples das dimensões aplicáveis suficientemente consolidadas. Dimensão legitimamente NOT_APPLICABLE não recebe zero.",
                "Média de igual peso das dimensões aplicáveis com medição suficiente. Dimensão legitimamente NOT_APPLICABLE sai do denominador e não recebe zero.",
            )
            updated = updated.replace(
                "Compatibilidade metodológica:",
                "Contrato metodológico:",
            )
            updated = updated.replace(
                "esta mudança de relatório não recalcula auditorias, não altera pesos e não quebra comparabilidade histórica.",
                "o resultado é calculado e persistido pelo contrato vigente desta auditoria.",
            )
            updated = updated.replace("—", "-").replace("–", "-")
            updated = humanize_report_html(updated, page_name=path.name)
            if updated != html:
                try:
                    path.write_text(updated, encoding="utf-8", newline="\n")
                except OSError:
                    continue
        return result

    report_navigation.normalize_report_navigation = normalize_with_current_wording
    report_navigation._rasai_public_wording_patch = True


def install() -> None:
    """Install the current catalogue and report consistency adapters idempotently."""
    from rasai import report_navigation

    report_navigation.NAV_ITEMS = CANONICAL_NAV_ITEMS
    report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = (
        "Integridade do auditor - verifica a reprodutibilidade do scoring persistido; "
        "SCORE-GEO-004 é o método vigente e não depende de artifact de calibração."
    )
    _patch_apdex_navigation()
    _patch_lighthouse_traceability_message()
    _patch_current_scoring_projection()
    _patch_final_branding_normalization()
