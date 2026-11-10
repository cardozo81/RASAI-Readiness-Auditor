"""Additive FAQ ARIA evidence from the *same* bounded captured-markup parser.

This is not a visibility/indexability assertion or a live DOM interaction.
V1 occurrences and v2 dispositions remain unchanged.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from rasai.contextual_documents import stable_id

CONTRACT = "contextual-faq-aria-overlay-v3"
MAX_ARIA_CONTROLS = 64
_ID = re.compile(r"^[^\s\x00-\x1f]{1,128}$")
_NAV_TAGS = {"nav", "header", "footer", "menu"}
_NAV_ROLES = {"navigation", "menu", "menubar", "contentinfo"}
_MENU_LABELS = {"menu", "produtos", "serviços", "servicos", "navegação", "navegacao"}


def _is_navigation(node):
    return node["tag"] in _NAV_TAGS or str(node["attrs"].get("role") or "").lower() in _NAV_ROLES


def qualify_capture(capture, parser=None):
    """One bounded overlay per physical capture; no changes to v1/v2 rows."""
    empty = dict(contract=CONTRACT, controls=[], counts=dict(controls=None,
        answer_present=None, not_observed_nd=None, ambiguous=None, excluded=None),
        coverage="MARKUP_NOT_AVAILABLE_ND", limitations=["NO_LIVE_EXPANSION_OR_RENDER_VISIBILITY"])
    if parser is None:
        return empty
    by_id = defaultdict(list)
    for ordinal, node in enumerate(parser.nodes):
        ident = node["attrs"].get("id")
        if isinstance(ident, str) and _ID.fullmatch(ident):
            by_id[ident].append((ordinal, node))
    v1 = {row["ordinal"]: row["occurrence_id"] for row in capture["occurrences"]}
    controls, candidates = [], []
    for ordinal, node in enumerate(parser.nodes):
        attrs = node["attrs"]
        if (node["skip"] or node["tag"] not in {"a", "button"} or
                str(attrs.get("role") or "").lower() != "button" or
                "aria-controls" not in attrs):
            continue
        candidates.append((ordinal, node))
    for ordinal, node in candidates[:MAX_ARIA_CONTROLS]:
        attrs = node["attrs"]
        chain = parser.ancestors(node)
        label = (parser.text(node) or str(attrs.get("aria-label") or "")).strip()[:600]
        expanded = attrs.get("aria-expanded")
        expanded = expanded.lower() if isinstance(expanded, str) else None
        target = attrs.get("aria-controls")
        target = target.strip() if isinstance(target, str) else ""
        nav = any(_is_navigation(n) for n in chain)
        main = any(n["tag"] in {"main", "article"} or n["attrs"].get("role") == "main" for n in chain)
        faq = any(re.search(r"(?:^|[\s_-])faq(?:$|[\s_-])|perguntas[-_ ]frequentes",
                            str(n["attrs"].get(key) or ""), flags=re.I)
                  for n in chain for key in ("id", "class"))
        status, basis, answer, panel_ref = "UNDETERMINED_ND", "EDITORIAL_INTENT_UNPROVEN", None, None
        if nav or label.casefold() in _MENU_LABELS:
            status, basis = "EXCLUDED_NAVIGATION", "NAVIGATION_CONTROL_OR_MENU"
        elif not label or not main and not faq:
            status, basis = "UNDETERMINED_ND", "CONTROL_WITHOUT_EDITORIAL_SCOPE"
        elif not _ID.fullmatch(target) or expanded not in {"true", "false"}:
            status, basis = "INVALID_OR_AMBIGUOUS_ND", "INVALID_ARIA_TARGET_OR_STATE"
        elif len(by_id[target]) > 1:
            status, basis = "INVALID_OR_AMBIGUOUS_ND", "DUPLICATE_TARGET_ID"
        elif not by_id[target]:
            status, basis = "NOT_OBSERVED_ND", "TARGET_NOT_PRESENT_IN_CAPTURE"
        else:
            panel_ordinal, panel = by_id[target][0]
            panel_ref = dict(ordinal=panel_ordinal, id=target,
                text_range=dict(start=panel["start"], end=panel["end"],
                                unit="DECODED_HTML_CHARACTERS"))
            if panel["end"] is None or any(_is_navigation(n) for n in parser.ancestors(panel)):
                status, basis = "INVALID_OR_AMBIGUOUS_ND", "PANEL_MALFORMED_OR_NAVIGATION"
            else:
                panel_text = parser.text(panel)
                if panel_text:
                    status, basis = "ANSWER_PRESENT_IN_DOM", "SAME_CAPTURE_ARIA_TARGET_WITH_TEXT"
                    answer = panel_text[:600]
                else:
                    status, basis = "PANEL_PRESENT_EMPTY_ND", "TARGET_PRESENT_WITHOUT_OBSERVED_ANSWER"
        controls.append(dict(
            id=stable_id(CONTRACT, capture["snapshot_id"], capture["source_sha256"], ordinal),
            occurrence_id=v1.get(ordinal), snapshot_id=capture["snapshot_id"],
            page_id=capture["page_id"], device=capture["device"], surface=capture["surface"],
            source_ref=capture["source_ref"], source_sha256=capture["source_sha256"],
            ordinal=ordinal, question=label, aria_controls=target,
            aria_expanded=expanded, text_range=dict(start=node["start"], end=node["end"],
                                                    unit="DECODED_HTML_CHARACTERS"),
            panel=panel_ref, answer=answer, status=status, basis=basis,
            limitations=["DOM_NOT_COMPUTED_VISIBILITY_OR_BOT_INDEXATION",
                         "EDITORIAL_FAQ_INTENT_NOT_INDEPENDENTLY_AUTHENTICATED"],
        ))
    counts = Counter(item["status"] for item in controls)
    return dict(contract=CONTRACT, controls=controls,
        counts=dict(controls=len(controls), answer_present=counts["ANSWER_PRESENT_IN_DOM"],
                    not_observed_nd=counts["NOT_OBSERVED_ND"],
                    ambiguous=counts["INVALID_OR_AMBIGUOUS_ND"] + counts["PANEL_PRESENT_EMPTY_ND"] + counts["UNDETERMINED_ND"],
                    excluded=counts["EXCLUDED_NAVIGATION"]),
        coverage="PARTIAL_CONTROL_LIMIT" if len(candidates) > MAX_ARIA_CONTROLS else "CAPTURE_INSPECTED",
        limitations=["NO_LIVE_EXPANSION_OR_RENDER_VISIBILITY"] +
                    (["CONTROL_LIMIT_PARTIAL"] if len(candidates) > MAX_ARIA_CONTROLS else []))


def report_overlay(captures):
    overlays = [capture.get("faq_aria_overlay_v3") or qualify_capture(capture) for capture in captures]
    complete = bool(overlays) and all(overlay["counts"]["controls"] is not None for overlay in overlays)
    fields = ("controls", "answer_present", "not_observed_nd", "ambiguous", "excluded")
    return dict(contract=CONTRACT, controls=[row for overlay in overlays for row in overlay["controls"]],
        counts={field: sum(overlay["counts"][field] for overlay in overlays) if complete else None
                for field in fields},
        coverage="CAPTURE_INSPECTED" if complete and all(o["coverage"] == "CAPTURE_INSPECTED" for o in overlays)
                 else "PARTIAL_OR_NOT_OBSERVED_ND",
        limitations=["ARIA_CLOSED_DOES_NOT_PROVE_MISSING_SITE_ANSWER",
                     "NO_COMPUTED_VISIBILITY_OR_LIVE_FETCH"])
