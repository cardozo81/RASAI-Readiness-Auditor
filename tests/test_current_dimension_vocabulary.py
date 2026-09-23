from __future__ import annotations


def test_equal_weight_identifier_never_reintroduces_old_public_formula() -> None:
    from rasai.report_presentation import public_label

    assert public_label("HIERARCHICAL_WEIGHTED_READINESS_V1") == "Hierarchical Weighted Readiness"
    assert public_label("EQUAL_WEIGHT_APPLICABLE_DIMENSIONS_V1") == "Hierarchical Weighted Readiness"
