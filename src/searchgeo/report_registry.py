"""Canonical report navigation registry for all current RASAI report surfaces.

The legacy report_navigation module owns rendering/polish. This registry only
installs the complete ordered catalogue so an optional report generated later
cannot accidentally remove links to previously materialized optional pages.
Items remain conditional because report_navigation.available_navigation only
renders files that actually exist (or the current page).
"""
from __future__ import annotations

CANONICAL_NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("Visão geral", "index.html"),
    ("Readiness SARI", "readiness.html"),
    ("SCORE-GEO-003", "score-geo-003.html"),
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


def install() -> None:
    """Install the current catalogue and scoring-integrity tooltip idempotently."""
    from searchgeo import report_navigation

    report_navigation.NAV_ITEMS = CANONICAL_NAV_ITEMS
    report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = (
        "Integridade do auditor · Verifica a reprodutibilidade do scoring persistido; "
        "SCORE-GEO-003 é o método vigente e SCORE-GEO-002 permanece apenas histórico."
    )
