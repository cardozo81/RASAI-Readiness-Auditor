"""Observed markup projection, not a crawler, visibility detector or semantic engine.

Offsets address decoded source HTML characters, never browser pixels. Vocabulary
is only a candidate signal. No documents, URLs or instructions are executed.
"""
from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

from rasai.contextual_documents import _DOCUMENT, digest, reference_url, stable_id
from rasai.domain import PageSnapshot

CONTRACT = "contextual-content-v1"
MAX_BYTES = 2_000_000
MAX_OCCURRENCES = 500
MAX_NODES = 20_000
TEXT_CHARS = 600
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_SKIP = frozenset({"script", "style", "template", "noscript", "svg", "head"})
_BLOCK = frozenset({"p", "h1", "h2", "h3", "h4", "li"})
_SOCIAL = frozenset({"facebook.com", "instagram.com", "linkedin.com", "youtube.com",
                     "twitter.com", "x.com", "tiktok.com"})
_COMMERCIAL = re.compile(r"\b(produto|plano|seguro|comprar|contratar|oferta|preço)\b", re.I)


class _Markup(HTMLParser):
    """Bounded structural supplement to canonical LinkObservation/text_blocks.

    Those objects discard ancestor/attribute/occurrence offsets, so they cannot
    establish menu/footer or a physical details-summary relationship afterward.
    Unclosed or mismatched nodes are retained only with explicit limitations.
    """
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.source = html
        self.lines = [0]
        for match in re.finditer("\n", html):
            self.lines.append(match.end())
        self.nodes, self.stack, self.tokens = [], [], []
        self.malformed = False

    def source_offset(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if len(self.nodes) >= MAX_NODES or len(self.stack) >= 128:
            raise ValueError("markup structural limit")
        values = dict(attrs)
        parent = self.stack[-1] if self.stack else None
        node = dict(tag=tag, attrs=values, parent=parent, start=self.source_offset(), end=None,
                    first=len(self.tokens), last=None,
                    skip=tag in _SKIP or bool(parent is not None and self.nodes[parent]["skip"]))
        self.nodes.append(node)
        if tag not in _VOID:
            self.stack.append(len(self.nodes) - 1)
        else:
            node.update(end=node["start"] + len(self.get_starttag_text()), last=len(self.tokens))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        found = next((i for i in range(len(self.stack) - 1, -1, -1)
                      if self.nodes[self.stack[i]]["tag"] == tag), None)
        if found is None:
            self.malformed = True
            return
        if found != len(self.stack) - 1:
            self.malformed = True
        for index in self.stack[found:]:
            # End-tag whitespace is literal source, not len(tag)+3.
            self.nodes[index].update(last=len(self.tokens), end=(
                self.source.find(">", self.source_offset()) + 1
                if self.nodes[index]["tag"] == tag else None))
        del self.stack[found:]

    def handle_data(self, data):
        if self.stack and not self.nodes[self.stack[-1]]["skip"] and data.strip():
            if len(self.tokens) >= MAX_NODES:
                raise ValueError("markup token limit")
            self.tokens.append(data)

    def text(self, node):
        return " ".join(" ".join(self.tokens[node["first"]:node["last"]]).split())

    def ancestors(self, node):
        result = [node]
        while result[-1]["parent"] is not None:
            result.append(self.nodes[result[-1]["parent"]])
        return result


def observe_content(*, audit_id: str, snapshot: PageSnapshot, original: bytes | None,
                    source_ref: str | None, surface: str) -> dict:
    if surface not in {"RENDERED_DOM", "RAW_HTML_FALLBACK", "NOT_CAPTURED"}:
        raise ValueError("unknown captured surface")
    result = dict(contract=CONTRACT, audit_id=audit_id, page_id=snapshot.page_id,
                  snapshot_id=snapshot.snapshot_id, device=snapshot.device.value,
                  captured_at=snapshot.captured_at.isoformat(), surface=surface,
                  source_ref=source_ref, source_sha256=digest(original) if original is not None else None,
                  requested_url=snapshot.requested_url, final_url_observed=snapshot.final_url,
                  occurrences=[], limitations=["CAPTURED_MARKUP_NOT_COMPUTED_VISIBILITY"],
                  counts={key: None for key in ("observed_occurrences", "distinct_destinations",
                          "potentially_documentary", "unknown", "omitted")})
    if surface != "RENDERED_DOM":
        result["limitations"].append("LATE_RENDERING_NOT_CAPTURED_ND")
    if original is None or surface == "NOT_CAPTURED":
        result["limitations"].append("SOURCE_NOT_CAPTURED_ND")
        return result
    if len(original) > MAX_BYTES:
        result["limitations"].append("SOURCE_BYTE_LIMIT_ND")
        return result
    from rasai.acquisition import decode_captured_text
    html = decode_captured_text(original)
    parser = _Markup(html)
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, RecursionError):
        result["limitations"].append("STRUCTURAL_LIMIT_ND")
        return result
    if parser.stack or parser.malformed:
        result["limitations"].append("MALFORMED_MARKUP_PARTIAL")
    for node in parser.nodes:
        if node["last"] is None:
            node.update(last=len(parser.tokens))
    base = snapshot.final_url or snapshot.requested_url
    candidates = []
    # Only a closed <details><summary> relationship establishes this FAQ pair.
    pairs = {}
    summaries, images = {}, {}
    for node in parser.nodes:
        if node["tag"] == "summary":
            summaries.setdefault(node["parent"], []).append(node)
        if node["tag"] == "img":
            alt = node["attrs"].get("alt")
            images.setdefault(node["parent"], []).append(alt[:TEXT_CHARS] if alt is not None else None)
    for index, node in enumerate(parser.nodes):
        if node["tag"] != "summary" or node["parent"] is None or node["end"] is None:
            continue
        parent = parser.nodes[node["parent"]]
        if parent["tag"] != "details" or parent["end"] is None or not parser.text(node):
            continue
        siblings = summaries[node["parent"]]
        if len(siblings) != 1:
            continue
        answer = " ".join(" ".join(parser.tokens[node["last"]:parent["last"]]).split())
        pairs[node["parent"]] = (index, answer)
    for index, node in enumerate(parser.nodes):
        tag = node["tag"]
        if node["skip"] or tag not in (_BLOCK | {"a", "button", "summary"}):
            continue
        chain = parser.ancestors(node)
        # Suppress nested block duplicates; anchors retain their own occurrence.
        if tag in _BLOCK and any(n["tag"] in _BLOCK for n in chain[1:]):
            continue
        text = parser.text(node)
        attrs = node["attrs"]
        href = attrs.get("href") if tag == "a" else None
        if not text and href is None and tag != "button":
            continue
        url, policy = reference_url(base, href) if isinstance(href, str) and len(href) <= 4096 else (None, "TEXT_ONLY_OR_OVER_LIMIT")
        family = {n["tag"] for n in chain}
        roles = {n["attrs"].get("role") for n in chain}
        category, basis = "UNKNOWN", "NO_STRUCTURAL_EVIDENCE"
        signals = [name for name, value in (("href", href), ("text", text)) if value and _DOCUMENT.search(value)]
        detail = next((n for n in chain if n["tag"] == "details"), None)
        detail_index = node["parent"] if tag == "summary" else None
        pair = pairs.get(detail_index)
        if "footer" in family or "contentinfo" in roles:
            category, basis = "FOOTER", "FOOTER_ANCESTOR"
        elif "nav" in family or "navigation" in roles or "menu" in roles:
            category, basis = "NAVIGATION", "NAVIGATION_ANCESTOR"
        elif url and any((urlsplit(url).hostname or "").lower() == h or
                         (urlsplit(url).hostname or "").lower().endswith("." + h) for h in _SOCIAL):
            category, basis = "SOCIAL", "KNOWN_DESTINATION_HOST_ONLY"
        elif tag == "summary" and pair:
            category, basis = "FAQ_QUESTION", "PHYSICAL_DETAILS_SUMMARY"
        elif href is not None and (not href or href.startswith("#") or not url):
            category, basis = "FRAGMENT_ACTION", "LITERAL_HREF_SCHEME_OR_FRAGMENT"
        elif tag == "button" or attrs.get("role") == "button":
            category, basis = "CTA", "BUTTON_ELEMENT_OR_ROLE"
        elif signals:
            category, basis = "DOCUMENT_REFERENCE" if href is not None else "TEXT_MENTION", "LEXICAL_DOCUMENT_CANDIDATE_ONLY"
        elif _COMMERCIAL.search(text) and ("main" in family or "article" in family or "main" in roles):
            category, basis = "COMMERCIAL_CANDIDATE", "MAIN_STRUCTURE_AND_LEXICAL_CANDIDATE"
        elif "main" in family or "article" in family or "main" in roles:
            category, basis = "MAIN_CONTENT", "MAIN_ANCESTOR"
        limitations = ["DESTINATION_NOT_VISITED", "DOCUMENT_NOT_AUTHENTICATED"] if href is not None else []
        if node["end"] is None:
            limitations.append("UNCLOSED_NODE_RANGE_ND")
        if tag == "summary" and pair and not pair[1]:
            limitations.append("FAQ_ANSWER_NOT_OBSERVED_ND")
        if tag == "summary" and pair:
            limitations.append("DETAILS_FAQ_EDITORIAL_CANDIDATE")
        if len(text) > TEXT_CHARS:
            limitations.append("TEXT_TRUNCATED")
        if href is not None and len(href) > 4096:
            limitations.append("HREF_TRUNCATED_URL_ND")
        parent = parser.nodes[node["parent"]] if node["parent"] is not None else node
        context = parser.text(parent)
        oid = stable_id(CONTRACT, audit_id, snapshot.snapshot_id, snapshot.device.value,
                        result["source_sha256"], index)
        occurrence = dict(occurrence_id=oid, ordinal=index, category=category, category_basis=basis,
                          limitations=limitations, href_literal=href[:4096] if href is not None else None, resolved_url=url, url_policy=policy,
                          anchor_text=text[:TEXT_CHARS] if tag == "a" else None,
                          text=text[:TEXT_CHARS], aria_label=attrs["aria-label"][:TEXT_CHARS] if attrs.get("aria-label") is not None else None,
                          alternative_text=images.get(index, [])[:20],
                          context=context[:TEXT_CHARS], context_truncated=len(context) > TEXT_CHARS,
                          text_range=dict(start=node["start"], end=node["end"], unit="DECODED_HTML_CHARACTERS"),
                          documentary_signals=signals, faq_question_ref=None,
                          faq_answer_observed=bool(pair[1]) if pair else None)
        candidates.append(occurrence)
        if pair and pair[1] and category == "FAQ_QUESTION":
            candidates.append(dict(occurrence, occurrence_id=stable_id(oid, "answer"),
                category="FAQ_ANSWER", category_basis="SAME_CLOSED_DETAILS_AFTER_SUMMARY",
                text=pair[1][:TEXT_CHARS], anchor_text=None, href_literal=None, resolved_url=None,
                faq_question_ref=oid, faq_answer_observed=True,
                text_range=dict(start=node["end"], end=detail["end"], unit="DECODED_HTML_CHARACTERS"),
                limitations=["TEXT_TRUNCATED"] if len(pair[1]) > TEXT_CHARS else []))
    counts = Counter(o["category"] for o in candidates)
    if not candidates:
        result["limitations"].append("OBSERVABLE_CONTEXT_NOT_FOUND_ND")
        return result
    result["counts"] = dict(observed_occurrences=len(candidates),
        distinct_destinations=len({o["resolved_url"] for o in candidates if o["resolved_url"]}),
        potentially_documentary=sum(bool(o["documentary_signals"]) for o in candidates),
        unknown=counts["UNKNOWN"], omitted=max(0, len(candidates) - MAX_OCCURRENCES))
    # Keep late main/FAQ/document candidates ahead of template navigation.
    selected = sorted(enumerate(candidates), key=lambda item:
        (item[1]["category"] in {"NAVIGATION", "FOOTER", "SOCIAL", "UNKNOWN"}, item[0]))[:MAX_OCCURRENCES]
    result["occurrences"] = [o for _, o in sorted(selected)]
    if result["counts"]["omitted"]:
        result["limitations"].append("OCCURRENCE_LIMIT_PARTIAL")
    return result
