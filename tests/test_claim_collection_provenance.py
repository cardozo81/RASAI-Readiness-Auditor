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

def test_claim_source_url_must_be_exact_https_without_credentials_or_controls():
    """#603: a signed receipt cannot launder a malformed URL via urlsplit."""
    for source_url in (
        " https://example.test/primary",
        "https://example.test/primary ",
        "https://examp\nle.test/primary",
        "https://examp\tle.test/primary",
        "https://@example.test/primary",
        "https://user:@example.test/primary",
        "https://example.test:unparseable/primary",
        "http://example.test/primary",
    ):
        changed = {**_receipt(), "source_url": source_url}
        assert _classify(changed)["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
        # MAC validity alone does not override a malformed physical URL.
        authenticated = verify_claim_review_receipt(
            CLAIM, product_scope="product-A", at_date=AS_OF,
            primary_bytes=DOCUMENT,
            receipt=changed, receipt_mac=_mac(changed),
            trusted_key=KEY,
            trusted_reviewer_ids=frozenset({"trusted-reviewer"}),
        )
        assert authenticated["state"] == "CLAIM_UNVERIFIED_EXTERNAL"


def test_603_literal_claim_identity_is_required_for_documentary_promotion():
    for raw in (" " + CLAIM, CLAIM + "\n", "\t" + CLAIM, 42):
        assert classify_claim(raw, product_scope="product-A", at_date=AS_OF,
                              primary_bytes=DOCUMENT, review=_receipt())["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
        assert verify_claim_review_receipt(raw, product_scope="product-A", at_date=AS_OF,
                    primary_bytes=DOCUMENT, receipt=_receipt(), receipt_mac=_mac(_receipt()),
                    trusted_key=KEY, trusted_reviewer_ids=frozenset({"trusted-reviewer"}))["state"] == "CLAIM_UNVERIFIED_EXTERNAL"
