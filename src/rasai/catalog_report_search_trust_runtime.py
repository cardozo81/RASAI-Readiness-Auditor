"""Composition hook ensuring CAT-05 trust projection is the final report layer."""
from __future__ import annotations

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import catalog_report_final_refinements as refinements
    from rasai.catalog_report_search_trust import install as install_search_trust

    current = refinements.install_catalog_report_refinements
    if getattr(current, "_rasai_search_trust_runtime", False):
        install_search_trust()
        _INSTALLED = True
        return

    def install_catalog_report_refinements() -> None:
        current()
        install_search_trust()

    install_catalog_report_refinements._rasai_search_trust_runtime = True
    install_catalog_report_refinements._rasai_original = current
    refinements.install_catalog_report_refinements = install_catalog_report_refinements
    # Patch already-imported report modules immediately as well.
    install_search_trust()
    _INSTALLED = True


__all__ = ["install"]
