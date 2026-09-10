"""Bounded retry/fallback policy for paid AI integrations.

Explicit providers may retry transient failures once. Dynamic AUTO never retries the
same provider immediately: one AI need traverses each currently eligible provider at
most once, while the execution-wide coordinator decides whether a provider remains
eligible for later needs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

MAX_PROVIDER_ATTEMPTS_PER_CONTEXT = 2
MAX_AUTO_ATTEMPTS_PER_CONTEXT = 8
MAX_RETRY_DELAY_SECONDS = 5.0
DEFAULT_RETRY_DELAY_SECONDS = 0.25
RATE_LIMIT_DEFAULT_DELAY_SECONDS = 1.0

RETRYABLE_ERROR_CLASSES = frozenset({"NETWORK_ERROR", "TIMEOUT_ERROR", "SERVER_ERROR", "RATE_LIMIT_ERROR", "EMPTY_RESPONSE"})
DECISION_SUCCESS = "SUCCESS"
DECISION_SUCCESS_AFTER_RETRY = "SUCCESS_AFTER_RETRY"
DECISION_RETRY = "RETRY"
DECISION_FALLBACK = "FALLBACK"
DECISION_FALLBACK_SUCCESS = "FALLBACK_SUCCESS"
DECISION_STOP = "STOP"


@dataclass(frozen=True, slots=True)
class RetryPolicyDecision:
    eligible: bool
    delay_seconds: float
    reason: str


def parse_retry_after(value: Any, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        seconds = float(text)
    except (TypeError, ValueError):
        try:
            target = parsedate_to_datetime(text)
            if target.tzinfo is None:
                target = target.replace(tzinfo=timezone.utc)
            reference = now or datetime.now(timezone.utc)
            seconds = (target.astimezone(timezone.utc) - reference.astimezone(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds)


def retry_policy(error_class: Any, retry_after_seconds: float | None = None) -> RetryPolicyDecision:
    token = str(getattr(error_class, "value", error_class) or "").upper()
    if token not in RETRYABLE_ERROR_CLASSES:
        return RetryPolicyDecision(False, 0.0, "NON_RETRYABLE_ERROR_CLASS")
    if retry_after_seconds is not None and retry_after_seconds > MAX_RETRY_DELAY_SECONDS:
        return RetryPolicyDecision(False, 0.0, "RETRY_AFTER_EXCEEDS_CAP")
    if token == "RATE_LIMIT_ERROR":
        delay = RATE_LIMIT_DEFAULT_DELAY_SECONDS if retry_after_seconds is None else retry_after_seconds
    else:
        delay = DEFAULT_RETRY_DELAY_SECONDS if retry_after_seconds is None else retry_after_seconds
    return RetryPolicyDecision(True, min(max(delay, 0.0), MAX_RETRY_DELAY_SECONDS), "TRANSIENT_ERROR")


def max_attempts_for_auto(provider_count: int) -> int:
    """Bound AUTO to one call per currently eligible provider for one AI need."""
    if provider_count <= 0:
        return 0
    return min(provider_count, MAX_AUTO_ATTEMPTS_PER_CONTEXT)
