from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai import console_execution_profiles as profiles
from rasai.console_execution_profile_readiness import install, profile_status


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        input_mode="url",
        target="https://example.com/",
        ai_provider="none",
        ai_model=None,
        ai_reasoning=None,
        runtime_blocks={},
        web_performance=False,
        lighthouse_categories="",
        content_remediation=False,
        technical_remediation=False,
        synthetic_apdex=False,
        apdex_experience=False,
        search_queries=(),
        search_depth=20,
        search_device="mobile",
        improvement_enabled=False,
        improvement_domains=("CONTENT",),
        improvement_max_recommendations=30,
        improvement_timeout=240.0,
        error="",
        operation="",
    )


def test_install_adds_complete_maximum_with_every_module() -> None:
    install()
    definition = profiles._PROFILE_BY_ID["complete-maximum"]
    assert definition.label == "Completo máximo"
    assert definition.modules == tuple(item.id for item in profiles.MODULES)


def test_complete_maximum_exposes_missing_dependencies_before_selection() -> None:
    install()
    ready, blockers, _ = profile_status(_state(), "complete-maximum")
    rendered = " | ".join(blockers).casefold()
    assert ready is False
    assert "termos" in rendered
    assert "apdex" in rendered
    assert "item 13" in rendered


def test_search_profile_validates_provider_contract_not_only_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    install()
    state = _state()
    state.search_queries = ("rasai",)
    monkeypatch.setenv("RASAI_SERP_MODE", "disabled")
    ready, blockers, _ = profile_status(state, "search-intelligence")
    assert ready is False
    assert any("disabled" in item.casefold() for item in blockers)


def test_deep_profile_with_missing_primary_ai_is_ready_with_closure_limitation() -> None:
    install()
    state = _state()
    state.improvement_enabled = True
    ready, blockers, advisories = profile_status(state, "deep-analysis")
    assert ready is True
    assert blockers == ()
    assert any("pendente" in item.casefold() for item in advisories)


def test_blocked_complete_maximum_remains_visible_but_is_not_selected(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install()
    state = _state()
    profiles.clear_profile(state)
    maximum_index = next(
        index for index, item in enumerate(profiles.PROFILES, 1) if item.id == "complete-maximum"
    )
    answers = iter((str(maximum_index), "V"))
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    profiles.configure_profile(state)

    output = capsys.readouterr().out
    assert "Completo máximo" in output
    assert "CONFIGURAR" in output
    assert "ainda não pode ser selecionado" in output
    assert profiles.active_profile(state) is None
