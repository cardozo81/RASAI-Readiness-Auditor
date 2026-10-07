from __future__ import annotations

from rasai.domain import Finding, FindingDevice, Severity
from rasai.prioritization import PriorityEngine
from rasai.remediation import recipe_for


def _finding(observed_value: object) -> Finding:
    return Finding(
        finding_id="FND-253",
        audit_id="AUD-253",
        rule_id="BR-GEO-034",
        rule_execution_id="REX-253",
        page_id="PGE-253",
        device=FindingDevice.DESKTOP,
        category="STRUCTURED_DATA",
        severity=Severity.MEDIUM,
        source="deterministic-rules-engine",
        title="Dados estruturados",
        observed_value=observed_value,
        expected_condition="dados estruturados são sintaticamente interpretáveis quando presentes",
        evidence_ids=("EVD-253",),
        status="OPEN",
    )


def test_br_geo_034_absent_markup_does_not_recommend_syntax_correction() -> None:
    finding = _finding({"blocks": 0, "invalid_blocks": 0, "present": False, "types": []})
    recipe = recipe_for("BR-GEO-034", observed_value=finding.observed_value)
    result = PriorityEngine().prioritize(audit_id="AUD-253", findings=(finding,), total_pages=1)
    recommendation = result.recommendations[0]

    assert recipe.action == "REVIEW_STRUCTURED_DATA_APPLICABILITY"
    assert "não existe sintaxe de bloco existente a corrigir" in recipe.description
    assert "Corrigir sintaxe" not in recommendation.title
    assert "não existe sintaxe de bloco existente a corrigir" in recommendation.description


def test_br_geo_034_present_invalid_markup_keeps_correction_recipe_and_priority_math() -> None:
    absent = _finding({"blocks": 0, "invalid_blocks": 0, "present": False, "types": []})
    invalid = _finding({"blocks": 1, "invalid_blocks": 1, "present": True, "types": []})

    absent_result = PriorityEngine().prioritize(audit_id="AUD-253", findings=(absent,), total_pages=1)
    invalid_result = PriorityEngine().prioritize(audit_id="AUD-253", findings=(invalid,), total_pages=1)
    recipe = recipe_for("BR-GEO-034", observed_value=invalid.observed_value)

    assert recipe.action == "CORRECT_STRUCTURED_DATA"
    assert recipe.title == "Corrigir sintaxe de Dados Estruturados"
    assert invalid_result.recommendations[0].title == "Corrigir sintaxe de Dados Estruturados"
    assert absent_result.groups[0].priority_score == invalid_result.groups[0].priority_score
