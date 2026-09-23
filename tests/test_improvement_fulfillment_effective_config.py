from __future__ import annotations

from types import SimpleNamespace

from rasai.selective_optional_reprocess import _effective_improvement_configuration


def test_executed_improvement_run_wins_over_current_environment() -> None:
    item = SimpleNamespace(
        configuration={
            "provider": "OPENAI",
            "model": "gpt-5.6-luna",
            "max_recommendations": 50,
            "language": "auto",
        }
    )
    run = {
        "provider": "OPENAI",
        "model": "gpt-5.6-luna",
        "reasoning": "medium",
        "domains_json": '["CONTENT","ACCESSIBILITY"]',
        "max_recommendations": 30,
        "analysis_language": "pt-BR",
    }
    environment = {
        "RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS": "50",
        "RASAI_IMPROVEMENT_PROVIDER": "OPENAI",
    }
    resolved = _effective_improvement_configuration(item, run, environment)
    assert resolved["max_recommendations"] == 30
    assert resolved["language"] == "pt-BR"
    assert resolved["domains"] == ["CONTENT", "ACCESSIBILITY"]


def test_existing_frozen_configuration_wins_when_no_run_exists() -> None:
    item = SimpleNamespace(
        configuration={
            "max_recommendations": 30,
            "language": "pt-BR",
            "domains": ["CONTENT"],
        }
    )
    resolved = _effective_improvement_configuration(
        item,
        None,
        {"RASAI_IMPROVEMENT_MAX_RECOMMENDATIONS": "50"},
    )
    assert resolved["max_recommendations"] == 30
    assert resolved["language"] == "pt-BR"
    assert resolved["domains"] == ["CONTENT"]
