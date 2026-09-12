from __future__ import annotations

import json

from rasai import rasai_readiness_reporting as reporting
from rasai.sari_readiness_presentation import (
    install,
    operational_readiness_panel,
    public_readiness_condition,
    readiness_state,
)


def _row(
    *,
    value: float | None = 96.0,
    consolidation: str = "CONSOLIDATED",
    confidence: str = "HIGH",
    status: str = "READY",
    discovery_gate: str = "PASS",
) -> dict[str, object]:
    return {
        "device": "MOBILE",
        "dimension": "OVERALL_READINESS",
        "value": value,
        "coverage": 1.0,
        "confidence": confidence,
        "consolidation_status": consolidation,
        "limitations": json.dumps(
            [
                f"CRITICAL_GATE:DISCOVERY:{discovery_gate}",
                "CRITICAL_GATE:INDEXABILITY:PASS",
                "CRITICAL_GATE:EXTRACTION:PASS",
                f"READINESS_STATUS:{status}",
            ]
        ),
    }


def test_high_numeric_score_is_not_presented_as_excellent_readiness_when_blocked() -> None:
    row = _row(status="BLOCKED", discovery_gate="BLOCKED")
    condition, label, quality = public_readiness_condition(row)

    assert condition == "critical"
    assert label == "Readiness bloqueada"
    assert quality == "Excelente (90-100)"
    assert readiness_state(row)[0] == "BLOCKED"


def test_high_numeric_score_is_not_green_when_measurement_is_partial() -> None:
    condition, label, quality = public_readiness_condition(
        _row(consolidation="PARTIAL", confidence="LOW")
    )

    assert condition == "near"
    assert label == "Readiness com medição parcial"
    assert quality == "Excelente (90-100)"


def test_high_numeric_score_is_positive_only_when_measurement_and_gates_support_it() -> None:
    condition, label, quality = public_readiness_condition(_row())

    assert condition == "expected"
    assert label == "Readiness pronta"
    assert quality == "Excelente (90-100)"


def test_installed_dashboard_and_hero_use_readiness_as_primary_state() -> None:
    install()
    row = _row(status="BLOCKED", discovery_gate="BLOCKED")

    condition, label = reporting._sari_condition(row)
    assert condition == "critical"
    assert "Readiness bloqueada" in label
    assert "qualidade Excelente (90-100)" in label

    html = reporting._overall_card([row], "MOBILE")
    assert "score-card bad" in html
    assert "Readiness bloqueada" in html
    assert "Qualidade do universo medido:</strong> Excelente (90-100)" in html
    assert "DISCOVERY=BLOCKED" in html


def test_readiness_panel_explains_integration_errors_do_not_become_site_failures() -> None:
    html = operational_readiness_panel({"scores": [_row()]})

    assert "Nota medida não substitui readiness operacional" in html
    assert "erro de provider/API/coleta não é defeito do website" in html
    assert "mapeamento explícito" in html
