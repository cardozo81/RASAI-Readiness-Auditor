"""Opt-in, live-page same-sample FAQ and readiness witness (#652/#322).

This is an explicit caller-owned adapter, not a background crawler, default M3
interaction or automatic M25 reclassification. It never opens/navigates a page,
writes to an AUD, signs with website data, or calls a provider. Two-stage proof:
a live Playwright session witness; optional independent read-only AUD DOM binding.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import hmac
import json
import re
from typing import Any, Mapping
from urllib.parse import urlsplit

from rasai.apdex_content_readiness_observation import PrimaryContentReadiness
from rasai.faq_existing_page_pilot import inspect_existing_page_faq
from rasai.faq_interaction_receipt import verify_faq_interaction_receipt
from rasai.playwright_primary_content_probe import observe_existing_playwright_page

_SCOPE_KEYS = (
    "audit_id", "page_id", "snapshot_id", "sample_id", "context_id",
    "requested_url", "final_url", "device", "architecture",
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE_VERSION = "RASAI-LIVE-SAME-PAGE-WITNESS-001"
_FAQ_ACTION = "FAQ_DISCLOSURE_BUTTON_CLICK"


@dataclass(frozen=True, slots=True)
class LiveWitness:
    """Private handoff object: DOM strings MUST NOT be logged/published."""
    scope: dict[str, str]
    readiness: PrimaryContentReadiness
    faq_result: dict[str, Any]
    receipt: dict[str, Any] | None
    receipt_mac: str | None
    signed_witness: dict[str, Any] | None
    witness_mac: str | None
    before_html: str | None
    later_html: str | None


def _bounded_scope(scope: Mapping[str, Any]) -> dict[str, str]:
    if not isinstance(scope, Mapping) or set(scope) != set(_SCOPE_KEYS):
        raise ValueError("incomplete same-sample identity")
    out: dict[str, str] = {}
    for key in _SCOPE_KEYS:
        value = scope[key]
        if (not isinstance(value, str) or not value or value != value.strip()
                or len(value) > (2048 if key.endswith("_url") else 160)
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError("unverifiable same-sample identity")
        out[key] = value
    if (not out["audit_id"].startswith("AUD-")
            or out["device"] not in {"MOBILE", "DESKTOP"}
            or out["architecture"] not in {"CSR_SPA", "HYDRATED", "MIXED",
                                            "STATIC_OR_SSR", "UNKNOWN"}):
        raise ValueError("invalid audit, device or architecture scope")
    for key in ("requested_url", "final_url"):
        parsed = urlsplit(out[key])
        if (parsed.scheme not in {"https", "http"}
                or not parsed.hostname or parsed.username is not None
                or parsed.password is not None):
            raise ValueError("unsafe source URL")
    return out


def _seal(payload: Mapping[str, Any], key: bytes) -> str:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > 32 * 1024:
        raise ValueError("witness exceeds bounded size")
    return hmac.new(key, encoded, sha256).hexdigest()


def observe_same_browser_sample(
    page: Any, *, scope: Mapping[str, Any],
    navigation_started_monotonic_ns: int,
    load_ms: float, faq_target_id: str,
    captured_dom_sha256: str,
    signing_key: bytes, collector_id: str,
    trusted_collectors: frozenset[str],
    explicit_faq_opt_in: bool = False,
    isolated_context_acknowledged: bool = False,
    readiness_opt_in: bool = False,
    readiness_window_ms: int = 1200,
) -> LiveWitness:
    """Run readiness BEFORE the FAQ gesture in exactly one *existing* page.

    A source renderer must freeze its authoritative rendered DOM *before*
    calling this function, without closing/reopening the page. A matching SHA
    alone never proves the stored AUD belongs to the same physical session.
    """
    identity = _bounded_scope(scope)
    if (
        page is None or not isinstance(signing_key, bytes)
        or len(signing_key) < 32
        or not isinstance(trusted_collectors, frozenset)
        or not isinstance(collector_id, str)
        or not collector_id.strip() or collector_id not in trusted_collectors
        or not isinstance(navigation_started_monotonic_ns, int)
        or isinstance(navigation_started_monotonic_ns, bool)
        or navigation_started_monotonic_ns <= 0
        or not isinstance(captured_dom_sha256, str)
        or not _SHA256.fullmatch(captured_dom_sha256)
    ):
        raise ValueError("live observation must be explicitly collector authorized")
    if (explicit_faq_opt_in is not True
            or isolated_context_acknowledged is not True):
        raise ValueError("physical FAQ gesture needs explicit opt-in and isolation")
    try:
        context = page.context
        if (page.url != identity["final_url"]
                or len(context.pages) != 1
                or context.pages[0] is not page
                or bool(context.service_workers)):
            raise ValueError("browser document/context differs from supplied scope")
    except (AttributeError, TypeError) as exc:
        raise ValueError("browser context not verifiable") from exc

    # Page-bound probe is limited to a single navigation origin and cannot
    # create a new browser or use time from an M3 page in a different process.
    readiness = observe_existing_playwright_page(
        page=page, sample_id=identity["sample_id"],
        context_id=identity["context_id"], page_id=identity["page_id"],
        device=identity["device"], architecture=identity["architecture"],
        navigation_started_monotonic_ns=navigation_started_monotonic_ns,
        load_ms=load_ms, enabled=bool(readiness_opt_in),
        window_ms=readiness_window_ms,
    )
    # Even an unavailable readiness probe does not grant permission to click
    # an unrelated new document. The page object and URL must be unchanged.
    if (page.url != identity["final_url"]
            or len(context.pages) != 1 or context.pages[0] is not page):
        raise ValueError("page identity changed during readiness observation")
    before_html = page.content()
    if sha256(before_html.encode("utf-8")).hexdigest() != captured_dom_sha256:
        raise ValueError("the frozen canonical DOM does not match live page")
    faq = inspect_existing_page_faq(
        page, target_id=faq_target_id,
        explicit_opt_in=True,
        isolated_context_acknowledged=True,
        expected_before_sha256=captured_dom_sha256,
    )
    if (
        faq.get("status") != "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED"
        or faq.get("before_sha256") != captured_dom_sha256
    ):
        return LiveWitness(identity, readiness, faq, None, None, None, None,
                           None, None)
    if (page.url != identity["final_url"]
            or len(context.pages) != 1 or context.pages[0] is not page):
        raise ValueError("page changed after FAQ action")
    later_html = page.content()
    if sha256(later_html.encode("utf-8")).hexdigest() != faq.get("after_sha256"):
        raise ValueError("DOM changed after FAQ action evidence")
    receipt = {
        "receipt_id": "FAQ-" + sha256(
            (identity["sample_id"] + captured_dom_sha256
             + str(faq["after_utc"])).encode("utf-8")
        ).hexdigest()[:24],
        "collector_id": collector_id,
        "target_id": faq_target_id,
        "document_url": identity["final_url"],
        "before_sha256": captured_dom_sha256,
        "after_sha256": faq["after_sha256"],
        "before_utc": faq["before_utc"],
        "after_utc": faq["after_utc"],
        "action": _FAQ_ACTION, "target_opt_in": True,
        "isolated_unauthenticated_context": True,
        "network_blocked_after_load": True,
    }
    receipt_mac = _seal(receipt, signing_key)
    authenticated = verify_faq_interaction_receipt(
        before_html, later_html, receipt=receipt,
        receipt_mac=receipt_mac, trusted_key=signing_key,
        permitted_collector_ids=trusted_collectors,
    )
    if authenticated["status"] != "ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION":
        raise ValueError("live collector receipt verification failed")
    witness = {
        "contract_version": _SIGNATURE_VERSION,
        "scope": identity,
        "collector_id": collector_id,
        "receipt_sha256": sha256(_seal(receipt, signing_key).encode()).hexdigest(),
        "readiness": asdict(readiness),
        "same_live_page_observed_by_collector": True,
        "same_persisted_aud_session_independently_attested": False,
        "crawler_discovery_verified": False,
        "score_change_authorized": False,
    }
    witness_mac = _seal(witness, signing_key)
    return LiveWitness(
        identity, readiness, faq, receipt, receipt_mac,
        witness, witness_mac, before_html, later_html,
    )


def verify_bound_live_witness(
    witness: LiveWitness, *, aud_dir: Any,
    trusted_key: bytes, permitted_collector_ids: frozenset[str],
) -> dict[str, Any]:
    """Read-only physical AUD DOM comparison; do not overclaim M3 same-session.

    Signed live session scope + equal persisted M3 DOM is stronger than two
    unrelated snapshots, but the M3 renderer must attest its own callback
    correlation before 'same_aud_sample_verified' may ever be TRUE.
    """
    fallback = {
        "status": "SAME_SAMPLE_PHYSICAL_EVIDENCE_NOT_VERIFIED",
        "signed_live_page_witness_valid": False,
        "same_aud_sample_verified": False,
        "same_browser_session_independently_attested": False,
        "crawler_discovery_verified": False,
        "score_change_authorized": False,
        "audit_writes": 0, "provider_requests": 0,
    }
    if (
        not isinstance(witness, LiveWitness) or witness.receipt is None
        or witness.signed_witness is None
        or not isinstance(trusted_key, bytes) or len(trusted_key) < 32
        or not isinstance(witness.receipt_mac, str)
        or not isinstance(witness.witness_mac, str)
        or witness.signed_witness.get("scope") != witness.scope
        or witness.signed_witness.get("readiness") != asdict(witness.readiness)
    ):
        return fallback
    try:
        if not (
            hmac.compare_digest(_seal(witness.receipt, trusted_key),
                                witness.receipt_mac)
            and hmac.compare_digest(_seal(witness.signed_witness, trusted_key),
                                    witness.witness_mac)
            and witness.signed_witness["receipt_sha256"] ==
                sha256(witness.receipt_mac.encode()).hexdigest()
        ):
            return fallback
        from rasai.faq_aud_receipt_binding import inspect_faq_receipt_aud_binding
        scope = _bounded_scope(witness.scope)
        linked = inspect_faq_receipt_aud_binding(
            aud_dir, audit_id=scope["audit_id"],
            page_id=scope["page_id"], snapshot_id=scope["snapshot_id"],
            requested_url=scope["requested_url"],
            final_url=scope["final_url"], device=scope["device"],
            before_html=witness.before_html, later_html=witness.later_html,
            receipt=witness.receipt, receipt_mac=witness.receipt_mac,
            trusted_key=trusted_key,
            permitted_collector_ids=permitted_collector_ids,
        )
    except (ValueError, TypeError, KeyError, UnicodeError):
        return fallback
    if linked["status"] != "SIGNED_RECEIPT_MATCHES_PERSISTED_AUD_DOM_BYTES":
        return {**fallback, "reason": linked.get("reason")}
    return {
        **fallback,
        "status": "LIVE_COLLECTOR_AND_AUD_DOM_LINKED_NOT_INDEPENDENTLY_ATTESTED",
        "signed_live_page_witness_valid": True,
        "persisted_dom_bytes_match_signed_receipt": True,
        "collector_claims_same_live_page": True,
        "faq_after_action_text_recoverable": linked["text_recoverable_after_action"],
        "readiness_status": witness.readiness.status,
        "reason": "TRUSTED_COLLECTOR_WITNESS_NOT_AN_INDEPENDENT_M3_SESSION_ATTESTATION",
    }


__all__ = [
    "LiveWitness", "observe_same_browser_sample", "verify_bound_live_witness",
]
