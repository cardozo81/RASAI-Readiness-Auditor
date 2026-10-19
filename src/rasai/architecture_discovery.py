"""Canonical physical architecture classification shared across execution paths.

This is a pure assessment over already acquired evidence, not an HTTP probe.
The console's independent acquisition adapter must reuse this exact entrypoint.
"""
from __future__ import annotations

from dataclasses import dataclass

from rasai.domain import ArchitectureClassification
from rasai.javascript_spa import JavascriptSpaAnalyzer, StateComparison
from rasai.architecture_raw_signals import RawHtmlSignals, inspect_raw_html_signals

METHOD_VERSION = "architecture-observation-v1"


@dataclass(frozen=True)
class ArchitectureAssessment:
    architecture: ArchitectureClassification
    comparison: StateComparison | None
    limitation: str | None
    method_version: str = METHOD_VERSION
    raw_available: bool = False
    rendered_available: bool = False
    raw_signals: RawHtmlSignals | None = None


def assess_architecture(
    *,
    raw_html: str | None,
    rendered_html: str | None,
    quality_reason: str | None = None,
    analyzer: JavascriptSpaAnalyzer | None = None,
) -> ArchitectureAssessment:
    """Return a conservative classification; never fetch or persist data."""
    # In HTTP-only mode the DOM rendered by JavaScript has not been captured.
    # Keep classification UNKNOWN, but preserve bounded and content-free RAW
    # structure when that physical document was supplied to this assessor.
    partial = (
        inspect_raw_html_signals(raw_html)
        if raw_html is not None and (quality_reason or rendered_html is None)
        else None
    )
    if quality_reason:
        return ArchitectureAssessment(
            ArchitectureClassification.UNKNOWN, None, quality_reason,
            raw_available=raw_html is not None,
            rendered_available=rendered_html is not None,
            raw_signals=partial,
        )
    if raw_html is None or rendered_html is None:
        return ArchitectureAssessment(
            ArchitectureClassification.UNKNOWN, None, "RAW_OR_RENDERED_UNAVAILABLE",
            raw_available=raw_html is not None,
            rendered_available=rendered_html is not None,
            raw_signals=partial,
        )
    comparison = (analyzer or JavascriptSpaAnalyzer()).compare(raw_html, rendered_html)
    if not comparison.raw_main_content.strip() and not comparison.rendered_main_content.strip():
        # No material content: the original classifier could label an empty
        # document STATIC_OR_SSR; classification requires positive evidence.
        return ArchitectureAssessment(ArchitectureClassification.UNKNOWN, comparison, "MAIN_CONTENT_NOT_IDENTIFIED",
                                      raw_available=True, rendered_available=True)
    return ArchitectureAssessment(comparison.architecture, comparison, None,
                                  raw_available=True, rendered_available=True)
