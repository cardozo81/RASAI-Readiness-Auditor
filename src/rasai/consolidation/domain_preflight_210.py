"""#210: opt-in feasibility gate for same-host, different-URL CONS comparisons.

This pure preflight is deliberately NOT wired into CONS generation or selection.
It cannot turn page metrics into a longitudinal trend or compare aggregate
scores between disjoint page universes. It performs no IO or service calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from rasai.consolidation.selection import AuditCandidate

_CONTRACT = "RASAI-CONS-DOMAIN-PREFLIGHT-210-1"

_METRIC_POLICY = {
    "scores": "NOT_COMPARABLE_DIFFERENT_URL_UNIVERSES",
    "web_performance": "PER_URL_ONLY_NO_CROSS_URL_DELTA",
    "synthetic_apdex": "PER_URL_AND_PROFILE_ONLY_NO_CROSS_URL_TREND",
    "geo_observations": "QUERY_MARKET_DEVICE_PROVENANCE_REQUIRED_NOT_INFERRED",
    "findings": "DESCRIPTIVE_INDEPENDENT_AUDS_NO_TREND",
    "domain_inventory": "SAME_EXACT_HOST_CONTEXT_ONLY",
}


def _origin(value: str) -> tuple[str, str, int] | None:
    """Normalize exact host/origin, never guess organization/eTLD+1."""
    # urlsplit strips embedded TAB, LF and CR on recent Python versions.
    # Refuse such input *before* parsing; otherwise separate physical URL
    # identities could be silently merged into one host/document.
    if (
        not isinstance(value, str)
        or not value or len(value) > 2048
        or value != value.strip()
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
        or "\\" in value
    ):
        return None
    try:
        url = urlsplit(value)
        scheme = url.scheme.lower()
        if (
            scheme not in {"http", "https"}
            or not url.hostname or url.username is not None
            or url.password is not None
            or "@" in url.netloc
            or "%" in url.netloc
            or not url.path.startswith("/")
            and url.path != ""
        ):
            return None
        host = url.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if not host or "." not in host:
            return None
        port = url.port or (443 if scheme == "https" else 80)
        if not 1 <= port <= 65535:
            return None
        return scheme, host, port
    except (TypeError, ValueError, UnicodeError, OverflowError):
        return None


def _document_identity(value: str, origin: tuple[str, str, int]) -> tuple:
    """Use fragment route as a distinct SPA universe; ignore plain anchors.

    An ordinary #section is the same fetched document. In contrast #/route
    and #!/route are client-side routing identities, NOT longitudinal copies
    of the same page. Their content is still unverified without rendering.
    """
    parsed = urlsplit(value)
    route = parsed.fragment if parsed.fragment.startswith(("/", "!/")) else ""
    return origin, parsed.path or "/", parsed.query, route


def assess_same_domain_pair(
    first: AuditCandidate,
    second: AuditCandidate,
) -> dict[str, Any]:
    """Evaluate a pair of *single-URL* candidates, never compute metric deltas.

    The caller must already have enforced indexed single-URL/single-device
    eligibility and authorized AUD access. This function cannot confer access.
    """
    base: dict[str, Any] = {
        "contract_version": _CONTRACT,
        "mode": "SAME_DOMAIN_DESCRIPTIVE_PREVIEW_ONLY",
        "status": "NOT_ELIGIBLE",
        "reason": None,
        "metric_comparability": dict(_METRIC_POLICY),
        "new_cons_generated": False,
        "same_url_longitudinal_changed": False,
        "source_audit_writes": 0,
        "provider_requests": 0,
        "page_level_deltas_allowed": False,
        "audit_score_trend_allowed": False,
        "metric_comparison_executed": False,
        "registrable_domain_equivalence_claimed": False,
        "source_attestation_verified": False,
    }
    if not all(isinstance(x, AuditCandidate) for x in (first, second)):
        return {**base, "reason": "CANDIDATE_SOURCE_NOT_PROVEN"}
    if not first.audit_id or not second.audit_id or first.audit_id == second.audit_id:
        return {**base, "reason": "DISTINCT_AUD_IDS_REQUIRED"}
    left, right = _origin(first.url), _origin(second.url)
    if left is None or right is None:
        return {**base, "reason": "SINGLE_URL_ORIGIN_INVALID"}
    if left[1] != right[1]:
        return {**base, "reason": "EXACT_HOST_MISMATCH"}
    if left != right:
        return {**base, "reason": "DIFFERENT_SCHEME_OR_PORT"}
    if _document_identity(first.url, left) == _document_identity(second.url, right):
        return {**base, "reason": "SAME_URL_USE_EXISTING_LONGITUDINAL_CONS"}
    if (
        not isinstance(first.device, str)
        or not isinstance(second.device, str)
        or first.device.upper() not in {"MOBILE", "DESKTOP"}
        or second.device.upper() not in {"MOBILE", "DESKTOP"}
    ):
        return {**base, "reason": "DEVICE_NOT_PROVEN"}
    if first.device.upper() != second.device.upper():
        return {**base, "reason": "DEVICE_MISMATCH"}
    if (
        not isinstance(first.status, str) or not isinstance(second.status, str)
        or first.status.upper() != "COMPLETED" or second.status.upper() != "COMPLETED"
        or first.completion_status != "COMPLETE"
        or second.completion_status != "COMPLETE"
    ):
        return {**base, "reason": "SOURCE_AUD_NOT_COMPLETE"}
    try:
        # Unlike the general historical parser, this cross-URL feasibility
        # gate cannot silently assume UTC for timezone-naive input.
        a = datetime.fromisoformat(str(first.event_time).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(second.event_time).replace("Z", "+00:00"))
        if (
            a.tzinfo is None or a.utcoffset() is None
            or b.tzinfo is None or b.utcoffset() is None
        ):
            return {**base, "reason": "CHRONOLOGY_UNVERIFIABLE"}
        a = a.astimezone(timezone.utc)
        b = b.astimezone(timezone.utc)
        if a == b:
            return {**base, "reason": "CHRONOLOGY_NOT_ORDERABLE"}
    except (TypeError, ValueError, OverflowError):
        return {**base, "reason": "CHRONOLOGY_UNVERIFIABLE"}
    return {
        **base,
        "status": "ELIGIBLE_FOR_DESCRIPTIVE_SAME_HOST_REVIEW_ONLY",
        "reason": "NO_CROSS_URL_LONGITUDINAL_INFERENCE",
    }
