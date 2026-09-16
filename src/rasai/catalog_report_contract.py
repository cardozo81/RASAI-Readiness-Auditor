"""Stable navigation contract for the catalog-driven report proposal."""
from __future__ import annotations

from dataclasses import dataclass

from rasai.audit_catalog import CATALOGS


CATALOG_REPORT_CONTRACT_VERSION = "CATALOG-REPORT-002"
CATALOG_REPORT_DIR = "report-catalog"


@dataclass(frozen=True, slots=True)
class CatalogReportPage:
    id: str
    filename: str
    label: str
    group: str
    catalog_id: str | None = None


_BASE_PAGES = (
    CatalogReportPage("overview", "index.html", "Visão geral", "Auditoria"),
    CatalogReportPage("sari", "sari.html", "SARI", "Auditoria"),
)

_CATALOG_PAGES = tuple(
    CatalogReportPage(
        item.id.casefold(),
        f"{item.id.casefold()}.html",
        f"{item.id} · {item.label}",
        "Catálogos",
        item.id,
    )
    for item in CATALOGS
)

_GOVERNANCE_PAGES = (
    CatalogReportPage(
        "capture-context",
        "capture-context.html",
        "Captura e contexto",
        "Governança",
    ),
    CatalogReportPage(
        "execution-evidence",
        "execution-evidence.html",
        "Evidências da execução",
        "Governança",
    ),
    CatalogReportPage(
        "ai-integrations",
        "ai-integrations.html",
        "IA e integrações",
        "Governança",
    ),
    CatalogReportPage(
        "methodology",
        "methodology.html",
        "Metodologia e scoring",
        "Governança",
    ),
    CatalogReportPage(
        "metrics",
        "metrics.html",
        "Índices e métricas",
        "Governança",
    ),
)

CATALOG_REPORT_PAGES = _BASE_PAGES + _CATALOG_PAGES + _GOVERNANCE_PAGES
CATALOG_REPORT_FILENAMES = tuple(page.filename for page in CATALOG_REPORT_PAGES)
CATALOG_PAGE_BY_ID = {
    page.catalog_id: page for page in CATALOG_REPORT_PAGES if page.catalog_id is not None
}
CATALOG_REPORT_NAV_ITEMS = tuple((page.label, page.filename) for page in CATALOG_REPORT_PAGES)


def page_by_filename(filename: str) -> CatalogReportPage:
    for page in CATALOG_REPORT_PAGES:
        if page.filename == filename:
            return page
    raise KeyError(filename)
