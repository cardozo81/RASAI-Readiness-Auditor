from __future__ import annotations

from types import ModuleType

import pytest

from rasai.console_execution_profiles import (
    AI_OFF,
    clear_profile,
    dependency_status,
    effective_profile,
    install,
    set_profile,
)
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_settings import configuration_fingerprint


def _state() -> SearchConsoleState:
    return SearchConsoleState(
        input_mode="url",
        target="https://example.com/",
        ai_provider="none",
        web_performance=False,
        lighthouse_categories="performance,accessibility,best-practices,seo,agentic-browsing",
    )


def test_profile_requires_explicit_single_url() -> None:
    state = _state()
    state.input_mode = "file"
    state.target = "urls.txt"
    with pytest.raises(ValueError, match="URL única"):
        set_profile(state, profile_id="seo", ai_mode=AI_OFF)


def test_overlay_is_ephemeral_and_does_not_mutate_base_configuration() -> None:
    state = _state()
    state.web_performance = False
    state.ai_provider = "none"
    original_categories = state.lighthouse_categories
    session = set_profile(state, profile_id="seo", ai_mode=AI_OFF)
    try:
        with effective_profile(state, session):
            assert state.web_performance is True
            assert state.lighthouse_categories == "best-practices,seo"
            assert state.ai_provider == "none"
        assert state.web_performance is False
        assert state.lighthouse_categories == original_categories
        assert state.ai_provider == "none"
    finally:
        clear_profile(state)


def test_profile_selection_does_not_change_persistable_configuration() -> None:
    state = _state()
    before = configuration_fingerprint(state)
    session = set_profile(state, profile_id="seo-geo-performance", ai_mode=AI_OFF)
    try:
        assert configuration_fingerprint(state) == before
        assert session.profile_id == "seo-geo-performance"
    finally:
        clear_profile(state)


def test_search_profile_requires_terms_but_never_invents_them() -> None:
    state = _state()
    state.search_queries = ()
    session = set_profile(state, profile_id="search-intelligence", ai_mode=AI_OFF)
    try:
        ready, blockers, _ = dependency_status(state, session)
        assert ready is False
        assert any("termos" in item.casefold() for item in blockers)
        assert state.search_queries == ()
    finally:
        clear_profile(state)


def test_profile_excludes_existing_search_terms_without_erasing_session_input() -> None:
    state = _state()
    state.search_queries = ("rasai", "search readiness")
    session = set_profile(state, profile_id="performance", ai_mode=AI_OFF)
    try:
        with effective_profile(state, session):
            assert state.search_queries == ()
        assert state.search_queries == ("rasai", "search readiness")
    finally:
        clear_profile(state)


def test_experience_profile_requires_preconfigured_synthetic_measurement() -> None:
    state = _state()
    state.synthetic_apdex = False
    state.apdex_experience = False
    session = set_profile(state, profile_id="experience", ai_mode=AI_OFF)
    try:
        ready, blockers, _ = dependency_status(state, session)
        assert ready is False
        assert any("apdex" in item.casefold() for item in blockers)
    finally:
        clear_profile(state)


def test_deep_profile_requires_item_13_and_does_not_infer_enablement() -> None:
    state = _state()
    session = set_profile(state, profile_id="deep-analysis", ai_mode=AI_OFF)
    try:
        ready, blockers, _ = dependency_status(state, session)
        assert ready is False
        assert any("item 13" in item.casefold() for item in blockers)
    finally:
        clear_profile(state)


def test_geo_profile_preserves_explicit_ymyl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()
    monkeypatch.setenv("RASAI_CONTENT_RISK_PROFILE", "ymyl")
    monkeypatch.setenv("RASAI_YMYL_CATEGORY", "financial-security")
    session = set_profile(state, profile_id="geo", ai_mode=AI_OFF)
    try:
        ready, blockers, advisories = dependency_status(state, session)
        assert ready is True
        assert blockers == ()
        assert any("explícito" in item.casefold() for item in advisories)
    finally:
        clear_profile(state)


def test_manual_web_override_wins_profile() -> None:
    state = _state()
    session = set_profile(state, profile_id="performance", ai_mode=AI_OFF)
    try:
        session.manual_overrides.add("web")
        state.web_performance = False
        with effective_profile(state, session):
            assert state.web_performance is False
    finally:
        clear_profile(state)


def test_manual_lighthouse_categories_do_not_disable_profile_web_performance() -> None:
    state = _state()
    session = set_profile(state, profile_id="performance", ai_mode=AI_OFF)
    try:
        state.lighthouse_categories = "performance"
        with effective_profile(state, session):
            assert state.web_performance is True
            assert state.lighthouse_categories == "performance"
        assert state.web_performance is False
        assert state.lighthouse_categories == "performance"
    finally:
        clear_profile(state)


def test_installed_wrapper_projects_profile_for_readiness_and_run_then_restores() -> None:
    module = ModuleType("profile_test_console")
    observed: list[tuple[str, bool, str]] = []
    module._menu = lambda state: "Q"
    module._configure = lambda state, choice: None

    def readiness(state):
        observed.append(("readiness", state.web_performance, state.lighthouse_categories))
        return True, "base ready"

    def run(state):
        observed.append(("run", state.web_performance, state.lighthouse_categories))
        return 0

    module._execution_readiness = readiness
    module.run_audit_from_console = run
    install(module)

    state = _state()
    session = set_profile(state, profile_id="performance", ai_mode=AI_OFF)
    try:
        ready, reason = module._execution_readiness(state)
        assert ready is True
        assert "perfil=Performance" in reason
        assert state.web_performance is False

        assert module.run_audit_from_console(state) == 0
        assert state.web_performance is False
        assert observed == [
            ("readiness", True, "performance,best-practices"),
            ("run", True, "performance,best-practices"),
        ]
        assert session.profile_id == "performance"
    finally:
        clear_profile(state)
