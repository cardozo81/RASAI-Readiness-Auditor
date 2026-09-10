from __future__ import annotations

import pytest

from rasai.audit_execution_contract import audit_job_defaults, normalize_audit_job_payload
from rasai.execution_contract import validate_execution_job_payload
from rasai.m25_cli import DEFAULT_UX_FRUSTRATED_SECONDS, DEFAULT_UX_SATISFIED_SECONDS


def test_saas_experience_apdex_defaults_match_cli_runtime() -> None:
    defaults = audit_job_defaults()
    assert defaults["apdex_experience_satisfied_seconds"] == DEFAULT_UX_SATISFIED_SECONDS
    assert defaults["apdex_experience_frustrated_seconds"] == DEFAULT_UX_FRUSTRATED_SECONDS

    normalized = normalize_audit_job_payload({
        "synthetic_apdex": True,
        "apdex_threshold_seconds": 1.0,
        "apdex_experience": True,
    })
    assert normalized["apdex_experience_satisfied_seconds"] == DEFAULT_UX_SATISFIED_SECONDS
    assert normalized["apdex_experience_frustrated_seconds"] == DEFAULT_UX_FRUSTRATED_SECONDS


def test_saas_experience_apdex_custom_thresholds_remain_supported() -> None:
    normalized = normalize_audit_job_payload({
        "synthetic_apdex": True,
        "apdex_threshold_seconds": 1.0,
        "apdex_experience": True,
        "apdex_experience_satisfied_seconds": 2.5,
        "apdex_experience_frustrated_seconds": 9.5,
    })
    assert normalized["apdex_experience_satisfied_seconds"] == 2.5
    assert normalized["apdex_experience_frustrated_seconds"] == 9.5

    with pytest.raises(ValueError, match="greater than satisfied"):
        normalize_audit_job_payload({
            "synthetic_apdex": True,
            "apdex_threshold_seconds": 1.0,
            "apdex_experience": True,
            "apdex_experience_satisfied_seconds": 5.0,
            "apdex_experience_frustrated_seconds": 4.0,
        })


def test_durable_execution_contract_rejects_invalid_payload_shapes() -> None:
    validate_execution_job_payload("AUDIT", {})
    validate_execution_job_payload("SEARCH_MONITOR", {"query_id": "QRY-1"})
    validate_execution_job_payload("REPORT_REFRESH", {})
    validate_execution_job_payload("REPORT_REFRESH", {"surface": "portfolio"})

    with pytest.raises(ValueError, match="unsupported AUDIT execution payload"):
        validate_execution_job_payload("AUDIT", {"argv": ["--unsafe"]})
    with pytest.raises(ValueError, match="non-empty"):
        validate_execution_job_payload("SEARCH_MONITOR", {"query_id": ""})
    with pytest.raises(ValueError, match="only payload.query_id"):
        validate_execution_job_payload("SEARCH_MONITOR", {"query_id": "QRY-1", "extra": True})
    with pytest.raises(ValueError, match="portfolio"):
        validate_execution_job_payload("REPORT_REFRESH", {"surface": "other"})
