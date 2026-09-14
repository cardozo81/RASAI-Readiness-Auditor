from __future__ import annotations

from rasai import m18_reporting
from rasai.ai_attempt_diagnostic_reporting import install


def test_technical_contract_attempt_is_labeled_as_technical_remediation() -> None:
    install()
    row = {
        "semantic_contract_version": "M24-TECHNICAL-REMEDIATION-v2",
    }
    assert m18_reporting._operation(row) == "Remediação técnica"


def test_sanitized_contract_detail_is_visible_without_hiding_failure_metadata() -> None:
    install()
    attempts = [
        {
            "url": "https://example.com/",
            "device": "MOBILE",
            "attempt_index": 1,
            "provider": "DEEPSEEK",
            "model": "deepseek-v4-pro",
            "status": "CONTRACT_ERROR",
            "error_class": "CONTRACT_ERROR",
            "error_type": "ValueError",
            "error_code": "TECHNICAL_AI_CONTRACT_VALIDATION_ERROR",
            "error_detail": "evidence outside the resource universe",
            "retry_eligible": 1,
            "decision": "REPROCESS_ELIGIBLE",
            "fallback_from_provider": None,
            "estimated_cost": 0.00123,
            "cost_currency": "USD",
            "input_tokens": 1000,
            "output_tokens": 200,
            "duration_ms": 500,
        }
    ]

    html = m18_reporting._failure_detail(attempts)

    assert "evidence outside the resource universe" in html
    assert "ValueError" in html
    assert "TECHNICAL_AI_CONTRACT_VALIDATION_ERROR" in html
    assert "O provider respondeu" in html
