"""Passive document observations. No collectors, providers, review receipts or scoring."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from html.parser import HTMLParser
import ipaddress
import json
import re
from urllib.parse import urlsplit

from rasai.domain import PageSnapshot
from rasai.extraction import ContentExtractor
from rasai.url_utils import normalized_origin, resolve_http_url

CONTRACT = "contextual-documents-v1"
REFERENCE_STATES = frozenset({"REFERENCED_ONLY", "DOCUMENT_COLLECTED", "NOT_ACCESSIBLE", "NOT_VERIFIED"})
_DOCUMENT = re.compile(r"condi[çc][õo]es|contrat|regulamento|cobertura|pol[ií]tica|anexo|\.pdf(?:\b|$)", re.I)


class _ReferenceContext(HTMLParser):
    """Supplement canonical extraction with literal href and adjacent token context.

    Captured markup is observable, not proof of computed visibility. Script,
    style and template payloads are excluded from documentary text.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []
        self.active = None
        self.skip = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript", "svg"}:
            self.skip.append(tag)
        if not self.skip and tag == "a":
            self.active = (dict(attrs).get("href"), len(self.parts))

    def handle_endtag(self, tag):
        if self.skip:
            if tag == self.skip[-1]:
                self.skip.pop()
            return
        if tag == "a" and self.active is not None:
            href, start = self.active
            self.links.append((href, start, len(self.parts)))
            self.active = None

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(" ".join(data.split()))


@dataclass(frozen=True)
class DiscoveryLimits:
    max_bytes: int = 2_000_000
    max_occurrences: int = 500
    context_chars: int = 400

    def __post_init__(self) -> None:
        if not (1 <= self.max_bytes <= 2_000_000 and 1 <= self.max_occurrences <= 500
                and 1 <= self.context_chars <= 400):
            raise ValueError("discovery limits outside policy")


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def stable_id(*values: object) -> str:
    return digest(json.dumps(values, ensure_ascii=False, sort_keys=True).encode())


def reference_url(base: str, href: str) -> tuple[str | None, str]:
    """Classify references without DNS, navigation or authorization inference."""
    if "\\" in href or any(ord(c) < 32 or ord(c) == 127 for c in href):
        return None, "INVALID_REFERENCE"
    url = resolve_http_url(base, href)
    if url is None:
        return None, "INVALID_REFERENCE"
    host = urlsplit(url).hostname or ""
    try:
        if not ipaddress.ip_address(host).is_global:
            return url, "UNSAFE_ADDRESS"
    except ValueError:
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return url, "UNSAFE_ADDRESS"
    if normalized_origin(url) != normalized_origin(base):
        return url, "CROSS_ORIGIN_NOT_AUTHORIZED"
    return url, "REFERENCE_ONLY_NO_EGRESS"


def discover_references(*, audit_id: str, snapshot: PageSnapshot, original: bytes | None,
                        artifact_ref: str | None, surface: str,
                        limits: DiscoveryLimits = DiscoveryLimits()) -> dict:
    """Explicit source selection; repeated anchors retain separate occurrence IDs.

    Anchor context uses the canonical extractor's nearest captured text block.
    It is advisory proximity, never product applicability or rendered visibility.
    """
    if surface not in {"RENDERED_DOM", "RAW_HTML_FALLBACK", "NOT_CAPTURED"}:
        raise ValueError("unknown observed surface")
    result = {"contract": CONTRACT, "audit_id": audit_id, "page_id": snapshot.page_id,
              "snapshot_id": snapshot.snapshot_id, "device": snapshot.device.value,
              "captured_at": snapshot.captured_at.isoformat(), "requested_url": snapshot.requested_url,
              "final_url_observed": snapshot.final_url, "surface": surface,
              "artifact_ref": artifact_ref, "source_sha256": digest(original) if original is not None else None,
              "occurrences": [], "limitations": [], "limits": asdict(limits)}
    if surface != "RENDERED_DOM":
        result["limitations"].append("LATE_SPA_REFERENCES_NOT_CAPTURED_ND")
    if original is None or surface == "NOT_CAPTURED":
        result["limitations"].append("SOURCE_NOT_CAPTURED_ND")
        return result
    if len(original) > limits.max_bytes:
        result["limitations"].append("SOURCE_BYTE_LIMIT_ND")
        return result
    from rasai.acquisition import decode_captured_text
    html = decode_captured_text(original)
    page = ContentExtractor().extract(html)
    context_parser = _ReferenceContext()
    context_parser.feed(html)
    context_parser.close()
    base = snapshot.final_url or snapshot.requested_url
    candidates = []
    for href, start, end in context_parser.links:
        # All anchors are observable candidates; no PDF format assertion by suffix.
        text = " ".join(context_parser.parts[start:end])
        context = " ".join(context_parser.parts[max(0, start - 1):end + 1])
        candidates.append(("ANCHOR", href, text, context))
    for block in page.text_blocks:
        if _DOCUMENT.search(block):
            candidates.append(("TEXT_MENTION", None, block, block))
    for index, (kind, href, text, context) in enumerate(candidates[:limits.max_occurrences]):
        url, policy = reference_url(base, href) if href is not None else (None, "TEXT_ONLY")
        result["occurrences"].append({
            "occurrence_id": stable_id(audit_id, snapshot.snapshot_id, snapshot.device.value,
                                       result["source_sha256"], kind, index),
            "document_candidate_id": stable_id(url) if url else None,
            "ordinal": index, "kind": kind, "href_literal": href,
            "resolved_url": url, "url_policy": policy,
            "text": text[:limits.context_chars], "context": context[:limits.context_chars],
            "text_truncated": len(text) > limits.context_chars,
            "context_truncated": len(context) > limits.context_chars,
            "reference_state": "REFERENCED_ONLY" if url else "NOT_VERIFIED",
            "applicability": "INSUFFICIENT_EVIDENCE",
            "document_final_url_observed": None,
        })
    if len(candidates) > limits.max_occurrences:
        result["limitations"].append("OCCURRENCE_LIMIT_PARTIAL")
    return result
