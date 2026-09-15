from __future__ import annotations

import os
from types import SimpleNamespace

from rasai.execution_context_isolation import (
    EXECUTION_GSC_POLICY_ENV,
    _ACTIVE_EXECUTION_STATE,
    _SubprocessProxy,
    build_execution_environment,
    install as install_execution_context_isolation,
    register_execution_environment_override,
)
from rasai.gsc_scope import GSC_ENABLED_ENV


def _state() -> SimpleNamespace:
    return SimpleNamespace(
        input_mode="url",
        target="https://example.test/",
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
        improvement_provider="",
        improvement_model="",
        improvement_reasoning="",
        error="",
        operation="",
    )


def test_profile_gsc_is_projected_only_into_child_environment(monkeypatch) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    monkeypatch.setenv(GSC_ENABLED_ENV, "true")
    monkeypatch.setenv("RASAI_PAGESPEED_ENABLED", "true")
    monkeypatch.setenv("RASAI_CRUX_ENABLED", "true")
    monkeypatch.setenv("RASAI_SERP_MODE", "live")
    monkeypatch.setenv("RASAI_IMPROVEMENT_INTELLIGENCE", "true")
    monkeypatch.delenv(EXECUTION_GSC_POLICY_ENV, raising=False)

    install_execution_context_isolation()
    readiness.install()
    state = _state()
    session = profiles.set_profile(state, profile_id="seo")
    readiness.set_gsc_profile_policy(session, readiness.GSC_PROFILE_DISABLED)

    canonical = {
        GSC_ENABLED_ENV: os.environ[GSC_ENABLED_ENV],
        "RASAI_PAGESPEED_ENABLED": os.environ["RASAI_PAGESPEED_ENABLED"],
        "RASAI_CRUX_ENABLED": os.environ["RASAI_CRUX_ENABLED"],
        "RASAI_SERP_MODE": os.environ["RASAI_SERP_MODE"],
        "RASAI_IMPROVEMENT_INTELLIGENCE": os.environ["RASAI_IMPROVEMENT_INTELLIGENCE"],
    }

    with profiles.effective_profile(state, session):
        # The parent console remains operator-owned even while profile state fields are
        # projected for command building/cost/readiness.
        for name, value in canonical.items():
            assert os.environ[name] == value
        assert EXECUTION_GSC_POLICY_ENV not in os.environ

        child = build_execution_environment(state)
        assert child[GSC_ENABLED_ENV] == "false"
        assert child[EXECUTION_GSC_POLICY_ENV] == readiness.GSC_PROFILE_DISABLED
        assert child["RASAI_PAGESPEED_ENABLED"] == canonical["RASAI_PAGESPEED_ENABLED"]
        assert child["RASAI_CRUX_ENABLED"] == canonical["RASAI_CRUX_ENABLED"]
        assert child["RASAI_SERP_MODE"] == canonical["RASAI_SERP_MODE"]
        assert child["RASAI_IMPROVEMENT_INTELLIGENCE"] == canonical["RASAI_IMPROVEMENT_INTELLIGENCE"]

    for name, value in canonical.items():
        assert os.environ[name] == value
    profiles.clear_profile(state)
    assert os.environ[GSC_ENABLED_ENV] == "true"


def test_explicit_user_change_is_not_rolled_back_by_active_profile(monkeypatch) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    monkeypatch.setenv(GSC_ENABLED_ENV, "false")
    install_execution_context_isolation()
    readiness.install()
    state = _state()
    session = profiles.set_profile(state, profile_id="seo")
    readiness.set_gsc_profile_policy(session, readiness.GSC_PROFILE_DISABLED)

    # Exercise legacy inner wrappers once so any stale baseline would have been created.
    with profiles.effective_profile(state, session):
        assert os.environ[GSC_ENABLED_ENV] == "false"

    # Simulates a direct operator change in the variable screen while the profile remains
    # selected. Subsequent profile previews/execution must not overwrite it in the parent.
    os.environ[GSC_ENABLED_ENV] = "true"
    with profiles.effective_profile(state, session):
        assert os.environ[GSC_ENABLED_ENV] == "true"
        assert build_execution_environment(state)[GSC_ENABLED_ENV] == "false"
    assert os.environ[GSC_ENABLED_ENV] == "true"

    profiles.clear_profile(state)
    assert os.environ[GSC_ENABLED_ENV] == "true"


def test_restored_audit_environment_is_fallback_and_user_value_wins(monkeypatch) -> None:
    state = _state()
    monkeypatch.delenv("RASAI_SERP_PROVIDER", raising=False)
    register_execution_environment_override(state, "RASAI_SERP_PROVIDER", "serpapi")
    register_execution_environment_override(state, "RASAI_SERP_MODE", "fixture")

    child = build_execution_environment(state)
    assert child["RASAI_SERP_PROVIDER"] == "serpapi"
    assert child["RASAI_SERP_MODE"] == "fixture"
    assert "RASAI_SERP_PROVIDER" not in os.environ

    # A later explicit operator configuration is canonical and must beat the historical
    # restored-AUD fallback.
    monkeypatch.setenv("RASAI_SERP_PROVIDER", "dataforseo")
    child = build_execution_environment(state)
    assert child["RASAI_SERP_PROVIDER"] == "dataforseo"


def test_subprocess_proxy_projects_even_when_runtime_supplies_env(monkeypatch) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    monkeypatch.setenv(GSC_ENABLED_ENV, "true")
    install_execution_context_isolation()
    readiness.install()
    state = _state()
    session = profiles.set_profile(state, profile_id="seo")
    readiness.set_gsc_profile_policy(session, readiness.GSC_PROFILE_DISABLED)

    class FakeSubprocess:
        def __init__(self) -> None:
            self.kwargs = None

        def Popen(self, *args, **kwargs):
            self.kwargs = kwargs
            return "PROCESS"

    fake = FakeSubprocess()
    proxy = _SubprocessProxy(fake)
    supplied = {GSC_ENABLED_ENV: "true", "UNCHANGED": "yes"}

    token = _ACTIVE_EXECUTION_STATE.set(state)
    try:
        result = proxy.Popen(["rasai"], env=supplied)
    finally:
        _ACTIVE_EXECUTION_STATE.reset(token)

    assert result == "PROCESS"
    assert supplied[GSC_ENABLED_ENV] == "true"
    assert fake.kwargs is not None
    assert fake.kwargs["env"][GSC_ENABLED_ENV] == "false"
    assert fake.kwargs["env"][EXECUTION_GSC_POLICY_ENV] == "disabled"
    assert fake.kwargs["env"]["UNCHANGED"] == "yes"


def test_restored_audit_fallback_reaches_child_without_profile(monkeypatch) -> None:
    state = _state()
    monkeypatch.delenv("RASAI_SERP_PROVIDER", raising=False)
    register_execution_environment_override(state, "RASAI_SERP_PROVIDER", "serpapi")

    class FakeSubprocess:
        def __init__(self) -> None:
            self.kwargs = None

        def Popen(self, *args, **kwargs):
            self.kwargs = kwargs
            return "PROCESS"

    fake = FakeSubprocess()
    proxy = _SubprocessProxy(fake)
    token = _ACTIVE_EXECUTION_STATE.set(state)
    try:
        proxy.Popen(["rasai"], env=dict(os.environ))
    finally:
        _ACTIVE_EXECUTION_STATE.reset(token)

    assert fake.kwargs is not None
    assert fake.kwargs["env"]["RASAI_SERP_PROVIDER"] == "serpapi"
    assert "RASAI_SERP_PROVIDER" not in os.environ