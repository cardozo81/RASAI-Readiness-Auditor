"""Dependency normalization for versioned system defaults.

System defaults are a lower-precedence layer. When a parent capability is explicitly off,
dependent capabilities cannot remain effectively on merely because a lower layer or the
canonical INI writer materialized their defaults into the process environment.
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Any, Iterable

from rasai.m23_cli import APDEX_ENABLED_ENV
from rasai.m25_cli import UX_ENABLED_ENV

_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def navigation_is_explicitly_disabled(names: Iterable[str] | None) -> bool:
    selected = set(names or ())
    if APDEX_ENABLED_ENV not in selected:
        return False
    navigation = (os.environ.get(APDEX_ENABLED_ENV) or "").strip().casefold()
    return navigation in _FALSE_VALUES


def normalize_apdex_environment_dependencies(
    state: Any,
    names: Iterable[str] | None,
) -> None:
    """Navigation OFF always makes the dependent Experience capability effectively OFF."""
    if not navigation_is_explicitly_disabled(names):
        return
    if hasattr(state, "apdex_experience"):
        state.apdex_experience = False


def install(console_module: ModuleType) -> None:
    """Wrap the console's M23 environment application at its final integration point."""
    if getattr(console_module, "_rasai_system_default_dependencies_installed", False):
        return

    original = console_module.apply_m23_environment_defaults

    def apply_m23_environment_defaults(state: Any, names: set[str] | None = None):
        suppress_experience = navigation_is_explicitly_disabled(names)
        previous_experience = os.environ.get(UX_ENABLED_ENV)
        normalize_apdex_environment_dependencies(state, names)

        # The canonical INI writer mirrors structured state into os.environ. On first
        # run this can materialize the lower-precedence Experience=true baseline even
        # when an incoming environment override has Navigation=false. Temporarily
        # project the only valid dependent state while M23 resolves its configuration;
        # the normal post-load sync will then persist the effective state for the
        # current process. No OS/User persistence is changed here.
        if suppress_experience:
            os.environ[UX_ENABLED_ENV] = "false"
        try:
            return original(state, names=names)
        finally:
            if suppress_experience:
                if previous_experience is None:
                    os.environ.pop(UX_ENABLED_ENV, None)
                else:
                    os.environ[UX_ENABLED_ENV] = previous_experience

    console_module.apply_m23_environment_defaults = apply_m23_environment_defaults
    console_module._rasai_system_default_dependencies_installed = True
