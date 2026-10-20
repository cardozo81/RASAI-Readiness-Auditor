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
    assert "Cobertura 97.5% (fração canônica 0.974737)" in html
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
    assert "Confiança contratual HIGH" in html  # Stored global confidence is not rewritten.


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


def test_nonfinite_dimension_coverage_is_not_rendered_as_nan() -> None:
    overall = _row()
    dimension = dict(overall, dimension="CONTENT_VALUE", coverage=float("nan"),
                     confidence="LOW", consolidation_status="PARTIAL")
    html = operational_readiness_panel({"scores": [overall, dimension]})
    assert "CONTENT_VALUE: cobertura N/D" in html
    assert "fração canônica N/D" in html
    assert "nan%" not in html.lower()


def test_invalid_overall_score_fails_closed() -> None:
    for invalid in ("not-a-score", float("nan"), float("inf")):
        condition, label, _ = public_readiness_condition(_row(value=invalid))
        assert condition == "neutral"
        assert label == "Readiness não determinada"


def test_invalid_overall_values_are_safe_in_public_html() -> None:
    for invalid in ("invalid", float("nan"), float("inf")):
        html = operational_readiness_panel({"scores": [_row(value=invalid)]})
        assert "Qualidade medida: <strong>-</strong>" in html
        assert "Readiness não determinada" in html


def test_invalid_overall_coverage_never_renders_nan_or_crashes() -> None:
    for invalid in ("invalid", float("nan"), float("inf"), -1.0, 2.0):
        row = _row()
        row["coverage"] = invalid
        html = operational_readiness_panel({"scores": [row]})
        assert "Cobertura N/D (fração canônica N/D)" in html
        assert "nan%" not in html.lower()


def test_observed_zero_coverage_remains_distinct_from_invalid_coverage() -> None:
    row = _row()
    row["coverage"] = 0.0
    html = operational_readiness_panel({"scores": [row]})
    assert "Cobertura 0.0% (fração canônica 0.000000)" in html


def test_device_cards_do_not_crash_on_nonfinite_coverage() -> None:
    from types import SimpleNamespace
    from rasai.sari_readiness_presentation import _reporting_overall_card, _site_overall_card
    row = _row()
    row["coverage"] = float("nan")
    reporting = SimpleNamespace(PUBLIC_METHOD_VERSION="SARI", _STATUS_LABELS={})
    site = SimpleNamespace(_STATUS_LABELS={}, _device_label=lambda _: "Mobile",
                           _confidence_badge=lambda _: "<span>Confidence</span>")
    executive = _reporting_overall_card(reporting, [row], "MOBILE")
    device = _site_overall_card(site, [row], "MOBILE")
    assert "Fração canônica: N/D" in executive
    assert "Canonical fraction: N/D" in device
    assert "nan%" not in executive.lower() and "nan%" not in device.lower()


def test_conflicting_gate_states_fail_closed() -> None:
    row = _row()
    row["limitations"] = json.dumps(["READINESS_STATUS:READY", "CRITICAL_GATE:DISCOVERY:BLOCKED", "CRITICAL_GATE:DISCOVERY:PASS"])
    assert readiness_state(row)[0] == "BLOCKED"
    assert public_readiness_condition(row)[0] == "critical"


def test_conflicting_aggregate_states_fail_closed() -> None:
    row = _row()
    row["limitations"] = json.dumps(["READINESS_STATUS:READY", "READINESS_STATUS:BLOCKED", "READINESS_STATUS:READY", "CRITICAL_GATE:DISCOVERY:PASS"])
    assert readiness_state(row)[0] == "UNKNOWN"


def test_partial_critical_gate_inventory_cannot_certify_ready() -> None:
    row = _row()
    row["limitations"] = json.dumps(["READINESS_STATUS:READY", "CRITICAL_GATE:DISCOVERY:PASS"])
    assert readiness_state(row)[0] == "UNKNOWN"
    assert public_readiness_condition(row)[1] == "Readiness indeterminada"


def test_single_blocked_gate_still_blocks_without_complete_inventory() -> None:
    row = _row()
    row["limitations"] = json.dumps(["READINESS_STATUS:READY", "CRITICAL_GATE:DISCOVERY:BLOCKED"])
    assert readiness_state(row)[0] == "BLOCKED"


def test_partial_dimension_coverage_is_disclosed_even_if_confidence_high() -> None:
    overall = _row()
    dimension = dict(overall, dimension="CONTENT_VALUE", coverage=0.7,
                     confidence="HIGH", consolidation_status="CONSOLIDATED")
    html = operational_readiness_panel({"scores": [overall, dimension]})
    assert "CONTENT_VALUE: cobertura 70.0%" in html
    assert "confiança HIGH, consolidação CONSOLIDATED" in html


def test_out_of_contract_scores_cannot_be_presented_as_ready() -> None:
    for value in (-0.1, 100.1, 10000, True):
        row = _row(value=value)
        condition, label, _ = public_readiness_condition(row)
        assert condition == "neutral"
        assert label == "Readiness não determinada"


def test_boolean_coverage_is_unavailable_not_one_hundred_percent() -> None:
    row = _row()
    row["coverage"] = True
    html = operational_readiness_panel({"scores": [row]})
    assert "Cobertura N/D (fração canônica N/D)" in html


def test_high_score_with_partial_coverage_does_not_claim_ready() -> None:
    row = _row()
    row["coverage"] = 0.7
    condition, label, quality = public_readiness_condition(row)
    assert condition == "near"
    assert label == "Readiness com medição parcial"
    assert quality == "Excelente (90-100)"


def test_high_score_with_unverifiable_coverage_does_not_claim_ready() -> None:
    for coverage in (None, True, float("nan"), 2.0):
        row = _row()
        row["coverage"] = coverage
        condition, label, _ = public_readiness_condition(row)
        assert condition == "neutral"
        assert label == "Readiness com cobertura não verificada"


def test_blocked_gate_remains_blocked_with_unavailable_coverage() -> None:
    row = _row(status="BLOCKED", discovery_gate="BLOCKED")
    row["coverage"] = None
    assert public_readiness_condition(row)[0] == "critical"


def test_ready_claim_without_any_persisted_gate_does_not_certify() -> None:
    row = _row()
    row["limitations"] = json.dumps(["READINESS_STATUS:READY"])
    assert readiness_state(row)[0] == "UNKNOWN"
    assert public_readiness_condition(row)[0] == "neutral"


def test_sari_convergence_warning_does_not_invent_external_measurements() -> None:
    """#600: 86.5/HIGH with partial dimension is not proof of real-world UX."""
    overall = _row(value=86.484962, status="ATTENTION", discovery_gate="WARNING")
    overall["coverage"] = 0.974737
    partial = dict(overall, dimension="CONTENT_VALUE", coverage=0.7,
                   confidence="LOW", consolidation_status="PARTIAL")
    html = operational_readiness_panel({"scores": [overall, partial]})
    assert "Convergência não garantida" in html
    assert "Lighthouse" in html and "ORIGIN versus URL" in html
    assert "cobertura 70.0%" in html
    assert "86.5/100" in html
    assert "Lighthouse ruim observado" not in html


def test_sari_convergence_warning_reaches_executive_and_device_cards() -> None:
    """#600: notices also appear when rendering cards independently."""
    from types import SimpleNamespace
    from rasai.sari_readiness_presentation import _reporting_overall_card, _site_overall_card

    row = _row(value=86.484962)
    reporting = SimpleNamespace(PUBLIC_METHOD_VERSION="SARI", _STATUS_LABELS={})
    site = SimpleNamespace(
        _STATUS_LABELS={}, _device_label=lambda _: "Mobile",
        _confidence_badge=lambda _: "<span>Confidence</span>",
    )
    executive = _reporting_overall_card(reporting, [row], "MOBILE")
    device = _site_overall_card(site, [row], "MOBILE")
    for card in (executive, device):
        assert "Convergência não garantida" in card
        assert "Lighthouse" in card
        assert "Core Web Vitals" in card
        assert "86.5" in card
