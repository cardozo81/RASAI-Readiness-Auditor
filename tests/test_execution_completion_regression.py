from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from rasai import m24_ai
from rasai.execution_completion_regression import (
    _EXECUTION_GSC_POLICY_ENV,
    _canonical_resource_evidence,
    _install_console_gsc_execution_marker,
    _install_gsc_collection_execution_gate,
    _project_gsc_policy,
)
from rasai.execution_context_isolation import (
    build_execution_environment,
    install as install_execution_context_isolation,
)
from rasai.gsc_scope import GSC_ENABLED_ENV


def _resource_response(resource: str, evidence_ids: list[str]) -> dict[str, object]:
    return {
        "summary_pt": "Resumo limitado às evidências fornecidas.",
        "actions": [],
        "resource_assessments": [
            {
                "resource": resource,
                "verdict": "NEUTRAL",
                "confidence": 0.8,
                "evidence_ids": evidence_ids,
                "rationale_pt": "Avaliação limitada ao recurso persistido.",
            }
        ],
        "policy_note_pt": "Mudanças de política exigem revisão humana.",
    }


def test_m24_resource_universe_includes_diagnostic_and_baseline_evidence() -> None:
    facts = [
        {
            "code": "M24-SITEMAP-HTTP_ERROR",
            "category": "SITEMAP",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-SITEMAP-DIAGNOSTIC"],
        },
        {
            "code": "M24-RESOURCE-SITEMAP-BASELINE",
            "category": "SITEMAP",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-SITEMAP-BASELINE"],
        },
        {
            "code": "M24-RESOURCE-ROBOTS-BASELINE",
            "category": "ROBOTS",
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            "evidence_ids": ["EV-ROBOTS-BASELINE"],
        },
    ]
    universe = _canonical_resource_evidence(facts)
    assert universe["SITEMAP"] == frozenset(
        {"EV-SITEMAP-DIAGNOSTIC", "EV-SITEMAP-BASELINE"}
    )

    result = m24_ai._validate(
        _resource_response(
            "SITEMAP",
            ["EV-SITEMAP-DIAGNOSTIC", "EV-SITEMAP-BASELINE"],
        ),
        allowed_codes=frozenset(),
        allowed_evidence=frozenset(
            {"EV-SITEMAP-DIAGNOSTIC", "EV-SITEMAP-BASELINE", "EV-ROBOTS-BASELINE"}
        ),
        resource_evidence=universe,
    )
    assert result["resource_assessments"][0]["evidence_ids"] == [
        "EV-SITEMAP-DIAGNOSTIC",
        "EV-SITEMAP-BASELINE",
    ]

    with pytest.raises(ValueError, match="outside its resource universe"):
        m24_ai._validate(
            _resource_response("ROBOTS", ["EV-SITEMAP-DIAGNOSTIC"]),
            allowed_codes=frozenset(),
            allowed_evidence=frozenset(
                {"EV-SITEMAP-DIAGNOSTIC", "EV-SITEMAP-BASELINE", "EV-ROBOTS-BASELINE"}
            ),
            resource_evidence=universe,
        )


def test_execution_gsc_disabled_overrides_global_true() -> None:
    effective = _project_gsc_policy(
        {
            GSC_ENABLED_ENV: "true",
            _EXECUTION_GSC_POLICY_ENV: "disabled",
        }
    )
    assert effective[GSC_ENABLED_ENV] == "false"


def test_gsc_collection_gate_passes_hard_disabled_environment(monkeypatch) -> None:
    from rasai import standards_gsc_observability_runtime as runtime

    received: list[dict[str, str]] = []

    def fake_collect(*, audit_id: str, workspace, env=None):
        received.append(dict(env or {}))
        return {
            "service_state": "DISABLED",
            "requested": False,
            "configured": True,
            "effective_enabled": False,
            "operations": [],
            "errors": [],
        }

    monkeypatch.setattr(runtime, "collect_configured_search_console", fake_collect)
    _install_gsc_collection_execution_gate()
    monkeypatch.setenv(GSC_ENABLED_ENV, "true")
    monkeypatch.setenv(_EXECUTION_GSC_POLICY_ENV, "disabled")

    result = runtime.collect_configured_search_console(
        audit_id="AUD-GSC-DISABLED",
        workspace=SimpleNamespace(),
    )

    assert result["effective_enabled"] is False
    assert received
    assert received[-1][GSC_ENABLED_ENV] == "false"


def test_profile_gsc_policy_is_private_to_execution_environment(monkeypatch) -> None:
    from rasai import console_execution_profile_readiness as readiness
    from rasai import console_execution_profiles as profiles

    monkeypatch.setenv(GSC_ENABLED_ENV, "true")
    monkeypatch.delenv(_EXECUTION_GSC_POLICY_ENV, raising=False)
    _install_console_gsc_execution_marker()
    install_execution_context_isolation()
    readiness.install()

    state = SimpleNamespace(
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
    session = profiles.set_profile(state, profile_id="seo")
    readiness.set_gsc_profile_policy(session, readiness.GSC_PROFILE_DISABLED)

    with profiles.effective_profile(state, session):
        # Parent/session variables remain operator-owned.
        assert os.environ[GSC_ENABLED_ENV] == "true"
        assert _EXECUTION_GSC_POLICY_ENV not in os.environ

        child = build_execution_environment(state)
        assert child[_EXECUTION_GSC_POLICY_ENV] == "disabled"
        assert child[GSC_ENABLED_ENV] == "false"

    assert _EXECUTION_GSC_POLICY_ENV not in os.environ
    assert os.environ[GSC_ENABLED_ENV] == "true"
    profiles.clear_profile(state)
    assert os.environ[GSC_ENABLED_ENV] == "true"