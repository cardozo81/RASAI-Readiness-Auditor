from pathlib import Path
import tempfile
import tomllib

from searchgeo.branding import (
    CANONICAL_READINESS_REPORT,
    LEGACY_PUBLIC_INDEX_VERSION,
    LEGACY_READINESS_REPORT,
    PRODUCT_DISPLAY_NAME,
    PUBLIC_INDEX_VERSION,
)
from searchgeo.searchgeo_readiness_reporting import (
    COMPATIBLE_ENGINE_VERSION,
    PUBLIC_METHOD_VERSION,
    SEARCHGEO_FILE,
    _legacy_readiness_redirect,
)


def test_public_branding_contract() -> None:
    assert PRODUCT_DISPLAY_NAME == "RASAi — Search & AI Readiness Auditor"
    assert PUBLIC_INDEX_VERSION == "SARI-001"
    assert LEGACY_PUBLIC_INDEX_VERSION == "SGRI-001"
    assert CANONICAL_READINESS_REPORT == "readiness.html"
    assert LEGACY_READINESS_REPORT == "searchgeo.html"
    assert PUBLIC_METHOD_VERSION == "SARI-001"
    assert COMPATIBLE_ENGINE_VERSION == "SCORE-GEO-003"
    assert SEARCHGEO_FILE == "readiness.html"


def test_legacy_report_alias_redirects_to_canonical_readiness() -> None:
    html = _legacy_readiness_redirect()
    assert "url=readiness.html" in html
    assert "href='readiness.html'" in html


def test_primary_and_legacy_cli_entrypoints_coexist() -> None:
    scripts = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert scripts["rasai"] == scripts["searchgeo"] == "searchgeo.entrypoint:main"
    assert scripts["rasai-console"] == scripts["searchgeo-console"] == "searchgeo.console_entrypoint:main"


def test_public_documentation_and_legacy_document_coexist() -> None:
    assert Path("docs/SARI_READINESS_INDEX.md").is_file()
    assert Path("docs/SEARCHGEO_READINESS_INDEX.md").is_file()
    assert Path("docs/BRANDING_AND_COMPATIBILITY.md").is_file()
