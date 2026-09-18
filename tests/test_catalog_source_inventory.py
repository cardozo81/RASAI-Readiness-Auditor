from rasai.catalog_report_catalog_state import _catalog_source_specs


def test_catalog_source_inventory_covers_material_decision_tables() -> None:
    cat03 = {table for table, _label in _catalog_source_specs("CAT-03")}
    assert {
        "semantic_coherence_assessments",
        "semantic_property_signals",
        "property_semantic_summaries",
        "content_context_interpretations",
    }.issubset(cat03)

    cat05 = {table for table, _label in _catalog_source_specs("CAT-05")}
    assert {
        "serp_competitive_analyses",
        "serp_competitive_results",
        "serp_competitive_pages",
        "serp_competitive_ai_analyses",
    }.issubset(cat05)

    cat09 = {table for table, _label in _catalog_source_specs("CAT-09")}
    assert {
        "recommendation_governance",
        "request_remediation_ai",
        "request_remediation_evidence",
        "root_cause_precision",
    }.issubset(cat09)
