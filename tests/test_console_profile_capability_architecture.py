import os
from types import SimpleNamespace

from rasai import console_execution_profile_readiness as readiness
from rasai import console_execution_profiles as profiles
from rasai.console_profile_capability_architecture import CAPS, effective_profile, metadata
from rasai.execution_capabilities import CAPABILITY_BY_ID, PROFILE_SELECTABLE


def _state():
    return SimpleNamespace(
        input_mode="url",
        target="https://example.com/",
        web_performance=False,
        lighthouse_categories="seo",
        ai_provider="openai",
        ai_model="configured-model",
        ai_reasoning=None,
        content_remediation=True,
        technical_remediation=False,
        synthetic_apdex=True,
        apdex_experience=True,
        search_queries=("brand",),
        improvement_enabled=True,
        runtime_blocks={},
    )


def test_profile_scope_disables_unselected_session_workloads_and_restores_parent() -> None:
    state = _state()
    session = profiles.SessionProfile(
        "performance",
        "Performance",
        ("web-performance",),
        profiles.AI_OFF,
        profiles._baseline(state),
    )

    with effective_profile(state, session):
        assert state.web_performance is True
        assert state.ai_provider == "none"
        assert state.ai_model is None
        assert state.content_remediation is False
        assert state.technical_remediation is False
        assert state.search_queries == ()
        assert state.synthetic_apdex is False
        assert state.apdex_experience is False
        assert state.improvement_enabled is False
        assert state.lighthouse_categories == "performance,best-practices"

    assert state.web_performance is False
    assert state.lighthouse_categories == "seo"
    assert state.ai_provider == "openai"
    assert state.ai_model == "configured-model"
    assert state.content_remediation is True
    assert state.search_queries == ("brand",)
    assert state.synthetic_apdex is True
    assert state.apdex_experience is True
    assert state.improvement_enabled is True


def test_no_ai_profile_is_authoritative_even_when_session_has_provider() -> None:
    state = _state()
    session = profiles.SessionProfile(
        "custom",
        "Personalizado",
        ("web-performance",),
        profiles.AI_OFF,
        profiles._baseline(state),
    )

    with effective_profile(state, session):
        assert state.ai_provider == "none"
        assert state.ai_model is None
        assert state.ai_reasoning is None

    assert state.ai_provider == "openai"
    assert state.ai_model == "configured-model"


def test_explicit_post_profile_override_wins() -> None:
    state = _state()
    session = profiles.SessionProfile(
        "performance",
        "Performance",
        ("web-performance",),
        profiles.AI_OFF,
        profiles._baseline(state),
    )
    session.manual_overrides.update({"web", "ai"})

    with effective_profile(state, session):
        assert state.web_performance is False
        assert state.ai_provider == "openai"


def test_gsc_profile_policy_is_projected_and_parent_environment_restored() -> None:
    state = _state()
    session = profiles.SessionProfile(
        "performance",
        "Performance",
        ("web-performance",),
        profiles.AI_OFF,
        profiles._baseline(state),
    )
    readiness.set_gsc_profile_policy(session, readiness.GSC_PROFILE_DISABLED)
    previous = os.environ.get(readiness.GSC_ENABLED_ENV)
    os.environ[readiness.GSC_ENABLED_ENV] = "true"
    try:
        with effective_profile(state, session):
            assert os.environ[readiness.GSC_ENABLED_ENV] == "false"
        assert os.environ[readiness.GSC_ENABLED_ENV] == "true"
    finally:
        if previous is None:
            os.environ.pop(readiness.GSC_ENABLED_ENV, None)
        else:
            os.environ[readiness.GSC_ENABLED_ENV] = previous


def test_presets_use_only_canonical_capability_ids() -> None:
    assert CAPS["search-intelligence"] == ("search-intelligence",)
    assert CAPS["apdex-navigation"] == ("apdex-navigation",)
    assert CAPS["apdex-experience"] == ("apdex-navigation", "apdex-experience")
    assert "deep-analysis" in CAPS["complete-maximum"]
    assert all(
        capability_id in CAPABILITY_BY_ID
        for capability_ids in CAPS.values()
        for capability_id in capability_ids
    )


def test_custom_profile_exposes_only_selectable_workloads() -> None:
    selectable = {item.id for item in PROFILE_SELECTABLE}
    assert "domain-discovery" not in selectable
    assert "quality" not in selectable
    assert {"web-performance", "search-intelligence", "apdex-navigation", "deep-analysis"} <= selectable


def test_profile_metadata_exposes_only_current_capability_contract() -> None:
    state = _state()
    session = profiles.SessionProfile(
        "performance",
        "Performance",
        ("web-performance",),
        profiles.AI_OFF,
        profiles._baseline(state),
    )
    payload = metadata(session)
    assert payload["capabilities"] == ["web-performance"]
    assert "modules" not in payload
