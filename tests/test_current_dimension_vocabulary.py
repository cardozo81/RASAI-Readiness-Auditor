from __future__ import annotations


def test_discovery_access_is_the_only_public_discovery_dimension() -> None:
    from rasai import (
        m15_reporting,
        report_presentation,
        report_registry,
        report_site,
        reporting,
        score_geo_004_reporting,
    )

    report_registry.install()

    assert m15_reporting._DIMENSION_GUIDE[0][0] == "DISCOVERY_ACCESS"
    assert reporting._CATEGORY_DIMENSION["TECHNICAL_ACCESSIBILITY"] == "DISCOVERY_ACCESS"
    assert reporting._CATEGORY_DIMENSION["DISCOVERY_ACCESS"] == "DISCOVERY_ACCESS"

    assert reporting._DIMENSION_LABELS["DISCOVERY_ACCESS"] == reporting._DIMENSION_LABELS["TECHNICAL_ACCESSIBILITY"]
    assert report_site._DIMENSION_LABELS["DISCOVERY_ACCESS"] == report_site._DIMENSION_LABELS["TECHNICAL_ACCESSIBILITY"]
    assert score_geo_004_reporting._DIMENSION_LABELS["DISCOVERY_ACCESS"] == score_geo_004_reporting._DIMENSION_LABELS["TECHNICAL_ACCESSIBILITY"]

    assert report_presentation.public_label("DISCOVERY_ACCESS") == "Discovery & Crawler Access"
    assert report_presentation.public_label("TECHNICAL_ACCESSIBILITY") == "Discovery & Crawler Access"


def test_equal_weight_identifier_never_reintroduces_old_public_formula() -> None:
    from rasai.report_presentation import public_label

    assert public_label("HIERARCHICAL_WEIGHTED_READINESS_V1") == "Hierarchical Weighted Readiness"
    assert public_label("EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1") == "Hierarchical Weighted Readiness"
