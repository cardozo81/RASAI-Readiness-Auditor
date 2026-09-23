from __future__ import annotations

from pathlib import Path

import pytest

from rasai.ai_efficiency_policy import install as install_ai_efficiency_policy


ROOT = Path(__file__).resolve().parents[1]


def _install() -> None:
    install_ai_efficiency_policy()


def test_search_competitive_uses_canonical_provider_choices() -> None:
    _install()
    from rasai.provider_registry import cli_provider_choices
    from rasai.search_intelligence.cli import build_parser

    parser = build_parser()
    action = next(item for item in parser._actions if item.dest == "ai_provider")
    choices = set(action.choices or ())
    assert set(cli_provider_choices()).issubset(choices)
    assert "auto" in choices
    assert "fixture" in choices


def test_search_monitor_accepts_auto_and_rejects_model_override() -> None:
    _install()
    from rasai.search_intelligence.monitoring import SearchMonitorQuery

    base = dict(
        query_id="SQRY-1",
        project_id="PRJ-1",
        property_id="PROP-1",
        environment_id="ENV-1",
        query="rasai",
        domain_of_interest="example.test",
        compare_content=True,
        ai_competitive=True,
        ai_provider="auto",
    )
    item = SearchMonitorQuery(**base)
    assert item.validate() is item
    with pytest.raises(ValueError, match="cannot override AUTO"):
        SearchMonitorQuery(**base, ai_model="forced-model").validate()


def test_improvement_accepts_primary_auto_selection() -> None:
    _install()
    from rasai.improvement_intelligence import ImprovementConfig

    config = ImprovementConfig(enabled=True, provider="auto").validate({})
    assert config.enabled is True
    assert config.provider == "auto"
    assert config.model == ""
    assert config.reasoning == ""


def test_improvement_saas_exposes_only_primary_ai_selection() -> None:
    _install()
    from rasai import audit_execution_contract as contract

    fields = set(contract.AUDIT_JOB_FIELDS)
    assert "ai_provider" in fields
    assert "ai_model" in fields
    assert "ai_reasoning" in fields
    assert "improvement_intelligence" in fields
    assert "improvement_ai_provider" not in fields
    assert "improvement_ai_model" not in fields
    assert "improvement_ai_reasoning" not in fields

    option_names = {item.name for item in contract.audit_job_options()}
    assert "improvement_intelligence" in option_names
    assert "improvement_ai_provider" not in option_names
    assert "improvement_ai_model" not in option_names
    assert "improvement_ai_reasoning" not in option_names


def test_obsolete_feature_local_ai_configuration_is_absent_from_defaults_and_docs() -> None:
    forbidden = (
        "RASAI_SEARCH_AI_PROVIDER",
        "RASAI_IMPROVEMENT_AI_PROVIDER",
        "RASAI_IMPROVEMENT_AI_MODEL",
        "RASAI_IMPROVEMENT_AI_REASONING",
        "improvement_ai_provider",
        "improvement_ai_model",
        "improvement_ai_reasoning",
    )
    files = (
        ROOT / "src/rasai/config/rasai-defaults.ini",
        ROOT / "docs/ENVIRONMENT_VARIABLES.md",
        ROOT / "docs/IMPROVEMENT_INTELLIGENCE.md",
        ROOT / "docs/COMPETITIVE_AI_INTELLIGENCE.md",
    )
    for path in files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token} must not be documented/configured in {path}"
