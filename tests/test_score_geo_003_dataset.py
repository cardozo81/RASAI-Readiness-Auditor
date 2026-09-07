from __future__ import annotations

from searchgeo.score_geo_003 import FEATURE_ORDER
from searchgeo.score_geo_003_calibration import CalibrationCollection, CalibrationRow
from searchgeo.score_geo_003_dataset import build_dataset_manifest


def _row(domain: str, *, total: int = 60) -> CalibrationRow:
    return CalibrationRow(
        domain=domain,
        audit_id=f"AUD-{domain}",
        device="MOBILE",
        features={feature: 0.8 for feature in FEATURE_ORDER},
        successes=30,
        total=total,
        engines=("BING_COPILOT", "GOOGLE_AI"),
        query_count=10,
        min_repetitions=3,
        observed_days=("2026-08-01", "2026-08-08", "2026-08-15"),
    )


def test_dataset_manifest_exposes_pre_fit_gates_without_claiming_validation() -> None:
    rows = tuple(_row(f"d{index}.test") for index in range(40))
    payload = build_dataset_manifest(CalibrationCollection(rows, ()), dataset_version="GEO-CAL-TEST")
    assert payload["status"] == "READY_FOR_MODEL_FIT"
    assert payload["gates"]["domains"]["pass"] is True
    assert payload["gates"]["observations"]["pass"] is True
    assert payload["summary"]["observations"] == 2400
    assert any("AUC" in item for item in payload["limitations"])
    assert len(payload["dataset_sha256"]) == 64


def test_dataset_manifest_is_explicit_when_base_is_insufficient() -> None:
    payload = build_dataset_manifest(CalibrationCollection((_row("one.test", total=30),), ("AUD-X:NO_DATA",)), dataset_version="SMALL")
    assert payload["status"] == "INSUFFICIENT_FOR_PROMOTION_PROTOCOL"
    assert payload["gates"]["domains"]["pass"] is False
    assert payload["gates"]["observations"]["pass"] is False
    assert payload["summary"]["skipped_audits"] == 1
