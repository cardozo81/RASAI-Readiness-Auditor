"""Bounded physical content map over the existing v1 parser trace.

Observes page titles, heading levels and already-selected v1 evidence without
reclassifying any occurrence or claiming SEO rankings / commercial truth.
"""
from __future__ import annotations

from collections import Counter
from html import unescape

from rasai.contextual_documents import stable_id

CONTRACT = "contextual-page-structure-v3"
MAX_HEADINGS = 48
MAX_TITLE = 320
MAX_HEADING = 600


def _scope(parser, node):
    chain = parser.ancestors(node)
    is_nav = any(n["tag"] in {"nav", "header", "footer", "menu"} or
                 n["attrs"].get("role") in {"navigation", "menu", "contentinfo", "menubar"}
                 for n in chain)
    is_main = any(n["tag"] in {"main", "article"} or n["attrs"].get("role") == "main"
                  for n in chain)
    return "NAVIGATION_OR_TEMPLATE" if is_nav else "MAIN_OR_ARTICLE" if is_main else "BODY_OR_UNDETERMINED"


def _observed_title(parser, node):
    if node["end"] is None:
        return None
    after_open = parser.source.find(">", node["start"], node["end"])
    before_close = parser.source.lower().rfind("</title", after_open + 1, node["end"])
    if after_open < 0 or before_close < after_open:
        return None
    return " ".join(unescape(parser.source[after_open + 1:before_close]).split())


def qualify_capture(capture, parser=None):
    result = dict(contract=CONTRACT, title=None, title_count=None, headings=[],
        heading_count=None, headings_omitted=None, evidence_categories={},
        coverage="MARKUP_NOT_AVAILABLE_ND",
        limitations=["NOT_COMPUTED_VISIBILITY_OR_INDEXATION", "TEXT_NOT_COMMERCIALLY_VERIFIED"])
    if parser is None:
        return result
    titles = [node for node in parser.nodes if node["tag"] == "title"]
    if len(titles) == 1:
        text = _observed_title(parser, titles[0])
        if text is not None:
            result["title"] = dict(text=text[:MAX_TITLE],
                truncated=len(text) > MAX_TITLE,
                text_range=dict(start=titles[0]["start"], end=titles[0]["end"],
                                unit="DECODED_HTML_CHARACTERS"),
                source_ref=capture["source_ref"], source_sha256=capture["source_sha256"])
    all_headings = []
    v1 = {row["ordinal"]: row["occurrence_id"] for row in capture["occurrences"]}
    for ordinal, node in enumerate(parser.nodes):
        if node["skip"] or node["tag"] not in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            continue
        text = parser.text(node) if node["last"] is not None else ""
        if not text:
            continue
        all_headings.append(dict(
            heading_id=stable_id(CONTRACT, capture["snapshot_id"], capture["source_sha256"], ordinal),
            occurrence_id=v1.get(ordinal), tag=node["tag"], scope=_scope(parser, node),
            text=text[:MAX_HEADING], truncated=len(text) > MAX_HEADING,
            text_range=dict(start=node["start"], end=node["end"],
                            unit="DECODED_HTML_CHARACTERS"),
            source_ref=capture["source_ref"], source_sha256=capture["source_sha256"],
            snapshot_id=capture["snapshot_id"], device=capture["device"]))
    result["heading_count"] = len(all_headings)
    result["headings_omitted"] = max(0, len(all_headings) - MAX_HEADINGS)
    result["title_count"] = len(titles)
    result["headings"] = all_headings[:MAX_HEADINGS]
    result["evidence_categories"] = dict(Counter(row["category"] for row in capture["occurrences"]))
    result["coverage"] = "CAPTURE_INSPECTED"
    if len(titles) > 1:
        result["limitations"].append("MULTIPLE_TITLE_ELEMENTS_INTENT_ND")
    if len(titles) == 1 and result["title"] is None:
        result["limitations"].append("TITLE_RANGE_OR_TEXT_NOT_OBSERVED_ND")
    if result["headings_omitted"]:
        result["limitations"].append("HEADING_LIMIT_PARTIAL")
    if capture["surface"] != "RENDERED_DOM":
        result["limitations"].append("RAW_HTML_FALLBACK_DOES_NOT_PROVE_LATE_DOM_ND")
    return result


def report_overlay(captures):
    overlays = [c.get("page_structure_overlay_v3") or qualify_capture(c) for c in captures]
    complete = bool(overlays) and all(o["heading_count"] is not None for o in overlays)
    counter = Counter()
    for overlay in overlays:
        counter.update(overlay["evidence_categories"])
    return dict(contract=CONTRACT,
        captures=[dict(page_id=c["page_id"], snapshot_id=c["snapshot_id"],
                       device=c["device"], source_ref=c["source_ref"],
                       source_sha256=c["source_sha256"],
                       **{key: overlay[key] for key in ("title", "title_count", "headings",
                          "heading_count", "headings_omitted", "coverage", "limitations")})
                  for c, overlay in zip(captures, overlays)],
        counts=dict(headings=sum(o["heading_count"] for o in overlays) if complete else None,
                    title_elements=sum(o["title_count"] for o in overlays) if complete else None,
                    headings_omitted=sum(o["headings_omitted"] for o in overlays) if complete else None,
                    evidence_categories=dict(counter)),
        coverage="CAPTURE_INSPECTED" if complete and all(o["coverage"] == "CAPTURE_INSPECTED"
                 for o in overlays) else "PARTIAL_OR_NOT_OBSERVED_ND",
        limitations=["HEADING_ALIGNMENT_REQUIRES_EDITORIAL_REVIEW",
                     "NO_VERIFICATION_OF_CLAIMS_DOCUMENTS_OR_RANKING"])
