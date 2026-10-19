"""Offline comparison of two FAQ DOM snapshots; never an interaction proof.

This module does not launch a browser, click, authenticate, access a website,
modify a persisted audit, or change BR-GEO-039/049. A later snapshot cannot
prove a user clicked or that Googlebot indexed content. Source attestation
and safe opted-in acquisition are separate work.
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from rasai.faq_observation import _AccordionParser, _FAQ_CONTEXT, _MAX_HTML_BYTES


def _state(html: str, target: str) -> str:
    parser = _AccordionParser()
    parser.feed(html)
    states = [value for controlled, value in parser.controls if controlled == target]
    if len(states) != 1 or states[0] not in {"true", "false"}:
        return "AMBIGUOUS_OR_MISSING_CONTROL"
    if parser.id_counts.get(target, 0) > 1:
        return "AMBIGUOUS_PANEL_ID"
    if not parser.id_counts.get(target, 0):
        return "COLLAPSED_UNMOUNTED" if states[0] == "false" else "EXPANDED_UNMOUNTED"
    if target in parser.ids_with_dom_text:
        return "COLLAPSED_DOM_TEXT" if states[0] == "false" else "EXPANDED_DOM_TEXT"
    return "COLLAPSED_EMPTY_DOM" if states[0] == "false" else "EXPANDED_EMPTY_DOM"


class _SafeDisclosureButton(HTMLParser):
    """DOM eligibility for opt-in action: never an authorization to click."""

    def __init__(self, target: str) -> None:
        super().__init__(convert_charrefs=True)
        self.target = target
        self.forms = 0
        self.matches = 0
        self.eligible = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "form":
            self.forms += 1
        refs = [value for name, value in attrs if name == "aria-controls"]
        if not any(isinstance(ref, str) and self.target in ref.split()
                   for ref in refs):
            return
        self.matches += 1
        props = dict(attrs)
        expanded = [value for name, value in attrs if name == "aria-expanded"]
        if (
            tag == "button" and not self.forms
            and len(refs) == 1 and refs[0] is not None
            and refs[0].split() == [self.target]
            and len(expanded) == 1
            and str(expanded[0] or "").strip().lower() == "false"
            and str(props.get("type") or "button").lower() == "button"
            and len(attrs) == len(props)
            and "disabled" not in props and "form" not in props
            and "href" not in props
            and not any(name.startswith("on") for name, _ in attrs)
        ):
            self.eligible += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "form":
            self.forms = max(0, self.forms - 1)


def eligible_isolated_faq_disclosure(html: str, target: str) -> bool:
    """Fail closed for links, form submissions or ambiguous controls."""
    if (
        not isinstance(html, str) or not isinstance(target, str)
        or not target or len(target) > 256
        or not _FAQ_CONTEXT.search(target)
        or any(ord(ch) < 32 or ord(ch) == 127 for ch in target)
        or len(html.encode("utf-8")) > _MAX_HTML_BYTES
    ):
        return False
    parser = _SafeDisclosureButton(target)
    parser.feed(html)
    return parser.matches == parser.eligible == 1


def compare_faq_dom_views(
    before_html: Any,
    later_html: Any,
    *,
    target_id: str,
    before_url: str,
    later_url: str,
) -> dict[str, Any]:
    """Compare only same-document FAQ source states, with explicit limits."""
    base = {
        "status": "NOT_COMPARABLE",
        "reason": "INPUT_UNVERIFIABLE",
        "before_state": None,
        "later_state": None,
        "action_or_click_verified": False,
        "crawler_discovery_verified": False,
        "editorial_answer_absence_proven": False,
        "score_change_authorized": False,
    }
    if (
        not isinstance(before_html, str) or not isinstance(later_html, str)
        or not isinstance(target_id, str) or not target_id
        or len(target_id) > 256 or not _FAQ_CONTEXT.search(target_id)
        or any(ord(char) < 32 or ord(char) == 127 for char in target_id)
        or len(before_html.encode("utf-8")) > _MAX_HTML_BYTES
        or len(later_html.encode("utf-8")) > _MAX_HTML_BYTES
        or not isinstance(before_url, str) or not isinstance(later_url, str)
        or before_url != later_url or len(before_url) > 2048
    ):
        return base
    try:
        url = urlsplit(before_url)
    except ValueError:
        return base
    if (
        url.scheme not in {"http", "https"} or not url.hostname
        or url.username is not None or url.password is not None
    ):
        return base
    pre = _state(before_html, target_id)
    post = _state(later_html, target_id)
    if pre.startswith("AMBIGUOUS") or post.startswith("AMBIGUOUS"):
        return {**base, "reason": "DOM_CONTROL_OR_PANEL_AMBIGUOUS"}
    if not pre.startswith("COLLAPSED_"):
        return {**base, "reason": "BASELINE_NOT_COLLAPSED"}
    if not post.startswith("EXPANDED_"):
        return {**base, "reason": "LATER_PANEL_NOT_EXPANDED"}
    return {
        **base,
        "status": "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY",
        "reason": (
            "TEXT_PRESENT_IN_LATER_DOM_NOT_CLICK_PROOF"
            if post == "EXPANDED_DOM_TEXT" else "LATER_DOM_WITHOUT_RECOVERABLE_TEXT"
        ),
        "before_state": pre,
        "later_state": post,
    }
