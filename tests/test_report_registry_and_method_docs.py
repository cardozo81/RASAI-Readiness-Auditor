from __future__ import annotations

from pathlib import Path
import tempfile

from rasai import report_navigation
from rasai.report_registry import CANONICAL_NAV_ITEMS, install
from rasai.score_geo_004_reporting import LEGACY_REPORT_FILE, REPORT_FILE


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
        assert ("Metodologia de scoring", "scoring.html") in CANONICAL_NAV_ITEMS
        assert not any(filename == LEGACY_REPORT_FILE for _, filename in CANONICAL_NAV_ITEMS)
        assert "SCORE-GEO-004" in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
        assert "SCORE-GEO-003" not in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
        assert "SCORE-GEO-002" not in report_navigation._RULE_TOOLTIPS["BR-GEO-054"]
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
                assert LEGACY_REPORT_FILE not in html
    finally:
        report_navigation.NAV_ITEMS = original_nav
        report_navigation._RULE_TOOLTIPS["BR-GEO-054"] = original_tooltip


def test_prepublication_scoring_report_has_no_versioned_alias() -> None:
    assert REPORT_FILE == "scoring.html"
    assert LEGACY_REPORT_FILE == "score-geo-004.html"
    assert REPORT_FILE != LEGACY_REPORT_FILE
    assert not any(filename == LEGACY_REPORT_FILE for _, filename in CANONICAL_NAV_ITEMS)




def test_current_method_documents_use_score_geo_004_without_declaring_003_current() -> None:
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
    forbidden = (
        "SCORE-GEO-003` é o scoring runtime vigente",
        "SCORE-GEO-003` como método padrão",
        "motor de scoring vigente para novas auditorias é **`SCORE-GEO-003`**",
        "scoring vigente para novas auditorias: `SCORE-GEO-003`",
        "As auditorias usam `SCORE-GEO-003`",
        "score-geo-003.html          # modelo/dataset/gates do scoring vigente",
    )
    for relative in current_docs:
        text = (root / relative).read_text(encoding="utf-8")
        assert "SCORE-GEO-004" in text, f"current scoring version missing from {relative}"
        for phrase in forbidden:
            assert phrase not in text, f"stale current-method wording in {relative}: {phrase}"


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
