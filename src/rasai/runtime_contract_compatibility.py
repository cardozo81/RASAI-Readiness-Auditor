"""Compose runtime compatibility hooks that are not yet fully native contracts.

AUTO provider membership remains canonical in the provider runtime.  PageSpeed/
Lighthouse transport is additionally guarded here because older console settings and
profiles may still contain the obsolete ``agentic-browsing`` transport token; the guard
normalizes those settings before any PageSpeed request is made.
"""
from __future__ import annotations

_RUNTIME_INSTALLED = False
_CONSOLE_INSTALLED = False


def install_runtime_contract_compatibility() -> None:
    """Install non-console compatibility hooks that are not native yet."""
    global _RUNTIME_INSTALLED
    if _RUNTIME_INSTALLED:
        return

    from rasai.lighthouse_transport_contract import install_lighthouse_transport_contract
    from rasai.documented_contract_reconciliation import (
        _install_ai_cost_report_fix,
        _install_ai_usage_presentation_fix,
        _install_crawling_capture_wording_fix,
        _install_m24_fallback_telemetry_fix,
        _install_scoring_wording_fix,
        _install_search_comparison_guidance,
    )

    # Run after runtime_completion_extensions so stale five-category defaults are
    # overridden before the public CLI/console starts executing audits.
    install_lighthouse_transport_contract()
    _install_ai_cost_report_fix()
    _install_ai_usage_presentation_fix()
    _install_scoring_wording_fix()
    _install_crawling_capture_wording_fix()
    _install_search_comparison_guidance()
    _install_m24_fallback_telemetry_fix()
    _RUNTIME_INSTALLED = True


def install_console_runtime_contract_compatibility() -> None:
    """Install remaining console-only adapters after console extensions compose."""
    global _CONSOLE_INSTALLED
    install_runtime_contract_compatibility()
    if _CONSOLE_INSTALLED:
        return

    from rasai.documented_contract_reconciliation import (
        _install_console_ai_selector,
        _install_console_auto_capability_filter,
        _install_console_search_content_comparison,
    )

    # Capability projection is still console-specific. Credential/model validity
    # remains independent from AUTO-pool membership; the execution router itself is
    # already canonical in provider_runtime_policy.
    _install_console_auto_capability_filter()
    _install_console_ai_selector()
    _install_console_search_content_comparison()
    _CONSOLE_INSTALLED = True
