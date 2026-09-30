"""Compatibility adapter for versioned system defaults.

CAT-06 (Navigation Apdex) and CAT-07 (Experience Apdex) are independent execution
capabilities.  Older releases treated Navigation as a parent and forcibly disabled
Experience when Navigation was OFF.  The public configuration API remains here so
entrypoint composition and older imports stay stable, but no cross-capability
normalization is performed.
"""
from __future__ import annotations

from types import ModuleType
from typing import Any, Iterable


def navigation_is_explicitly_disabled(names: Iterable[str] | None) -> bool:
    """Deprecated compatibility predicate.

    It no longer drives dependency behavior because CAT-07 can execute without CAT-06.
    """
    return False


def normalize_apdex_environment_dependencies(
    state: Any,
    names: Iterable[str] | None,
) -> None:
    """No-op compatibility hook; Apdex domains are independently configurable."""
    del state, names


def install(console_module: ModuleType) -> None:
    """Mark the compatibility layer without rewriting the console resolver."""
    if getattr(console_module, "_rasai_system_default_dependencies_installed", False):
        return
    console_module._rasai_system_default_dependencies_installed = True
