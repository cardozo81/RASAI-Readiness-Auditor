from __future__ import annotations

import re

from rasai.audit_catalog import CATALOGS
from rasai.catalog_report_contract import (
    CATALOG_REPORT_DIR,
    CATALOG_REPORT_FILENAMES,
    CATALOG_REPORT_NAV_ITEMS,
    CATALOG_REPORT_PAGES,
    CATALOG_REPORT_CONTRACT_VERSION,
)


_VERSIONED_SCORING_FILE = re.compile(r"score-geo-\d+\.html")


def test_catalog_navigation_is_complete_stable_and_current_only() -> None:
    assert CATALOG_REPORT_DIR == "report-catalog"
    assert CATALOG_REPORT_CONTRACT_VERSION == "CATALOG-REPORT-002"
    assert CATALOG_REPORT_NAV_ITEMS == tuple(
        (page.label, page.filename) for page in CATALOG_REPORT_PAGES
    )
    assert len(CATALOG_REPORT_FILENAMES) == len(set(CATALOG_REPORT_FILENAMES))
    assert CATALOG_REPORT_FILENAMES[0:2] == ("index.html", "sari.html")
    assert tuple(f"{catalog.id.casefold()}.html" for catalog in CATALOGS) == tuple(
        page.filename for page in CATALOG_REPORT_PAGES if page.catalog_id is not None
    )
    assert ("Método de Pontuação de Prontidão", "methodology.html") in CATALOG_REPORT_NAV_ITEMS
    assert not any(_VERSIONED_SCORING_FILE.fullmatch(name) for name in CATALOG_REPORT_FILENAMES)


def test_methodology_surface_is_canonical_and_version_neutral() -> None:
    methodology = next(page for page in CATALOG_REPORT_PAGES if page.id == "methodology")
    assert methodology.filename == "methodology.html"
    assert methodology.group == "Governança"
    assert "004" not in methodology.filename
