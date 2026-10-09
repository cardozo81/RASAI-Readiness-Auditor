"""#358 strict guidance only: no provider or M25 score/config writes."""
from __future__ import annotations

from copy import deepcopy

from rasai.experience_architecture_guidance_358 import (
    resolve_experience_architecture_guidance as resolve,
)


def _config():
    return {
        "kpm": "USER_ACTION_DURATION",
        "satisfied_threshold_seconds": 3.0,
        "frustrated_threshold_seconds": 12.0,
        "samples": 100,
        "session_mode": "warm",
    }


def _m6():
    return {"snapshot_id": "SNP-1", "page_id": "P-1", "device": "MOBILE"}


def test_guided_profile_proposes_only_supported_load_fields_and_preserves_custom_config():
    cfg = _config()
    before = deepcopy(cfg)
    out = resolve(
        cfg, selected_architecture="CSR_SPA",
        observed_architecture="CSR_SPA", provenance=_m6(),
        profile_mode="DYNATRACE_GUIDED", objective="INITIAL_LOAD",
    )
    assert out["adequacy"] == "ADEQUADA_AO_ESCOPO"
    assert out["architecture_source"] == "M6_OBSERVED"
    assert out["profile_mode"] == "DYNATRACE_GUIDED"
    assert out["effective_kpm"] == "USER_ACTION_DURATION"
    assert len(out["new_audit_configuration_preview"]) == 3
    assert {x["value"] for x in out["new_audit_configuration_preview"]} == {
        "USER_ACTION_DURATION", "3.0", "12.0",
    }
    assert all(x["action"] == "PROPOSE_ONLY_REQUIRES_OPERATOR_CONFIRMATION"
               for x in out["new_audit_configuration_preview"])
    assert cfg == before
    assert out["synthetic_apdex_changed"] is False
    assert out["original_aud_writes"] == out["provider_requests"] == 0


def test_custom_mode_keeps_all_explicit_fields_and_never_leaks_guided_proposal():
    cfg = {**_config(), "kpm": "DOM_INTERACTIVE",
           "satisfied_threshold_seconds": 4.0,
           "frustrated_threshold_seconds": 16.0}
    result = resolve(
        cfg, selected_architecture="HYDRATED", profile_mode="CUSTOM",
        objective="INITIAL_LOAD",
        per_field_source={"kpm": "OPERATOR", "satisfied_threshold_seconds": "INI"},
    )
    assert result["effective_kpm"] == "DOM_INTERACTIVE"
    assert result["effective_settings"]["satisfied_threshold_seconds"] == 4
    assert result["new_audit_configuration_preview"] == []
    assert result["per_field_source"]["kpm"] == "OPERATOR"
    assert result["architecture_source"] == "OPERATOR_DECLARED"
    assert result["observed_architecture"] == "UNKNOWN"


def test_guided_profile_warns_of_conflict_and_does_not_override():
    cfg = {**_config(), "kpm": "LOAD_EVENT_END",
           "satisfied_threshold_seconds": 5.0}
    result = resolve(
        cfg, selected_architecture="CSR_SPA",
        profile_mode="DYNATRACE_GUIDED",
    )
    assert result["adequacy"] == "REVISAO_RECOMENDADA"
    assert "GUIDED_PRESET_CONFLICTS_WITH_EFFECTIVE_FIELDS" in result["reasons"]
    proposal = result["new_audit_configuration_preview"]
    assert proposal[0]["would_override_current"] is True
    assert proposal[1]["would_override_current"] is True
    assert proposal[2]["would_override_current"] is False
    assert cfg["kpm"] == "LOAD_EVENT_END"


def test_m6_observation_after_execution_does_not_retroactively_replace_declared():
    cfg = _config()
    result = resolve(
        cfg, selected_architecture="STATIC_OR_SSR",
        observed_architecture="CSR_SPA", provenance=_m6(),
        profile_mode="CUSTOM", objective="INITIAL_LOAD",
    )
    assert result["architecture_mismatch"] is True
    assert result["adequacy"] == "REVISAO_RECOMENDADA"
    assert result["selected_architecture"] == "STATIC_OR_SSR"
    assert result["observed_architecture"] == "CSR_SPA"
    assert result["new_audit_started"] is False
    assert result["original_aud_writes"] == 0


def test_spa_wider_experience_is_partial_even_if_synthetic_load_is_good():
    out = resolve(
        _config(), selected_architecture="CSR_SPA",
        observed_architecture="CSR_SPA", provenance=_m6(),
        profile_mode="CUSTOM", objective="WIDER_EXPERIENCE",
    )
    assert out["adequacy"] == "COBERTURA_PARCIAL"
    assert "INITIAL_LOAD_DOES_NOT_COVER_WIDER_EXPERIENCE" in out["reasons"]
    assert any(a["scope"] == "DYNATRACE_EXTERNAL" for a in out["next_actions"])
    assert out["unsupported_action_types"] == [
        "XHR_AUTONOMOUS", "CUSTOM_AUTONOMOUS", "VENDOR_VISUALLY_COMPLETE",
    ]
    assert out["new_audit_configuration_preview"] == []


def test_unknown_no_provenance_and_invalid_kpm_abstain():
    out = resolve(
        _config(), observed_architecture="CSR_SPA",
        selected_architecture="AUTO",
        provenance=None, profile_mode="CUSTOM",
    )
    assert out["architecture_source"] == "UNKNOWN"
    assert out["effective_architecture_for_advice"] == "UNKNOWN"
    assert out["adequacy"] == "INDETERMINADA"
    invalid = resolve(
        {**_config(), "kpm": "VISUALLY_COMPLETE"},
        selected_architecture="STATIC_OR_SSR",
        profile_mode="CUSTOM",
    )
    assert invalid["adequacy"] == "INDETERMINADA"
    assert "KPM_NOT_EXECUTABLE_IN_M25" in invalid["reasons"]


def test_imported_mode_does_not_run_parser_or_reset_existing_m25():
    cfg = {**_config(), "kpm": "LOAD_EVENT_START"}
    before = deepcopy(cfg)
    out = resolve(
        cfg, selected_architecture="STATIC_OR_SSR",
        profile_mode="DYNATRACE_IMPORTED",
        per_field_source={
            "kpm": "DYNATRACE_EXPORTED_JSON",
            "satisfied_threshold_seconds": "DYNATRACE_EXPORTED_JSON",
            "frustrated_threshold_seconds": "DYNATRACE_EXPORTED_JSON",
        },
    )
    assert out["profile_mode"] == "DYNATRACE_IMPORTED"
    assert out["effective_kpm"] == "LOAD_EVENT_START"
    assert out["new_audit_configuration_preview"] == []
    assert cfg == before
    assert out["per_field_source"]["kpm"] == "DYNATRACE_EXPORTED_JSON"


def test_mixed_or_hydrated_require_no_fabricated_xhr_or_content_ready():
    for arch in ("MIXED", "HYDRATED"):
        out = resolve(
            _config(), selected_architecture=arch,
            profile_mode="DYNATRACE_GUIDED", objective="WIDER_EXPERIENCE",
        )
        assert out["adequacy"] == "COBERTURA_PARCIAL"
        assert out["new_audit_configuration_preview"][0]["value"] == "USER_ACTION_DURATION"
        assert out["new_audit_started"] is False


def test_source_fields_do_not_accept_m6_without_snapshot_page_device_proof():
    for evidence in (
        {}, {"snapshot_id": "SNP-1", "page_id": "P-1"},
        {"snapshot_id": "SNP-1", "page_id": "P-1", "device": ""},
    ):
        outcome = resolve(
            _config(), selected_architecture="AUTO",
            observed_architecture="HYDRATED",
            provenance=evidence,
            profile_mode="CUSTOM",
        )
        assert outcome["observed_architecture"] == "UNKNOWN"
        assert outcome["architecture_source"] == "UNKNOWN"


def test_no_runtime_or_transport_imports_and_no_modified_input():
    from rasai import experience_architecture_guidance_358 as module
    assert not any(name in module.__dict__ for name in (
        "sqlite3", "urlopen", "requests", "httpx", "m25_apdex_experience",
        "m23_apdex", "AuditWorkspace", "provider_factory",
    ))
