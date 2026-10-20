"""#603: verify an independently supplied, authenticated review receipt offline.

A checksum of the document and a boolean in site/AI output are not authority.
Only a receipt MAC validated against a separate trusted key and reviewer identity
can be submitted to claim_source_verification for documentary comparison.
The key is injected by a trusted caller; never sourced from the audited website.
No signer, network client, secrets storage or regulatory certification here.
"""
from __future__ import annotations

import hmac
import json
from hashlib import sha256
from typing import Any, Mapping

from rasai.claim_source_verification import classify_claim

_RECEIPT_FIELDS = frozenset({
    "source_url", "document_sha256", "effective_from", "effective_until",
    "reviewed_on", "product_scope", "claim_text", "document_version",
    "issuer", "reviewer_receipt_id", "reviewer_id", "matched_excerpt",
    "review_decision", "independent_source_authenticity_verified",
})
_MAX_RECEIPT_BYTES = 16384


def verify_claim_review_receipt(
    claim_text: str,
    *,
    product_scope: str,
    at_date: Any,
    primary_bytes: bytes | None,
    receipt: Mapping[str, Any] | None,
    receipt_mac: str,
    trusted_key: bytes,
    trusted_reviewer_ids: frozenset[str],
    require_collection_date: bool = False,
) -> dict[str, str]:
    """Fail closed on unsigned/untrusted/altered receipt or original document.

    A verified receipt attests a reviewer's explicitly bounded statement, not
    the truth of the claim, regulatory compliance, or authenticity of a website.
    """
    fallback = {
        "state": "CLAIM_UNVERIFIED_EXTERNAL",
        "basis": "NO_AUTHENTICATED_REVIEW_RECEIPT",
    }
    if (
        not isinstance(receipt, Mapping)
        or not isinstance(receipt_mac, str)
        or not isinstance(trusted_key, bytes) or len(trusted_key) < 32
        or not isinstance(trusted_reviewer_ids, frozenset)
        or not receipt_mac or len(receipt_mac) != 64
        or not _RECEIPT_FIELDS.issubset(receipt)
        or set(receipt) - _RECEIPT_FIELDS - {"collected_on"}
        or receipt.get("independent_source_authenticity_verified") is not True
        or not isinstance(receipt.get("reviewer_id"), str)
        or not receipt["reviewer_id"].strip()
        or receipt["reviewer_id"] not in trusted_reviewer_ids
    ):
        return fallback
    if any(not isinstance(value, (str, bool)) for value in receipt.values()):
        return fallback
    try:
        payload = json.dumps(
            dict(receipt), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > _MAX_RECEIPT_BYTES:
            return fallback
        calculated = hmac.new(trusted_key, payload, sha256).hexdigest()
        if not hmac.compare_digest(calculated, receipt_mac.lower()):
            return fallback
    except (TypeError, ValueError, UnicodeError):
        return fallback
    return classify_claim(
        claim_text, product_scope=product_scope, at_date=at_date,
        primary_bytes=primary_bytes, review=receipt,
        external_validation_required=True,
        require_collection_date=require_collection_date,
    )


__all__ = ["verify_claim_review_receipt"]
