"""Passive, per-URL inventory of potential FAQ disclosure targets.

This is an authorization planning tool, NOT a selector that performs clicks.
It makes no network requests, does not open a browser or modify any AUD,
and cannot establish that an observed DOM belongs to an audited sample.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlsplit

from rasai.faq_observation import _FAQ_CONTEXT, _MAX_HTML_BYTES
from rasai.faq_transition_policy import eligible_isolated_faq_disclosure

_CONTRACT = "RASAI-FAQ-TARGET-INVENTORY-001"
_MAX_CANDIDATES = 100


class _CandidateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[str | None] = []
        self.summary_count = 0
        self.uncoupled_expanded_controls = 0
        self.nonbutton_disclosures = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "summary":
            self.summary_count += 1
        if tag != "button":
            if any(key == "aria-controls" for key, _ in attrs) or any(
                key == "role" and value == "button" for key, value in attrs
            ):
                self.nonbutton_disclosures += 1
            return
        controls = [value for key, value in attrs if key == "aria-controls"]
        if not controls:
            if any(key == "aria-expanded" for key, _ in attrs):
                self.uncoupled_expanded_controls += 1
            return
        if len(controls) != 1 or not isinstance(controls[0], str):
            self.refs.append(None)
            return
        targets = controls[0].split()
        self.refs.append(targets[0] if len(targets) == 1 else None)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _scope_url(value: object) -> bool:
    if (not isinstance(value, str) or not value or len(value) > 2048
            or value != value.strip() or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and not parsed.fragment and parsed.port != 0
        )
    except ValueError:
        return False


def inspect_faq_target_candidates(
    html: str, *, requested_url: str, final_url: str, device: str,
) -> dict[str, Any]:
    """Discover non-authoritative IDs in *one* captured DOM at one URL/device.

    Every result needs an independent per-URL consent decision, and a fresh
    live DOM eligibility/hash check before any future physical action.
    Non-semantic IDs and details/summary cannot be clicked by the current
    conservative worker; do not silently invent a CSS selector for them.
    """
    denied: dict[str, Any] = {
        "contract": _CONTRACT,
        "status": "NOT_VERIFIABLE",
        "reason": "SCOPE_OR_HTML_UNVERIFIABLE",
        "candidates": [],
        "action_performed": False,
        "click_authorized": False,
        "same_aud_sample_verified": False,
        "crawler_discovery_verified": False,
        "provider_requests": 0,
        "audit_writes": 0,
    }
    if (not isinstance(html, str) or not _scope_url(requested_url)
            or not _scope_url(final_url)
            or device not in {"DESKTOP", "MOBILE"}):
        return denied
    try:
        encoded_html = html.encode("utf-8")
        if not 0 < len(encoded_html) <= _MAX_HTML_BYTES:
            return denied
        parser = _CandidateParser()
        parser.feed(html)
        if (len(parser.refs) > _MAX_CANDIDATES
                or parser.summary_count > _MAX_CANDIDATES
                or parser.uncoupled_expanded_controls > _MAX_CANDIDATES
                or parser.nonbutton_disclosures > _MAX_CANDIDATES):
            return {**denied, "reason": "CANDIDATE_LIMIT_EXCEEDED"}
        counts: dict[str, int] = {}
        for candidate in parser.refs:
            if candidate is not None:
                counts[candidate] = counts.get(candidate, 0) + 1
        seen: set[str] = set()
        items: list[dict[str, str | bool]] = []
        for candidate in parser.refs:
            if candidate is None:
                items.append({
                    "target_id": "",
                    "eligibility": "AMBIGUOUS_OR_MULTIPLE_IDREFS",
                    "action_authorized": False,
                })
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            if (not candidate or len(candidate) > 256
                    or any(ord(ch) < 32 or ord(ch) == 127 for ch in candidate)):
                verdict = "INVALID_TARGET_ID"
            elif counts[candidate] != 1:
                verdict = "DUPLICATE_CONTROL"
            elif not _FAQ_CONTEXT.search(candidate):
                verdict = "NONSEMANTIC_ID_REQUIRES_SEPARATE_ADAPTER_REVIEW"
            elif eligible_isolated_faq_disclosure(html, candidate):
                verdict = "CURRENT_BUTTON_POLICY_ELIGIBLE_NOT_AUTHORIZED"
            else:
                verdict = "UNSAFE_OR_AMBIGUOUS_BUTTON"
            items.append({
                "target_id": candidate,
                "eligibility": verdict,
                "action_authorized": False,
            })
        return {
            **denied,
            "status": "PASSIVE_INVENTORY_ONLY",
            "reason": None,
            "requested_url_sha256": sha256(requested_url.encode("utf-8")).hexdigest(),
            "final_url_sha256": sha256(final_url.encode("utf-8")).hexdigest(),
            "device": device,
            "observed_dom_sha256": sha256(encoded_html).hexdigest(),
            "candidate_count": len(items),
            "candidates": items,
            "details_summary_controls_unsupported": parser.summary_count,
            "nonbutton_disclosures_unsupported": parser.nonbutton_disclosures,
            "expanded_buttons_without_target_unsupported":
                parser.uncoupled_expanded_controls,
            "review_required": True,
            "automatic_target_selection": False,
            "limitation": (
                "Inventario de DOM local; IDs variam por URL e captura. "
                "Nenhum candidato autoriza clique, indexacao ou equivalencia "
                "com amostra fisica da AUD. Controles nao suportados exigem "
                "decisao e adaptador independente."
            ),
        }
    except (UnicodeError, ValueError, TypeError):
        return denied


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventario FAQ passivo, sem browser, rede ou clique")
    parser.add_argument("--html-file", type=Path, required=True)
    parser.add_argument("--requested-url", required=True)
    parser.add_argument("--final-url", required=True)
    parser.add_argument("--device", choices=("DESKTOP", "MOBILE"), required=True)
    args = parser.parse_args(argv)
    try:
        path = args.html_file
        if path.is_symlink() or not path.is_file():
            raise ValueError("not regular")
        size = path.stat().st_size
        if not 0 < size <= _MAX_HTML_BYTES:
            raise ValueError("outside limit")
        html = path.read_bytes()
        if len(html) != size:
            raise ValueError("changed while reading")
        result = inspect_faq_target_candidates(
            html.decode("utf-8"),
            requested_url=args.requested_url, final_url=args.final_url,
            device=args.device,
        )
    except (OSError, ValueError, UnicodeError):
        result = {
            "contract": _CONTRACT, "status": "NOT_VERIFIABLE",
            "reason": "HTML_FILE_NOT_READABLE",
            "candidates": [], "action_performed": False,
            "click_authorized": False, "provider_requests": 0,
            "audit_writes": 0,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASSIVE_INVENTORY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["inspect_faq_target_candidates", "main"]
