from __future__ import annotations

from pathlib import Path
import re
import tempfile

from rasai import report_navigation
from rasai.report_registry import CANONICAL_NAV_ITEMS, install
from rasai.score_geo_004_reporting import REPORT_FILE


_VERSIONED_SCORING_FILE = re.compile(r"score-geo-\d+\.html")
_OLD_SCORING_VERSION = re.compile(r"SCORE-GEO-00[123]")


def _page(title: str) -> str:
    return (
        "<!doctype html><html><body>"
        "<aside class='app-nav'><nav><a href='index.html'>old</a></nav></aside>"
        f"<main class='app-main'><header class='hero'><h1>{title}</h1></header>"
        "<footer class='footer'>footer</footer></main></body></html>"
    )


def test_optional_report_navigation_is_complete_stable_and_current_only() -> None:
    original_nav = report_navigation.NAV_ITEMS
    original_tooltip = report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
    try:
        install()
        assert report_navigation.NAV_ITEMS == CANONICAL_NAV_ITEMS
        assert ("Metodologia de scoring", "scoring.html") in CANONICAL_NAV_ITEMS
        assert not any(_VERSIONED_SCORING_FILE.fullmatch(filename) for _, filename in CANONICAL_NAV_ITEMS)
        assert "SCORE-GEO-004" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
        assert not _OLD_SCORING_VERSION.search(report_navigation._RULE_TOOLTIPS["BR-GEO-054"])
        assert "histórico" not in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]

        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "css").mkdir()
            (report_dir / "css" / "site.css").write_text("body{}", encoding="utf-8")
            materialized = (
                "index.html",
                "readiness.html",
                "scoring.html",
                "crawling-discovery.html",
                "apdex.html",
                "apdex-experience.html",
                "ai-visibility.html",
                "observability.html",
                "ai-usage.html",
                "references.html",
            )
            for name in materialized:
                (report_dir / name).write_text(_page(name), encoding="utf-8")

            report_navigation.normalize_report_navigation(report_dir)

            expected_order = [
                filename for _label, filename in CANONICAL_NAV_ITEMS if filename in materialized
            ]
            for current in materialized:
                html = (report_dir / current).read_text(encoding="utf-8")
                positions = [html.index(f"href='{name}'") for name in expected_order]
                assert positions == sorted(positions)
                assert html.count("class='active'") == 1
                assert f"class='active' href='{current}'" in html
                assert "mobile.html" not in html
                assert "desktop.html" not in html
                assert not _VERSIONED_SCORING_FILE.search(html)
    finally:
        report_navigation.NAV_ITEMS = original_nav
        report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = original_tooltip


def test_prepublication_scoring_report_has_only_canonical_surface() -> None:
    assert REPORT_FILE == "scoring.html"
    assert not _VERSIONED_SCORING_FILE.fullmatch(REPORT_FILE)
    assert not any(_VERSIONED_SCORING_FILE.fullmatch(filename) for _, filename in CANONICAL_NAV_ITEMS)


def test_current_method_documents_expose_only_score_geo_004() -> None:
    root = Path(__file__).resolve().parents[1]
    current_docs = (
        "README.md",
        "docs/SCORING_GUIDE.md",
        "docs/SCORE_GEO_004.md",
        "docs/SARI_READINESS_INDEX.md",
        "docs/CONSOLIDATED_REPORTING.md",
        "docs/RULES_GUIDE.md",
        "docs/REPORT_GUIDE.md",
        "docs/OUTPUTS_AND_ARTIFACTS.md",
        "docs/CLI_REFERENCE.md",
        "docs/specification/00_SPEC_INDEX.md",
        "docs/specification/05_SCORING_MODEL.md",
        "docs/specification/12_AI_HANDOFF.md",
    )
    for relative in current_docs:
        text = (root / relative).read_text(encoding="utf-8")
        assert "SCORE-GEO-004" in text, f"current scoring version missing from {relative}"
        assert not _OLD_SCORING_VERSION.search(text), f"obsolete scoring version exposed in {relative}"


def test_current_report_docs_use_stable_scoring_filename() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative in (
        "README.md",
        "docs/SCORING_GUIDE.md",
        "docs/SCORE_GEO_004.md",
        "docs/SARI_READINESS_INDEX.md",
        "docs/REPORT_GUIDE.md",
        "docs/OUTPUTS_AND_ARTIFACTS.md",
        "docs/CLI_REFERENCE.md",
        "docs/specification/00_SPEC_INDEX.md",
        "docs/specification/05_SCORING_MODEL.md",
        "docs/specification/12_AI_HANDOFF.md",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "scoring.html" in text, f"stable scoring report path missing from {relative}"
        assert not _VERSIONED_SCORING_FILE.search(text), f"versioned scoring report path exposed in {relative}"
