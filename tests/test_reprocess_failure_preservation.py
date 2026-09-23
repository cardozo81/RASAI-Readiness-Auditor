"""Selective reprocessing must keep the most specific persisted failure reason."""
from __future__ import annotations

from types import SimpleNamespace

from rasai.reprocess_failure_preservation import should_preserve_failure


def _item(**overrides):
    values = {
        "component": "SEMANTIC_AI",
        "status": "FAILED_RETRYABLE",
        "attempt_count": 1,
        "last_error_class": "AI_PROVIDER",
        "last_error_code": "OLD_GENERIC",
        "last_error_message": "old generic failure",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_waiting_prerequisite_is_never_replaced_by_generic_retry_failure() -> None:
    original = _item(status="FAILED_RETRYABLE")
    current = _item(
        status="WAITING_FOR_DATA",
        last_error_code="MAIN_CONTENT_UNAVAILABLE",
        last_error_message="AI_WAITING_FOR_DATA:MAIN_CONTENT_UNAVAILABLE",
    )

    assert should_preserve_failure(original, current) is True


def test_fresh_provider_failure_is_preserved() -> None:
    original = _item(attempt_count=1)
    current = _item(
        attempt_count=2,
        last_error_code="RATE_LIMITED",
        last_error_message="provider did not return an available result",
    )

    assert should_preserve_failure(original, current) is True


def test_repeated_technical_contract_failure_keeps_authoritative_diagnostic() -> None:
    original = _item(
        component="TECHNICAL_AI",
        last_error_class="AI_CONTRACT",
        last_error_code="TECHNICAL_AI_CONTRACT_VALIDATION_ERROR",
        last_error_message="evidence outside the resource universe",
    )
    current = _item(
        component="TECHNICAL_AI",
        last_error_class="AI_CONTRACT",
        last_error_code="TECHNICAL_AI_CONTRACT_VALIDATION_ERROR",
        last_error_message="evidence outside the resource universe",
    )

    assert should_preserve_failure(original, current) is True


def test_repeated_technical_provider_failure_keeps_provider_diagnostic() -> None:
    original = _item(
        component="TECHNICAL_AI",
        last_error_class="AI_PROVIDER",
        last_error_code="RATE_LIMITED",
        last_error_message="provider rate limited the request",
    )
    current = _item(
        component="TECHNICAL_AI",
        last_error_class="AI_PROVIDER",
        last_error_code="RATE_LIMITED",
        last_error_message="provider rate limited the request",
    )

    assert should_preserve_failure(original, current) is True


def test_unchanged_stale_retry_failure_can_receive_orchestrator_fallback() -> None:
    original = _item()
    current = _item()

    assert should_preserve_failure(original, current) is False
