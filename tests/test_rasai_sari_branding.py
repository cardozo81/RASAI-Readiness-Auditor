from pathlib import Path
import tomllib

from rasai.branding import (
    CANONICAL_READINESS_REPORT,
    PRODUCT_DISPLAY_NAME,
    PUBLIC_INDEX_VERSION,
)
from rasai.catalog_report_contract import CATALOG_REPORT_DIR
from rasai.score_geo_004 import SCORING_VERSION


def test_public_branding_contract() -> None:
    assert PRODUCT_DISPLAY_NAME == "RASAi - Search & AI Readiness Auditor"
    assert PUBLIC_INDEX_VERSION == "SARI-001"
    assert CANONICAL_READINESS_REPORT == "report-catalog/sari.html"
    assert SCORING_VERSION == "SCORE-GEO-004"
    assert CATALOG_REPORT_DIR == "report-catalog"


def test_primary_cli_entrypoints_are_rasai_only() -> None:
    scripts = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["rasai"] == "rasai.entrypoint:main"
    assert scripts["rasai-console"] == "rasai.console_entrypoint:main"
    assert set(scripts) == {"rasai", "rasai-console"}


def test_public_documentation_uses_current_contract() -> None:
    assert Path("docs/SARI_READINESS_INDEX.md").is_file()
    assert Path("docs/SCORE_GEO_004.md").is_file()
    assert Path("docs/BRANDING.md").is_file()
