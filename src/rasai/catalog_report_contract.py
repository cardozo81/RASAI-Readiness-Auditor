"""Independent contract for the catalog-driven HTML report experiment.

The current public report generator keeps owning ``report/``.  This contract owns only
``report-catalog/`` so both report generations can coexist until the catalog proposal is
validated.  Keeping navigation here gives every new page one shared, ordered menu.
"""
from __future__ import annotations

from dataclasses import dataclass

CATALOG_REPORT_DIR = "report-catalog"
CATALOG_REPORT_CONTRACT_VERSION = "CATALOG-REPORT-001"


@dataclass(frozen=True, slots=True)
class CatalogReportPage:
    id: str
    filename: str
    label: str
    group: str
    catalog_id: str | None = None


CATALOG_REPORT_PAGES: tuple[CatalogReportPage, ...] = (
    CatalogReportPage("overview", "index.html", "Visão geral", "Auditoria"),
    CatalogReportPage("sari", "sari.html", "SARI", "Auditoria"),
    CatalogReportPage("cat-01", "cat-01.html", "CAT-01 · Fundamentos técnicos e descoberta", "Catálogos", "CAT-01"),
    CatalogReportPage("cat-02", "cat-02.html", "CAT-02 · Acessibilidade", "Catálogos", "CAT-02"),
    CatalogReportPage("cat-03", "cat-03.html", "CAT-03 · Conteúdo, semântica e dados estruturados", "Catálogos", "CAT-03"),
    CatalogReportPage("cat-04", "cat-04.html", "CAT-04 · Web Performance", "Catálogos", "CAT-04"),
    CatalogReportPage("cat-05", "cat-05.html", "CAT-05 · Search & AI Intelligence", "Catálogos", "CAT-05"),
    CatalogReportPage("cat-06", "cat-06.html", "CAT-06 · Apdex de navegação", "Catálogos", "CAT-06"),
    CatalogReportPage("cat-07", "cat-07.html", "CAT-07 · Apdex de experiência", "Catálogos", "CAT-07"),
    CatalogReportPage("cat-08", "cat-08.html", "CAT-08 · Análise profunda e melhorias", "Catálogos", "CAT-08"),
    CatalogReportPage("cat-09", "cat-09.html", "CAT-09 · Remediações", "Catálogos", "CAT-09"),
    CatalogReportPage("execution-evidence", "execution-evidence.html", "Evidências da execução", "Governança"),
    CatalogReportPage("ai-integrations", "ai-integrations.html", "IA e integrações", "Governança"),
    CatalogReportPage("methodology", "methodology.html", "Metodologia e scoring", "Governança"),
    CatalogReportPage("metrics", "metrics.html", "Índices e métricas", "Governança"),
)

CATALOG_PAGE_BY_ID = {
    page.catalog_id: page for page in CATALOG_REPORT_PAGES if page.catalog_id is not None
}
CATALOG_REPORT_FILENAMES = tuple(page.filename for page in CATALOG_REPORT_PAGES)
CATALOG_REPORT_NAV_ITEMS = tuple((page.label, page.filename) for page in CATALOG_REPORT_PAGES)


def page_by_filename(filename: str) -> CatalogReportPage:
    for page in CATALOG_REPORT_PAGES:
        if page.filename == filename:
            return page
    raise KeyError(filename)
