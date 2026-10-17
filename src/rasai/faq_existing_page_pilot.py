"""Opt-in FAQ disclosure observation on an already-loaded isolated browser page.

No browser launch, navigation or audit writes. The caller owns the independent
browser context; any post-load HTTP requests are aborted during the click.
This is local diagnostic evidence, never crawler visibility or SARI scoring.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any
from urllib.parse import urlsplit

from rasai.faq_observation import _FAQ_CONTEXT, _MAX_HTML_BYTES
from rasai.faq_transition_policy import compare_faq_dom_views


def inspect_existing_page_faq(
    page: Any, *, target_id: str, explicit_opt_in: bool = False,
    isolated_context_acknowledged: bool = False,
) -> dict[str, Any]:
    """Click exactly one FAQ button in an isolated single-page browser context.

    A physical browser caller must have loaded the target independently and
    blocked service workers. Output is descriptive and never a signed receipt.
    """
    result = {
        "status": "NOT_OBSERVED",
        "reason": "OPT_IN_OR_ISOLATION_NOT_PROVEN",
        "action_performed": False,
        "network_isolation_enforced_during_action": False,
        "same_aud_sample_verified": False,
        "authenticated_collector_receipt": False,
        "crawler_discovery_verified": False,
        "score_change_authorized": False,
        "audit_writes": 0,
        "provider_requests": 0,
    }
    if (explicit_opt_in is not True
            or isolated_context_acknowledged is not True or page is None
            or not isinstance(target_id, str)
            or not target_id or len(target_id) > 256
            or not _FAQ_CONTEXT.search(target_id)
            or any(ord(char) < 32 for char in target_id)):
        return result
    try:
        context = page.context
        if len(context.pages) != 1 or context.service_workers:
            return {**result, "reason": "BROWSER_CONTEXT_NOT_ISOLATED"}
        original_url = page.url
        parsed = urlsplit(original_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return {**result, "reason": "DOCUMENT_IDENTITY_UNVERIFIABLE"}
    except (AttributeError, TypeError, ValueError):
        return {**result, "reason": "BROWSER_CONTEXT_NOT_ISOLATED"}

    def abort_new_request(route: Any) -> None:
        route.abort()

    route_attached = False
    try:
        context.route("**/*", abort_new_request)
        route_attached = True
        before = page.content()
        if len(before.encode("utf-8")) > _MAX_HTML_BYTES:
            return {**result, "reason": "DOM_EXCEEDS_LIMIT"}
        candidates = page.locator("button[aria-controls]")
        count = candidates.count()
        if count > 100:
            return {**result, "reason": "TOO_MANY_CONTROLS"}
        controls = [
            candidates.nth(index) for index in range(count)
            if candidates.nth(index).get_attribute("aria-controls") == target_id
        ]
        if (len(controls) != 1
                or controls[0].get_attribute("aria-expanded") != "false"):
            return {**result, "reason": "AMBIGUOUS_OR_ALREADY_OPEN_CONTROL"}
        if (
            controls[0].get_attribute("form") is not None
            or controls[0].get_attribute("formaction") is not None
            or controls[0].evaluate("(button) => Boolean(button.closest('form'))")
        ):
            return {**result, "reason": "UNSAFE_FORM_CONTROL"}
        controls[0].click(timeout=1500)
        if page.url != original_url or len(context.pages) != 1:
            return {**result, "reason": "NAVIGATION_OR_POPUP_AFTER_ACTION",
                    "action_performed": True}
        after = page.content()
        if len(after.encode("utf-8")) > _MAX_HTML_BYTES:
            return {**result, "reason": "DOM_EXCEEDS_LIMIT_AFTER_ACTION",
                    "action_performed": True}
        comparison = compare_faq_dom_views(
            before, after, target_id=target_id,
            before_url=original_url, later_url=page.url,
        )
        if comparison["status"] != "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY":
            return {**result, "reason": comparison["reason"],
                    "action_performed": True}
        return {
            **result,
            "status": "LOCAL_FAQ_ACTION_OBSERVED_NOT_ATTESTED",
            "network_isolation_enforced_during_action": True,
            "reason": comparison["reason"],
            "action_performed": True,
            "before_state": comparison["before_state"],
            "after_state": comparison["later_state"],
            "before_sha256": sha256(before.encode("utf-8")).hexdigest(),
            "after_sha256": sha256(after.encode("utf-8")).hexdigest(),
        }
    except Exception:
        return {**result, "reason": "BROWSER_ACTION_OR_INSPECTION_FAILED"}
    finally:
        if route_attached:
            try:
                context.unroute("**/*", abort_new_request)
            except Exception:
                pass
