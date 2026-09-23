from __future__ import annotations

from rasai.report_observation_reconciliation import (
    content_remediation_diagnostic,
    sari_band,
)


def test_sari_visual_bands_follow_current_five_band_contract() -> None:
    assert sari_band(100) == ("expected", "Excelente", "90-100")
    assert sari_band(90) == ("expected", "Excelente", "90-100")
    assert sari_band(89.9) == ("expected", "Alta", "75-89")
    assert sari_band(75) == ("expected", "Alta", "75-89")
    assert sari_band(74.9) == ("near", "Moderada", "60-74")
    assert sari_band(60) == ("near", "Moderada", "60-74")
    assert sari_band(59.9) == ("below", "Baixa", "40-59")
    assert sari_band(40) == ("below", "Baixa", "40-59")
    assert sari_band(39.9) == ("critical", "Crítica", "0-39")
    assert sari_band(0) == ("critical", "Crítica", "0-39")
    assert sari_band(None) == ("neutral", "Não determinado", "sem score válido")


def test_content_remediation_empty_state_distinguishes_disabled_and_no_eligible_findings() -> None:
    severity, message = content_remediation_diagnostic(
        {"enabled": 0, "status": "DISABLED", "eligible_findings": 0, "reason": None},
        0,
    )
    assert severity == "neutral"
    assert "desabilitada" in message
    assert "default OFF" in message

    severity, message = content_remediation_diagnostic(
        {
            "enabled": 1,
            "status": "NO_ELIGIBLE_FINDINGS",
            "eligible_findings": 0,
            "reason": "NO_ELIGIBLE_FINDINGS",
        },
        0,
    )
    assert severity == "neutral"
    assert "nenhum finding era elegível" in message
    assert "não indica erro de provider" in message


def test_content_remediation_empty_state_flags_missing_provider_or_unexpected_zero_attempts() -> None:
    severity, message = content_remediation_diagnostic(
        {
            "enabled": 1,
            "status": "NOT_CONFIGURED",
            "eligible_findings": 3,
            "reason": "NO_HEALTHY_PROVIDER",
        },
        0,
    )
    assert severity == "warn"
    assert "nenhum provider saudável/configurado" in message

    severity, message = content_remediation_diagnostic(
        {
            "enabled": 1,
            "status": "DEGRADED",
            "eligible_findings": 2,
            "reason": "PROVIDER_ERROR",
        },
        0,
    )
    assert severity == "warn"
    assert "nenhuma tentativa externa foi persistida" in message
    assert "PROVIDER_ERROR" in message
