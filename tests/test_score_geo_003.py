from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from searchgeo.domain import DeviceContext, RuleExecution, RuleResult
from searchgeo.score_geo_003 import (
    CalibrationModel,
    FEATURE_ORDER,
    MODEL_FORMAT_VERSION,
    SCORING_VERSION,
    VALIDATED_STATUS,
    load_model,
    write_model,
)
from searchgeo.score_geo_003_calibration import CalibrationRow, fit_calibration_model
from searchgeo.scoring import ConsolidationStatus
from searchgeo.scoring_v003 import ScoreGeo003Engine

_NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _execution(rule_id: str, result: RuleResult, *, observed: dict[str, object] | None = None) -> RuleExecution:
    return RuleExecution(
        rule_execution_id=f"REX-{rule_id}-{result.value}", audit_id="AUD-003", rule_id=rule_id,
        rule_version="1", page_id="P1", snapshot_id=None, device=DeviceContext.DESKTOP,
        result=result, observed_value=observed or {}, expected_condition="fixture",
        evidence_ids=("EVD-1",), executed_at=_NOW,
    )


def _complete_executions() -> tuple[RuleExecution, ...]:
    base = (
        _execution("BR-GEO-005", RuleResult.PASS),
        _execution("BR-GEO-011", RuleResult.PASS),
        _execution("BR-GEO-025", RuleResult.PASS),
        _execution("BR-GEO-028", RuleResult.PASS),
        _execution("BR-GEO-031", RuleResult.PASS),
        _execution("BR-GEO-038", RuleResult.PASS),
        _execution("BR-GEO-041", RuleResult.PASS),
        _execution("BR-GEO-045", RuleResult.PASS),
        _execution("BR-GEO-048", RuleResult.PASS),
    )
    structured = tuple(_execution(f"BR-GEO-{number:03d}", RuleResult.NOT_APPLICABLE) for number in range(34, 38))
    return (*base, *structured)


def _validated_model() -> CalibrationModel:
    return CalibrationModel(
        format_version=MODEL_FORMAT_VERSION,
        scoring_version=SCORING_VERSION,
        model_version="GEO-LR-TEST",
        dataset_version="GEO-CAL-TEST",
        status=VALIDATED_STATUS,
        trained_at=_NOW.isoformat(),
        intercept=-0.5,
        coefficients={feature: 0.2 for feature in FEATURE_ORDER},
        imputation_means={feature: 0.5 for feature in FEATURE_ORDER},
        engines=("ENGINE-A", "ENGINE-B"),
        training={"domains": 28, "observations": 1680},
        validation={"domains": 12, "observations": 720, "auc": 0.8, "brier": 0.15, "baseline_brier": 0.25},
        protocol={"split": "DOMAIN_HOLDOUT_70_30_V1"},
        calibration_confidence="MEDIUM",
        artifact_sha256="a" * 64,
    )


def test_score_geo_003_blocks_overall_without_validated_model() -> None:
    result = ScoreGeo003Engine().score(
        audit_id="AUD-003",
        executions=_complete_executions(),
        devices=(DeviceContext.DESKTOP,),
    )
    overall = result.overall_by_device[DeviceContext.DESKTOP]
    assert all(score.scoring_version == "SCORE-GEO-003" for score in result.scores)
    assert overall.scoring_version == "SCORE-GEO-003"
    assert overall.value is None
    assert overall.consolidation_status == ConsolidationStatus.NOT_CONSOLIDATED
    assert "CALIBRATION_MODEL_UNAVAILABLE:SCORE-GEO-003" in overall.limitations


def test_score_geo_003_uses_validated_model_for_overall() -> None:
    result = ScoreGeo003Engine(calibration_model=_validated_model()).score(
        audit_id="AUD-003",
        executions=_complete_executions(),
        devices=(DeviceContext.DESKTOP,),
    )
    overall = result.overall_by_device[DeviceContext.DESKTOP]
    assert overall.value is not None
    assert 0.0 < overall.value < 100.0
    assert overall.consolidation_status == ConsolidationStatus.CONSOLIDATED
    assert overall.confidence.value == "MEDIUM"
    assert "CALIBRATION_MODEL:GEO-LR-TEST" in overall.limitations
    assert "DIMENSION_NOT_APPLICABLE:STRUCTURED_DATA" in overall.limitations


def test_model_round_trip_and_strict_contract() -> None:
    payload = {
        "format_version": MODEL_FORMAT_VERSION,
        "scoring_version": SCORING_VERSION,
        "model_version": "GEO-LR-TEST",
        "dataset_version": "GEO-CAL-TEST",
        "status": "VALIDATED",
        "trained_at": _NOW.isoformat(),
        "feature_order": list(FEATURE_ORDER),
        "intercept": -0.1,
        "coefficients": {feature: 0.1 for feature in FEATURE_ORDER},
        "imputation_means": {feature: 0.5 for feature in FEATURE_ORDER},
        "engines": ["ENGINE-A", "ENGINE-B"],
        "calibration_confidence": "MEDIUM",
        "training": {"domains": 28},
        "validation": {"domains": 12, "auc": 0.7, "brier": 0.2, "baseline_brier": 0.24},
        "protocol": {"split": "DOMAIN_HOLDOUT_70_30_V1"},
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        written = write_model(path, payload)
        loaded = load_model(path)
        assert written.model_version == loaded.model_version
        assert len(loaded.artifact_sha256) == 64
        assert 0.0 < loaded.predict_probability({feature: 0.8 for feature in FEATURE_ORDER}) < 1.0


def test_calibration_gate_can_validate_minimum_empirical_dataset() -> None:
    rows: list[CalibrationRow] = []
    for index in range(40):
        signal = index / 39
        cited = 60 if signal >= 0.5 else 0
        rows.append(
            CalibrationRow(
                domain=f"site-{index:02d}.example",
                audit_id=f"AUD-{index:02d}",
                device="DESKTOP",
                features={feature: signal for feature in FEATURE_ORDER},
                successes=cited,
                total=60,
                engines=("ENGINE-A", "ENGINE-B"),
                query_count=10,
                min_repetitions=3,
            )
        )
    fit = fit_calibration_model(rows, dataset_version="GEO-CAL-001")
    assert fit.validated
    assert fit.payload["status"] == "VALIDATED"
    assert fit.payload["validation"]["domains"] >= 12
    assert fit.payload["validation"]["auc"] >= 0.60
    assert fit.payload["validation"]["brier"] < fit.payload["validation"]["baseline_brier"]
