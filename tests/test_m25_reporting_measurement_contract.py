from __future__ import annotations

from rasai.m25_reporting import _measurement_contract_context, _measurement_contract_section


def test_current_measurement_contract_is_rendered_without_expanding_settle_duration() -> None:
    context = _measurement_contract_context(
        {
            "measurement_contract": {
                "user_action_duration": "navigationStart_to_loadEventEnd_or_last_xhr_fetch_started_before_loadEventEnd",
                "settle_role": "observation_only_not_duration_extension",
                "runtime_errors": "javascript_and_console_errors_global_when_error_policy_is_enabled",
                "request_error_scope": "first-party",
            }
        }
    )

    assert context["state"] == "ATUAL"
    assert context["legacy"] is False
    section = _measurement_contract_section(context)
    assert "Contrato atual" in section
    assert "XHR/fetch iniciado antes do loadEventEnd" in section
    assert "por si só não estende USER_ACTION_DURATION" in section
    assert "console.error" in section
    assert "first-party" in section
    assert "não aplica retroativamente" not in section


def test_legacy_measurement_contract_preserves_historical_semantics() -> None:
    context = _measurement_contract_context({})

    assert context["state"] == "LEGADO"
    assert context["legacy"] is True
    section = _measurement_contract_section(context)
    assert "Execução legada" in section
    assert "não aplica retroativamente a semântica atual" in section
    assert "Contrato atual" not in section
