"""Complete persistence contract for the interactive console.

Saving the console configuration materializes every public non-sensitive setting into
``rasai-console.ini``. Explicit session/environment values win, then state projections,
then a persistable public runtime default. Settings without an effective value are still
listed as blank so the INI remains a complete inventory. Secrets are never written.
"""
from __future__ import annotations

import os
from typing import Any

from rasai.console_config import is_secret

_INSTALLED = False

# RASAI_CONFIG is an override selector, not a runtime value that should be created by a
# console save. Its EnvironmentSpec historically carries explanatory copy in ``default``
# ("rasai.toml opcional ..."). Materializing that text would turn an absent optional
# override into an explicit invalid path on the next process/load. Keep the key in the
# complete INI inventory, but blank unless the operator actually set it.
_EXPLICIT_ONLY_DEFAULTS = frozenset({"RASAI_CONFIG"})


def _public_nonsecret_specs() -> tuple[Any, ...]:
    """Return the fully composed operator-facing, non-secret configuration catalog."""
    from rasai import console_provider_environment as facade

    specs = facade.refresh_specs()
    return tuple(
        spec
        for spec in specs
        if not bool(getattr(spec, "sensitive", False)) and not is_secret(str(spec.name))
    )


def _effective_text(spec: Any, projected: dict[str, str]) -> str:
    """Resolve the value that a newly saved INI should reproduce safely."""
    name = str(spec.name)
    explicit_candidates = (os.environ.get(name), projected.get(name))
    for candidate in explicit_candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text

    if name in _EXPLICIT_ONLY_DEFAULTS:
        return ""

    default = getattr(spec, "default", None)
    if default is not None:
        text = str(default).strip()
        if text:
            return text
    return ""


def persisted_environment_values(state: Any) -> dict[str, str]:
    """Materialize every public non-secret setting, including safe effective defaults."""
    from rasai import console_settings as settings

    projected = settings._runtime_environment_projection(state)
    result = {
        str(spec.name): _effective_text(spec, projected)
        for spec in _public_nonsecret_specs()
    }
    return dict(sorted(result.items()))


def install() -> None:
    """Install the complete save projection without changing runtime configuration rules."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_settings as settings

    settings._persisted_environment_values = persisted_environment_values
    _INSTALLED = True
