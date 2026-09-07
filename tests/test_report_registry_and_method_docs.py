from __future__ import annotations

from pathlib import Path
import tempfile

from searchgeo import report_navigation
from searchgeo.report_registry import CANONICAL_NAV_ITEMS, install


def _page(title: str) -> str:
    return (
        "<!doctype html><html><body>"
        "<aside class='app-nav'><nav><a href='index.html'>old</a></nav></aside>"
        f"<main class='app-main'><header class='hero'><h1>{title}</h1></header>"
        "<footer class='footer'>footer</footer></main></body></html>"
    )


def test_optional_report_navigation_is_complete_stable_and_conditional() -> None:
    original_nav = report_navigation.NAV_ITEMS
    original_tooltip = report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
    try:
        install()
        assert report_navigation.NAV_ITEMS == CANONICAL_NAV_ITEMS
        assert "SCORE-GEO-003" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
        assert "SCORE-GEO-002" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
        assert "histórico" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]

        with tempfile.TemporaryDirectory() as directory:
            report_dir = Path(directory)
            (report_dir / "css").mkdir()
            (report_dir / "css" / "site.css").write_text("body{}", encoding="utf-8")
            materialized = (
                "index.html",
                "readiness.html",
                "score-geo-003.html",
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
    finally:
        report_navigation.NAV_ITEMS = original_nav
        report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = original_tooltip


def test_current_method_documents_do_not_restore_score_geo_002_as_current() -> None:
    root = Path(__file__).resolve().parents[1]
    current_docs = (
        "docs/CONSOLIDATED_REPORTING.md",
        "docs/RULES_GUIDE.md",
        "docs/REPORT_GUIDE.md",
        "docs/OUTPUTS_AND_ARTIFACTS.md",
        "docs/MONITORING_OBSERVABILITY.md",
        "docs/specification/00_SPEC_INDEX.md",
        "docs/specification/04_WORKFLOWS.md",
        "docs/specification/08_TECHNICAL_ARCHITECTURE.md",
        "docs/specification/12_AI_HANDOFF.md",
        "docs/specification/18_MULTI_AI_PROVIDER_ROUTING.md",
        "docs/specification/19_SCORE_APPLICABILITY_GEO_MINIMUMS.md",
        "docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md",
        "docs/specification/27_MONITORING_OBSERVABILITY.md",
    )
    forbidden = (
        "Baseline vigente: `SCORE-GEO-002`",
        "O identificador persistido vigente é `SCORE-GEO-002`",
        "O scoring vigente é `SCORE-GEO-002`",
        "scoring vigente é `SCORE-GEO-002`",
        "`SCORE-GEO-002` permanece scoring baseline",
    )
    for relative in current_docs:
        text = (root / relative).read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"stale current-method wording in {relative}: {phrase}"
        assert "SCORE-GEO-003" in text
