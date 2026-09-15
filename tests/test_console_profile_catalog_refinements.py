from __future__ import annotations

from types import SimpleNamespace

from rasai import console_execution_profile_readiness as readiness
from rasai import console_execution_profiles as profiles
from rasai.console_profile_catalog_refinements import install


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


def test_profile_dependencies_use_canonical_preparation_items(monkeypatch) -> None:
    readiness.install()
    console = SimpleNamespace()
    install(console)

    state = _state()
    maximum = readiness._candidate(state, profiles._PROFILE_BY_ID["complete-maximum"])
    monkeypatch.setattr(profiles, "_effective_ai_provider", lambda _state: "auto")
    monkeypatch.setattr(
        "rasai.improvement_intelligence_console._single_url_ready",
        lambda _state: (True, "ok"),
    )

    ready, blockers, _ = profiles.dependency_status(state, maximum)
    rendered = " | ".join(blockers)
    assert ready is False
    assert "item 13" in rendered
    assert "item 12" in rendered
    assert "item 8" not in rendered


def test_deep_profile_uses_primary_ai_and_requests_deep_analysis() -> None:
    readiness.install()
    console = SimpleNamespace()
    install(console)

    definition = profiles._PROFILE_BY_ID["deep-analysis"]
    candidate = readiness._candidate(_state(), definition)
    assert candidate.ai_mode == profiles.AI_IF_AVAILABLE
    assert "item 6" in profiles.MODULE_BY_ID["deep-analysis"].dependency_note
    assert "especializada" in profiles.MODULE_BY_ID["deep-analysis"].dependency_note
