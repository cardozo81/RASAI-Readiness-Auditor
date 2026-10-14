"""Conservative, offline claim-to-primary-document review contract (#603).

An external link or a supplied document alone never establishes authenticity,
applicability, truth or regulatory conformity. Only an independently attested,
versioned review record may promote a claimed match/contradiction. This helper
does not contact authorities, run AI, change a score or accept arbitrary URLs
as independently verified proof.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from typing import Any, Mapping
from urllib.parse import urlsplit

_STATES = frozenset({
    "CLAIM_OBSERVED",
    "CLAIM_UNVERIFIED_EXTERNAL",
    "CLAIM_CORROBORATED",
    "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE",
})
_MAX_DOCUMENT_BYTES = 4_000_000


def classify_claim(
    claim_text: str,
    *,
    product_scope: str,
    at_date: date,
    primary_bytes: bytes | None = None,
    review: Mapping[str, Any] | None = None,
    external_validation_required: bool = True,
) -> dict[str, str]:
    """Require all independent source and reviewer fields, else abstain.

    The independently-verified flag and reviewer receipt must originate from
    trusted ingestion/review, never from the audited website or LLM response.
    Even an accepted review is documentary corroboration, not a legal opinion.
    """
    state = (
        "CLAIM_UNVERIFIED_EXTERNAL" if external_validation_required
        else "CLAIM_OBSERVED"
    )
    fallback = {"state": state, "basis": "NO_VERIFIED_PRIMARY_SOURCE"}
    claim = str(claim_text or "").strip()
    if not claim or not product_scope or not isinstance(at_date, date):
        return fallback
    if not isinstance(primary_bytes, bytes) or not 0 < len(primary_bytes) <= _MAX_DOCUMENT_BYTES:
        return fallback
    if not isinstance(review, Mapping):
        return fallback
    try:
        target = urlsplit(str(review.get("source_url") or ""))
        valid_url = target.scheme == "https" and bool(target.hostname) and not (
            target.username or target.password
        )
        effective_from = date.fromisoformat(str(review.get("effective_from")))
        effective_until = date.fromisoformat(str(review.get("effective_until")))
        reviewed_on = date.fromisoformat(str(review.get("reviewed_on")))
        decoded = primary_bytes.decode("utf-8")
        asserted_hash = str(review.get("document_sha256") or "").strip().lower()
        evidence = str(review.get("matched_excerpt") or "").strip()
        decision = str(review.get("review_decision") or "").strip().upper()
    except (UnicodeError, ValueError, TypeError):
        return fallback
    if not (
        valid_url
        and asserted_hash == sha256(primary_bytes).hexdigest()
        and effective_from <= at_date <= effective_until
        and reviewed_on <= at_date
        and str(review.get("product_scope") or "") == product_scope
        and bool(str(review.get("document_version") or "").strip())
        and bool(str(review.get("issuer") or "").strip())
        and bool(str(review.get("reviewer_receipt_id") or "").strip())
        and review.get("independent_source_authenticity_verified") is True
        and len(evidence) >= 12 and evidence in decoded
        and decision in {"CORROBORATES", "CONTRADICTS"}
    ):
        return fallback
    # These are the only two promoted review outcomes. They remain explicit
    # documentary assessments, not product certification or legal compliance.
    return {
        "state": (
            "CLAIM_CORROBORATED" if decision == "CORROBORATES"
            else "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE"
        ),
        "basis": "INDEPENDENT_VERSIONED_SOURCE_REVIEW",
    }
