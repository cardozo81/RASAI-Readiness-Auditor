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
    require_collection_date: bool = False,
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
    claim = claim_text if isinstance(claim_text, str) else ""
    # Datetime is a date subclass, but cannot be safely compared to parsed dates.
    # Invalid caller input must abstain rather than crash the report consumer.
    if (not claim or claim != claim.strip() or not isinstance(product_scope, str)
            or not product_scope.strip() or product_scope != product_scope.strip()
            or type(at_date) is not date):
        # A missing/malformed claim is not an observed factual claim, even
        # when documentary validation was not requested for this context.
        return (fallback if external_validation_required else {
            "state": "CLAIM_UNVERIFIED_EXTERNAL",
            "basis": "INVALID_CLAIM_OR_SCOPE",
        })
    if not isinstance(primary_bytes, bytes) or not 0 < len(primary_bytes) <= _MAX_DOCUMENT_BYTES:
        return fallback
    if not isinstance(review, Mapping):
        return fallback
    # urlsplit silently discards embedded TAB/LF/CR and leading C0 spaces,
    # which could turn a malformed claimed primary-source URL into HTTPS.
    # Signed review bytes must identify the exact URL without such repairs.
    source_url = review.get("source_url")
    if (not isinstance(source_url, str) or not source_url
            or source_url != source_url.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in source_url)):
        return fallback
    try:
        target = urlsplit(source_url)
        valid_url = (
            target.scheme == "https" and bool(target.hostname)
            and target.username is None and target.password is None
            and (target.port is None or 1 <= target.port <= 65535)
        )
        effective_from = date.fromisoformat(str(review.get("effective_from")))
        effective_until = date.fromisoformat(str(review.get("effective_until")))
        reviewed_on = date.fromisoformat(str(review.get("reviewed_on")))
        collected_raw = review.get("collected_on")
        collected_on = (
            date.fromisoformat(str(collected_raw))
            if collected_raw is not None else None
        )
        decoded = primary_bytes.decode("utf-8")
        asserted_hash = str(review.get("document_sha256") or "").strip().lower()
        evidence = str(review.get("matched_excerpt") or "").strip()
        decision = str(review.get("review_decision") or "").strip().upper()
    except (UnicodeError, ValueError, TypeError):
        return fallback
    # Regulated/material reviews may demand the physical collection date.
    # Keep historical receipts readable without treating missing collection
    # evidence as verified when the strict review policy is requested.
    if require_collection_date and collected_on is None:
        return {
            "state": "CLAIM_UNVERIFIED_EXTERNAL",
            "basis": "PRIMARY_COLLECTION_DATE_NOT_VERIFIED",
        }
    if not (
        valid_url
        and asserted_hash == sha256(primary_bytes).hexdigest()
        and effective_from <= at_date <= effective_until
        # Retrospective independent documentary review is valid: a reviewer
        # may inspect today a source version that was effective at the AUD
        # snapshot date. Never force false backdating of reviewer credentials.
        # Applicability is bounded by effective_from/until at at_date; review
        # and collection chronology is a separate, present-time assertion.
        and reviewed_on <= date.today()
        and (collected_on is None or collected_on <= reviewed_on)
        and str(review.get("product_scope") or "") == product_scope
        and isinstance(review.get("claim_text"), str) and review["claim_text"] == claim
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
