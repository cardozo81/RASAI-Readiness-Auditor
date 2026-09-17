from __future__ import annotations

from rasai.m25_reporting import _measurement_contract_context, _measurement_contract_section


def test_measurement_contract_is_rendered_without_expanding_settle_duration() -> None:
    context = _measurement_contract_context(
        {
            "measurement_contract": {
                "user_action_duration": "navigationStart_to_loadEventEnd_or_last_xhr_fetch_started_before_loadEventEnd",
                "settle_role": "observation_only_not_duration_extension",
                "runtime_errors": "javascript_and_console_errors_all_scope_only",
                "request_error_scope": "first-party",
            }
        }
    )

    section = _measurement_contract_section(context)
    assert "XHR/fetch iniciado antes do loadEventEnd" in section
    assert "por si só não estende USER_ACTION_DURATION" in section
    assert "Erros JavaScript e de console" in section
    assert "permanecem diagnósticos" in section
    assert "recursos próprios" in section


def test_contract_rendering_keeps_current_semantics_when_optional_metadata_is_absent() -> None:
    context = _measurement_contract_context({})
    section = _measurement_contract_section(context)

    assert "Load Action configurada para esta execução" in section
    assert "observacional" in section
    assert "escopo amplo" in section
    assert "Falhas de requisição" in section
