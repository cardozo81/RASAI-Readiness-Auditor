from pathlib import Path


def test_scoring_report_uses_full_width_dimension_panels() -> None:
    source = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")
    assert "class='grid scoring-weight-groups'" not in source
    assert "class='scoring-weight-groups'" in source
    assert "class='scoring-dimension-panel'" in source
    assert "scoring-dimension-table" in source
    assert "overflow-y:visible" in source
    assert "max-height:none!important" in source
    assert "min-width:940px" in source


def test_scoring_report_orders_dimension_panels_by_method_contract() -> None:
    source = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")
    assert "ordered_dimensions = [dimension for dimension in FEATURE_ORDER if dimension in grouped]" in source
    assert "scoring_groups: set[str] = set()" in source
    assert "scoring-dimension-meta" in source


def test_scoring_layout_is_page_scoped() -> None:
    source = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")
    assert "<style>{_SCORING_LAYOUT_CSS}</style>" in source
    report_site = Path("src/rasai/report_site.py").read_text(encoding="utf-8")
    assert ".scoring-dimension-panel" not in report_site
