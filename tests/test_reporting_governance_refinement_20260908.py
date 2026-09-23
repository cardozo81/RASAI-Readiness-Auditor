from __future__ import annotations

from pathlib import Path

from rasai import report_navigation
from rasai.report_contract import surface_by_id
from rasai.rule_references import references_for

def test_bounded_discovery_rules_have_public_titles_and_heuristic_provenance() -> None:
    assert "BR-GEO-055" in report_navigation._RULE_TOOLTIPS
    assert "BR-GEO-056" in report_navigation._RULE_TOOLTIPS
    assert references_for("BR-GEO-055")[0].basis == "HEURISTIC"
    assert references_for("BR-GEO-056")[0].basis == "HEURISTIC"

def test_scoring_contract_explains_bounded_ai_and_reference_inputs_are_tuple() -> None:
    scoring = surface_by_id("scoring")
    refs = surface_by_id("references")
    assert "BR-GEO-055/056" in scoring.ai_usage
    assert refs.inputs == ("fontes metodológicas e referências públicas",)

def test_scoring_report_materializes_human_rule_criterion_and_group() -> None:
    text = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")
    assert "<th>Critério</th>" in text
    assert "<th>Grupo</th>" in text
    assert "Contribuição efetiva" in text
    assert "_rule_description" in text

def test_all_report_contracts_receive_operational_reading_governance() -> None:
    text = Path("src/rasai/report_registry.py").read_text(encoding="utf-8")
    assert "data-report-reading-governance" in text
    assert "score mede a qualidade do universo avaliado" in text
    assert "Coverage e Confidence medem força/completude da medição" in text
    assert "UNKNOWN não é convertido em FAIL" in text

def test_ruleset_documentation_includes_current_rules_through_060() -> None:
    business = Path("docs/specification/03_BUSINESS_RULES.md").read_text(encoding="utf-8")
    guide = Path("docs/RULES_GUIDE.md").read_text(encoding="utf-8")
    assert "BR-GEO-001..060" in business
    assert "BR-GEO-055" in business and "BR-GEO-056" in business and "BR-GEO-060" in business
    assert "BR-GEO-055 / BR-GEO-056" in guide
    assert "BR-GEO-060" in guide
