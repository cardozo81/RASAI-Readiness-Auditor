"""#601: authenticated, read-only FAQ before/after DOM evidence receipt.

The consumer does not click, navigate or run a browser. A signed receipt only
attests the explicitly authorized collector's claim about an isolated action.
It never proves Googlebot visibility, editorial absence or score eligibility.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hmac
from hashlib import sha256
import json
from typing import Any, Mapping

from rasai.faq_observation import _MAX_HTML_BYTES
from rasai.faq_transition_policy import compare_faq_dom_views

_FIELDS = frozenset({
    "receipt_id", "collector_id", "target_id", "document_url",
    "before_sha256", "after_sha256", "before_utc", "after_utc",
    "action", "target_opt_in", "isolated_unauthenticated_context",
    "network_blocked_after_load",
})
_ACTION = "FAQ_DISCLOSURE_BUTTON_CLICK"
_MAX_RECEIPT_BYTES = 8192


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def verify_faq_interaction_receipt(
    before_html: Any,
    later_html: Any,
    *,
    receipt: Mapping[str, Any] | None,
    receipt_mac: str,
    trusted_key: bytes,
    permitted_collector_ids: frozenset[str],
) -> dict[str, Any]:
    """Verify source hashes and attested action, then compare HTML safely.

    No automatic prior AUD capture, no assertions about human UX equivalence.
    The MAC verification key MUST be provided by a different trust boundary
    than the website content or an AI response.
    """
    unverified = {
        "status": "INTERACTION_NOT_ATTESTED",
        "action_attested_by_trusted_collector": False,
        "crawler_discovery_verified": False,
        "editorial_answer_absence_proven": False,
        "score_change_authorized": False,
        "new_audit_requests": 0,
        "audit_writes": 0,
    }
    if (
        not isinstance(receipt, Mapping) or set(receipt) != _FIELDS
        or not isinstance(receipt_mac, str) or len(receipt_mac) != 64
        or not isinstance(trusted_key, bytes) or len(trusted_key) < 32
        or not isinstance(permitted_collector_ids, frozenset)
        or not isinstance(receipt.get("collector_id"), str)
        or receipt["collector_id"] not in permitted_collector_ids
        or receipt.get("target_opt_in") is not True
        or receipt.get("isolated_unauthenticated_context") is not True
        or receipt.get("network_blocked_after_load") is not True
        or receipt.get("action") != _ACTION
        or not isinstance(receipt.get("receipt_id"), str)
        or not receipt["receipt_id"]
        or not isinstance(before_html, str) or not isinstance(later_html, str)
    ):
        return unverified
    try:
        original = before_html.encode("utf-8")
        updated = later_html.encode("utf-8")
    except UnicodeError:
        return unverified
    if not original or not updated or max(len(original), len(updated)) > _MAX_HTML_BYTES:
        return unverified
    if (
        receipt.get("before_sha256") != sha256(original).hexdigest()
        or receipt.get("after_sha256") != sha256(updated).hexdigest()
    ):
        return unverified
    before = _utc(receipt.get("before_utc"))
    after = _utc(receipt.get("after_utc"))
    if (
        before is None or after is None or after <= before
        or (after - before).total_seconds() > 30
    ):
        return unverified
    try:
        signed = json.dumps(
            dict(receipt), ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        if len(signed) > _MAX_RECEIPT_BYTES or not hmac.compare_digest(
            hmac.new(trusted_key, signed, sha256).hexdigest(),
            receipt_mac.lower(),
        ):
            return unverified
    except (ValueError, TypeError, UnicodeError):
        return unverified
    observed = compare_faq_dom_views(
        before_html, later_html,
        target_id=receipt.get("target_id"),
        before_url=receipt.get("document_url"),
        later_url=receipt.get("document_url"),
    )
    if observed["status"] != "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY":
        return {**unverified, "reason": "ATTESTED_SOURCE_DOM_INCONCLUSIVE"}
    return {
        **unverified,
        "status": "ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION",
        "action_attested_by_trusted_collector": True,
        "before_state": observed["before_state"],
        "later_state": observed["later_state"],
        "text_recoverable_after_action": observed["later_state"] == "EXPANDED_DOM_TEXT",
        "receipt_scope": "TRUSTED_COLLECTOR_ONLY_NOT_CRAWLER_OR_HUMAN_UX_CERTIFICATION",
    }


__all__ = ["verify_faq_interaction_receipt"]
