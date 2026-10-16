from __future__ import annotations

import json

from rasai.sari_readiness_presentation import (
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


def test_readiness_panel_explains_integration_errors_do_not_become_site_failures() -> None:
    html = operational_readiness_panel({"scores": [_row()]})

    assert "Nota medida não substitui readiness operacional" in html
    assert "erro de provider/API/coleta não é defeito do website" in html
    assert "mapeamento explícito" in html


def test_executive_panel_preserves_canonical_fraction_and_limits_confidence_claim() -> None:
    row = _row(value=86.484962, status="ATTENTION", discovery_gate="WARNING")
    row["coverage"] = 0.974737
    html = operational_readiness_panel({"scores": [row]})
    assert "Coverage 97.5% (fração canônica 0.974737)" in html
    assert "não representam intervalo estatístico" in html
    assert "posição SERP ou citação generativa" in html
    assert "86.5/100" in html


def test_executive_panel_does_not_silently_promote_partial_dimension() -> None:
    overall = _row(value=86.484962, status="ATTENTION")
    dimension = dict(overall, dimension="CONTENT_VALUE", coverage=0.7,
                     confidence="LOW", consolidation_status="PARTIAL")
    html = operational_readiness_panel({"scores": [overall, dimension]})
    assert "qualidade do universo efetivamente avaliado" in html
    assert "dimensões de baixa cobertura devem ser analisadas separadamente" in html
    assert "Confidence HIGH" in html  # Stored global confidence is not rewritten.


def test_blocked_readiness_remains_critical_with_partial_measurement() -> None:
    row = _row(status="BLOCKED", discovery_gate="BLOCKED", consolidation="PARTIAL", confidence="LOW")
    condition, label, quality = public_readiness_condition(row)
    assert condition == "critical"
    assert label == "Readiness bloqueada"
    assert quality == "Excelente (90-100)"


def test_blocked_readiness_remains_critical_without_consolidated_confidence() -> None:
    row = _row(status="BLOCKED", discovery_gate="BLOCKED", consolidation="NOT_CONSOLIDATED", confidence="UNAVAILABLE")
    condition, label, quality = public_readiness_condition(row)
    assert condition == "critical"
    assert label == "Readiness bloqueada"
    assert quality == "Excelente (90-100)"


def test_unknown_critical_gate_is_not_presented_as_only_partial_coverage() -> None:
    row = _row(status="UNKNOWN", discovery_gate="UNKNOWN", consolidation="PARTIAL", confidence="LOW")
    condition, label, quality = public_readiness_condition(row)
    assert condition == "neutral"
    assert label == "Readiness indeterminada"
    assert quality == "Excelente (90-100)"


def test_blocked_readiness_is_visible_without_numeric_score() -> None:
    row = _row(value=None, status="BLOCKED", discovery_gate="BLOCKED")
    condition, label, _quality = public_readiness_condition(row)
    assert condition == "critical"
    assert label == "Readiness bloqueada"


def test_persisted_blocked_gate_takes_precedence_over_ready_marker() -> None:
    row = _row(status="READY", discovery_gate="BLOCKED")
    assert readiness_state(row)[0] == "BLOCKED"
    assert public_readiness_condition(row)[0] == "critical"


def test_unknown_gate_value_fails_closed() -> None:
    row = _row(status="READY", discovery_gate="NOT_CHECKED")
    assert readiness_state(row)[0] == "UNKNOWN"


def test_warning_gate_without_aggregate_status_requires_attention() -> None:
    row = _row(status="UNKNOWN", discovery_gate="WARNING")
    assert readiness_state(row)[0] == "ATTENTION"


def test_ready_aggregate_with_warning_gate_requires_attention() -> None:
    row = _row(status="READY", discovery_gate="WARNING")
    assert readiness_state(row)[0] == "ATTENTION"
    assert public_readiness_condition(row)[1] == "Readiness requer atenção"


def test_unrecognized_measurement_states_fail_closed() -> None:
    for consolidation, confidence in (("UNRECOGNIZED", "HIGH"), ("CONSOLIDATED", "UNRECOGNIZED"), ("", "HIGH")):
        condition, label, _ = public_readiness_condition(_row(consolidation=consolidation, confidence=confidence))
        assert condition == "neutral"
        assert label == "Readiness não consolidada"


def test_partial_dimension_is_explicit_without_changing_aggregate() -> None:
    overall = _row(value=86.484962, confidence="HIGH", consolidation="CONSOLIDATED")
    dimension = dict(overall, dimension="CONTENT_VALUE", coverage=0.7,
                     confidence="LOW", consolidation_status="PARTIAL")
    html = operational_readiness_panel({"scores": [overall, dimension]})
    assert "CONTENT_VALUE: cobertura 70.0%" in html
    assert "fração canônica 0.700000" in html
    assert "confiança LOW, consolidação PARTIAL" in html
    assert "O estado agregado não substitui a leitura por dimensão." in html
    assert "86.5/100" in html
