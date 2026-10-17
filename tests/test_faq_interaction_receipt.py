"""FAQ collector receipt UTC clock provenance guards."""
from datetime import timezone

from rasai.faq_interaction_receipt import _utc


def test_receipt_clocks_require_explicit_utc_offset() -> None:
    assert _utc("2026-10-14T20:00:00Z").tzinfo == timezone.utc
    assert _utc("2026-10-14T20:00:00+00:00").tzinfo == timezone.utc
    assert _utc("2026-10-14T20:00:00-03:00") is None
    assert _utc("2026-10-14T20:00:00") is None
    assert _utc("invalid") is None


def test_blank_collector_identity_never_attests_even_if_explicitly_allowlisted() -> None:
    from rasai.faq_interaction_receipt import verify_faq_interaction_receipt

    receipt = {
        "receipt_id": " ",
        "collector_id": " ",
        "target_id": "faq",
        "document_url": "https://example.test/",
        "before_sha256": "a" * 64,
        "after_sha256": "b" * 64,
        "before_utc": "2026-10-14T20:00:00Z",
        "after_utc": "2026-10-14T20:00:01Z",
        "action": "FAQ_DISCLOSURE_BUTTON_CLICK",
        "target_opt_in": True,
        "isolated_unauthenticated_context": True,
        "network_blocked_after_load": True,
    }
    result = verify_faq_interaction_receipt(
        "<main>a</main>", "<main>b</main>",
        receipt=receipt, receipt_mac="0" * 64, trusted_key=b"k" * 32,
        permitted_collector_ids=frozenset({" "}),
    )
    assert result["status"] == "INTERACTION_NOT_ATTESTED"
    assert result["score_change_authorized"] is False
