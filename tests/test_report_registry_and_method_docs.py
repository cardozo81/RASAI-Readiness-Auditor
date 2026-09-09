from __future__ import annotations

from pathlib import Path
import re
import tempfile

from rasai import report_navigation
from rasai.report_registry import CANONICAL_NAV_ITEMS, install
from rasai.score_geo_004_reporting import REPORT_FILE


_VERSIONED_SCORING_FILE = re.compile(r"score-geo-\d+\.html")
_NON_CANONICAL_SCORING_VERSION = re.compile(r"SCORE-GEO-(?!004)\d{3}")


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
        assert not _NON_CANONICAL_SCORING_VERSION.search(report_navigation._RULE_TOOLTIPS["BR-GEO-054"])
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
            for name in materialized:
                html = (report_dir / name).read_text(encoding="utf-8")
                positions = [html.find(f"href='{filename}'") for filename in expected_order]
                assert all(position >= 0 for position in positions)
                assert positions == sorted(positions)
                assert html.count("class='active'") == 1
                assert "score-geo-004.html" not in html
    finally:
        report_navigation.NAV_ITEMS = original_nav
        report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = original_tooltip


def test_scoring_report_filename_is_canonical_and_not_versioned() -> None:
    assert REPORT_FILE == "scoring.html"
    assert not _VERSIONED_SCORING_FILE.fullmatch(REPORT_FILE)
