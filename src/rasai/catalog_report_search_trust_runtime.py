"""Composition hook ensuring CAT-03/CAT-05 trust projections are final report layers."""
from __future__ import annotations

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import catalog_report_final_refinements as refinements
    from rasai.catalog_report_search_trust import install as install_search_trust
    from rasai.semantic_coherence_reporting import install as install_semantic_coherence_reporting

    current = refinements.install_catalog_report_refinements
    if getattr(current, "_rasai_report_trust_runtime", False):
        install_semantic_coherence_reporting()
        install_search_trust()
        _INSTALLED = True
        return

    def install_catalog_report_refinements() -> None:
        current()
        # CAT-03 semantic/context provenance must wrap the final base evidence renderer.
        install_semantic_coherence_reporting()
        # CAT-05 scope/source state is applied last and only touches Search Intelligence.
        install_search_trust()

    install_catalog_report_refinements._rasai_report_trust_runtime = True
    install_catalog_report_refinements._rasai_original = current
    refinements.install_catalog_report_refinements = install_catalog_report_refinements
    # Patch already-imported report modules immediately as well.
    install_semantic_coherence_reporting()
    install_search_trust()
    _INSTALLED = True


__all__ = ["install"]
