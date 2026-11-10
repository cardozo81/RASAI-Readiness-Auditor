"""Explicit N:M documentary hypotheses with physical excerpt validation.

No equivalence to claim_source_verification.product_scope and no signed outcomes.
"""
from __future__ import annotations

from rasai.contextual_documents import digest, stable_id

APPLICABILITY = frozenset({"POTENTIALLY_APPLICABLE", "INSUFFICIENT_EVIDENCE",
                          "SCOPE_DEMONSTRATED", "PRODUCT_INCOMPATIBLE",
                          "VERSION_OR_EFFECTIVITY_INCOMPATIBLE", "POSSIBLE_CONTRADICTION"})


def evidence_span(document: dict, *, page: int, start: int, end: int, quote: str) -> dict:
    if (document["status"] != "DOCUMENT_COLLECTED" or not quote
            or digest(document["text"].encode()) != document["text_sha256"]
            or type(start) is not int or type(end) is not int
            or not 0 <= start < end <= len(document["text"])
            or document["text"][start:end] != quote
            or not any(p["page"] == page and p["start"] <= start < end <= p["end"] for p in document["pages"])):
        raise ValueError("excerpt is not physically bound to derived document text")
    return {"document_id": document["document_id"], "text_sha256": document["text_sha256"],
            "page": page, "start": start, "end": end, "quote": quote}


def relate(*, occurrence_id: str, page_id: str, product_candidate: str | None,
           document: dict, spans: list[dict], claim_literal: str | None = None,
           version_observed: str | None = None, effective_observed: str | None = None,
           applicability: str = "INSUFFICIENT_EVIDENCE", basis: str = "OPERATOR_HYPOTHESIS") -> dict:
    """One edge per occurrence/product/document/version/claim, allowing N:M.

    The caller supplies explicit interpretations. SCOPE_DEMONSTRATED means only
    that supplied product/version/date literals appear in selected document
    excerpts, never that a commercial claim was independently authenticated.
    """
    if applicability not in APPLICABILITY or basis not in {"OPERATOR_HYPOTHESIS", "OBSERVED_LITERAL"}:
        raise ValueError("unrecognized advisory relationship")
    checked = [evidence_span(document, page=s["page"], start=s["start"], end=s["end"], quote=s["quote"]) for s in spans]
    if any(s != c for s, c in zip(spans, checked)):
        raise ValueError("excerpt hash or document identity mismatch")
    if applicability != "INSUFFICIENT_EVIDENCE" and not checked:
        raise ValueError("applicability requires physical documentary basis")
    if applicability == "SCOPE_DEMONSTRATED":
        joined = "\n".join(s["quote"] for s in checked)
        if (basis != "OBSERVED_LITERAL" or not product_candidate
                or any(value and value not in joined for value in (product_candidate, version_observed, effective_observed))):
            raise ValueError("scope literals absent from evidence")
    values = dict(occurrence_id=occurrence_id, page_id=page_id, product_candidate=product_candidate,
                  document_id=document["document_id"], version_observed=version_observed,
                  effective_observed=effective_observed, claim_literal=claim_literal,
                  applicability=applicability, basis=basis, excerpts=checked,
                  claim_state="CLAIM_UNVERIFIED_EXTERNAL", independent_verification=False)
    return {"relationship_id": stable_id(values), **values}
