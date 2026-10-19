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


def _signed_601_receipt(before, after):
    from hashlib import sha256
    import hmac
    import json
    secret = b"offline-fixture-not-a-real-collector-key-001"
    receipt = {
        "receipt_id": "TEST-601",
        "collector_id": "ISOLATED-TEST",
        "target_id": "faq-answer",
        "document_url": "https://example.test/faq",
        "before_sha256": sha256(before.encode("utf-8")).hexdigest(),
        "after_sha256": sha256(after.encode("utf-8")).hexdigest(),
        "before_utc": "2026-10-14T20:00:00Z",
        "after_utc": "2026-10-14T20:00:01Z",
        "action": "FAQ_DISCLOSURE_BUTTON_CLICK",
        "target_opt_in": True,
        "isolated_unauthenticated_context": True,
        "network_blocked_after_load": True,
    }
    payload = json.dumps(
        receipt, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return receipt, hmac.new(secret, payload, sha256).hexdigest(), secret


def test_601_valid_signed_isolated_disclosure_still_does_not_prove_crawler():
    from rasai.faq_interaction_receipt import verify_faq_interaction_receipt

    before = (
        '<button type="button" aria-controls="faq-answer" '
        'aria-expanded="false">Q</button>'
    )
    after = (
        '<button type="button" aria-controls="faq-answer" '
        'aria-expanded="true">Q</button>'
        '<div id="faq-answer">Answer mounted by SPA</div>'
    )
    receipt, mac, secret = _signed_601_receipt(before, after)
    result = verify_faq_interaction_receipt(
        before, after, receipt=receipt, receipt_mac=mac,
        trusted_key=secret, permitted_collector_ids=frozenset({"ISOLATED-TEST"}),
    )
    assert result["status"] == "ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION"
    assert result["text_recoverable_after_action"] is True
    assert result["crawler_discovery_verified"] is False
    assert result["score_change_authorized"] is False


def test_601_valid_mac_does_not_make_link_form_or_js_click_safe():
    from rasai.faq_interaction_receipt import verify_faq_interaction_receipt

    unsafe = (
        '<a href="https://other.test/" aria-controls="faq-answer" '
        'aria-expanded="false">Q</a>',
        '<form><button aria-controls="faq-answer" '
        'aria-expanded="false">Q</button></form>',
        '<button type="submit" aria-controls="faq-answer" '
        'aria-expanded="false">Q</button>',
        '<button form="checkout" aria-controls="faq-answer" '
        'aria-expanded="false">Q</button>',
        '<button disabled aria-controls="faq-answer" '
        'aria-expanded="false">Q</button>',
        '<div role="button" aria-controls="faq-answer" '
        'aria-expanded="false">Q</div>',
        '<button onclick="doAction()" aria-controls="faq-answer" '
        'aria-expanded="false">Q</button>',
    )
    for before in unsafe:
        after = before.replace(
            'aria-expanded="false"', 'aria-expanded="true"',
        ) + '<div id="faq-answer">Response</div>'
        receipt, mac, secret = _signed_601_receipt(before, after)
        result = verify_faq_interaction_receipt(
            before, after, receipt=receipt, receipt_mac=mac,
            trusted_key=secret, permitted_collector_ids=frozenset({"ISOLATED-TEST"}),
        )
        assert result["status"] == "INTERACTION_NOT_ATTESTED"
        assert result["reason"] == "UNSAFE_OR_AMBIGUOUS_FAQ_ACTION_TARGET"
        assert result["action_attested_by_trusted_collector"] is False
