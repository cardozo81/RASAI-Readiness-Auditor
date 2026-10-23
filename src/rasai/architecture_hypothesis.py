"""Domain-independent, non-authoritative architecture hypotheses from RAW facts.

This is a consultative interpretation when the rendered DOM is unavailable.
It does not classify a site, modify persisted audits, or choose collectors.
The hypothesis never upgrades UNKNOWN to a verified classification.
"""
from __future__ import annotations

from dataclasses import dataclass

from rasai.architecture_raw_signals import RawHtmlSignals
from rasai.domain import ArchitectureClassification as Architecture


@dataclass(frozen=True, slots=True)
class ArchitectureHypothesis:
    """Uncalibrated low-confidence signal, separate from physical classification."""
    likely: Architecture | None
    alternatives: tuple[Architecture, ...]
    structure: str | None
    evidence: tuple[str, ...]
    confidence: str = "LOW"
    method_version: str = "architecture-hypothesis-v1"


def suggest_architecture_from_raw(signals: RawHtmlSignals | None) -> ArchitectureHypothesis | None:
    """Use only positive, bounded HTML evidence; never infer from a hostname.

    Missing DOM, frame loads and JavaScript execution prevent verification.
    A document embedding an iframe is not automatically a SPA: its own
    architecture may differ from that of the embedded document.
    """
    if signals is None or signals.status != "RAW_STRUCTURAL_SIGNALS_OBSERVED":
        return None
    scripts = signals.external_script_tags + signals.inline_script_tags
    frames = signals.iframe_tags

    if frames:
        evidence = ["IFRAME_ELEMENT_IN_RAW_HTML"]
        if signals.iframe_src_tags:
            evidence.append("IFRAME_SRC_DECLARED_NOT_FETCHED")
        if signals.iframe_srcdoc_tags:
            evidence.append("IFRAME_SRCDOC_DECLARED_NOT_EXECUTED")
        if signals.raw_main_text_present:
            evidence.append("HOST_RAW_MAIN_TEXT_PRESENT")
        return ArchitectureHypothesis(
            likely=None, alternatives=(), structure="EMBEDDED_FRAME_COMPOSITION",
            evidence=tuple(evidence),
        )

    if (not signals.raw_main_text_present and signals.app_root_marker_present
            and scripts):
        return ArchitectureHypothesis(
            likely=Architecture.CSR_SPA, alternatives=(Architecture.MIXED,),
            structure="JS_APPLICATION_SHELL",
            evidence=("APP_ROOT_MARKER", "SCRIPT_REFERENCES",
                      "SUBSTANTIVE_RAW_MAIN_NOT_PROVED"),
        )

    if signals.raw_main_text_present and signals.framework_attribute_present and scripts:
        return ArchitectureHypothesis(
            likely=Architecture.HYDRATED,
            alternatives=(Architecture.MIXED, Architecture.STATIC_OR_SSR),
            structure="SERVER_CONTENT_WITH_FRAMEWORK_SIGNALS",
            evidence=("RAW_MAIN_CONTENT_PRESENT", "FRAMEWORK_ATTRIBUTE", "SCRIPT_REFERENCES"),
        )

    if signals.raw_main_text_present and signals.h1_present:
        return ArchitectureHypothesis(
            likely=Architecture.STATIC_OR_SSR,
            alternatives=(Architecture.HYDRATED, Architecture.MIXED),
            structure="SERVER_CONTENT_PRESENT",
            evidence=("RAW_MAIN_CONTENT_PRESENT", "RAW_H1_PRESENT"),
        )
    return None


__all__ = ["ArchitectureHypothesis", "suggest_architecture_from_raw"]
