"""Compose current runtime contract adapters at public entrypoints.

AUTO provider membership and PageSpeed/Lighthouse category ownership live in their
canonical runtime modules. This adapter composes only the current specialist runtime
and console behaviors that remain outside those owners.
"""
from __future__ import annotations

_RUNTIME_INSTALLED = False
_CONSOLE_INSTALLED = False


def install_runtime_contract_compatibility() -> None:
    """Install the current non-console specialist runtime hooks."""
    global _RUNTIME_INSTALLED
    if _RUNTIME_INSTALLED:
        return

    from rasai.documented_contract_reconciliation import _install_m24_fallback_telemetry_fix

    _install_m24_fallback_telemetry_fix()
    _RUNTIME_INSTALLED = True


def install_console_runtime_contract_compatibility() -> None:
    """Install current console-only adapters after console extensions compose."""
    global _CONSOLE_INSTALLED
    install_runtime_contract_compatibility()
    if _CONSOLE_INSTALLED:
        return

    from rasai.documented_contract_reconciliation import (
        _install_console_ai_selector,
        _install_console_auto_capability_filter,
        _install_console_search_content_comparison,
    )

    # Capability projection is still console-specific.  Credential/model validity
    # remains independent from AUTO-pool membership; the execution router itself is
    # already canonical in provider_runtime_policy.
    _install_console_auto_capability_filter()
    _install_console_ai_selector()
    _install_console_search_content_comparison()
    _CONSOLE_INSTALLED = True
