from __future__ import annotations


def test_ai_schemas_require_current_degradation_and_expected_benefit() -> None:
    from rasai import improvement_intelligence, m20_ai, provider_extensions_m20

    improvement_schema = improvement_intelligence._schema(
        [{"finding_id": "F1", "evidence_ids": ["E1"]}],
        5,
    )
    improvement_item = improvement_schema["properties"]["recommendations"]["items"]
    assert "current_degradation" in improvement_item["required"]
    assert "expected_benefit" in improvement_item["required"]
    assert improvement_item["properties"]["current_degradation"]["minLength"] == 1
    assert improvement_item["properties"]["expected_benefit"]["minLength"] == 1

    content_schema = m20_ai.content_remediation_schema()
    content_item = content_schema["properties"]["suggestions"]["items"]
    assert "current_degradation" in content_item["required"]
    assert "expected_benefit" in content_item["required"]

    provider_schema = provider_extensions_m20.content_remediation_schema()
    provider_item = provider_schema["properties"]["suggestions"]["items"]
    assert "current_degradation" in provider_item["required"]
    assert "expected_benefit" in provider_item["required"]
