"""Primary-document acquisition chronology is evidence, not a compliance decision."""
from datetime import date
from hashlib import sha256
import hmac
import json

from rasai.claim_source_verification import classify_claim
from rasai.claim_review_receipt import verify_claim_review_receipt

CLAIM = "Activation after 24 hours"
DOCUMENT = b"Official source text: Activation after 24 hours for product A."
KEY = b"isolated-review-test-key-of-at-least-32-bytes"
AS_OF = date(2026, 10, 14)


def _receipt() -> dict:
    return {
        "source_url": "https://example.test/primary",
        "document_sha256": sha256(DOCUMENT).hexdigest(),
        "effective_from": "2026-01-01",
        "effective_until": "2026-12-31",
        "reviewed_on": "2026-10-12",
        "collected_on": "2026-10-11",
        "product_scope": "product-A",
        "claim_text": CLAIM,
        "document_version": "2026",
        "issuer": "Test issuer",
        "reviewer_receipt_id": "review-1",
        "reviewer_id": "trusted-reviewer",
        "matched_excerpt": "Activation after 24 hours",
        "review_decision": "CORROBORATES",
        "independent_source_authenticity_verified": True,
    }


def _mac(receipt: dict) -> str:
    data = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(KEY, data, sha256).hexdigest()


def _classify(review: dict) -> dict:
    return classify_claim(
        CLAIM, product_scope="product-A", at_date=AS_OF,
        primary_bytes=DOCUMENT, review=review,
    )


def test_collection_date_must_precede_documentary_review() -> None:
    valid = _receipt()
    assert _classify(valid)["state"] == "CLAIM_CORROBORATED"
    assert _classify({**valid, "collected_on": "2026-10-13"})["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert _classify({**valid, "collected_on": "invalid"})["state"] == "CLAIM_UNVERIFIED_EXTERNAL"


def test_collection_date_is_included_in_signed_receipt() -> None:
    receipt = _receipt()
    kwargs = dict(
        claim_text=CLAIM, product_scope="product-A", at_date=AS_OF,
        primary_bytes=DOCUMENT, trusted_key=KEY,
        trusted_reviewer_ids=frozenset({"trusted-reviewer"}),
    )
    verified = verify_claim_review_receipt(
        receipt=receipt, receipt_mac=_mac(receipt), **kwargs,
    )
    assert verified["state"] == "CLAIM_CORROBORATED"

    edited = {**receipt, "collected_on": "2026-10-13"}
    assert verify_claim_review_receipt(
        receipt=edited, receipt_mac=_mac(receipt), **kwargs,
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
    assert verify_claim_review_receipt(
        receipt=edited, receipt_mac=_mac(edited), **kwargs,
    )["state"] == "CLAIM_UNVERIFIED_EXTERNAL"


def test_regulated_claim_scope_cannot_be_blank_or_padded_even_with_signed_receipt():
    """Documentary corroboration requires an exact nonblank product identity."""
    for scope in (" ", "product-A "):
        receipt = {**_receipt(), "product_scope": scope}
        result = classify_claim(
            CLAIM, product_scope=scope, at_date=AS_OF,
            primary_bytes=DOCUMENT, review=receipt,
        )
        assert result["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
        signed = verify_claim_review_receipt(
            CLAIM, product_scope=scope, at_date=AS_OF,
            primary_bytes=DOCUMENT, receipt=receipt, receipt_mac=_mac(receipt),
            trusted_key=KEY, trusted_reviewer_ids=frozenset({"trusted-reviewer"}),
        )
        assert signed["state"] == "CLAIM_UNVERIFIED_EXTERNAL"


def test_unverified_claim_mode_does_not_invent_observation_for_invalid_input():
    """No documentary check is not proof that an empty claim was observed."""
    for invalid_claim, invalid_scope, invalid_date in (
        ("", "product-A", AS_OF),
        ("   ", "product-A", AS_OF),
        (CLAIM, "", AS_OF),
        (CLAIM, "product-A ", AS_OF),
        (CLAIM, "product-A", "2026-10-14"),
    ):
        result = classify_claim(
            invalid_claim, product_scope=invalid_scope, at_date=invalid_date,
            external_validation_required=False,
        )
        assert result == {
            "state": "CLAIM_UNVERIFIED_EXTERNAL",
            "basis": "INVALID_CLAIM_OR_SCOPE",
        }
    valid = classify_claim(
        CLAIM, product_scope="product-A", at_date=AS_OF,
        external_validation_required=False,
    )
    assert valid["state"] == "CLAIM_OBSERVED"
