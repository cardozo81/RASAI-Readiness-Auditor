"""Complete persistence contract for the interactive console.

Saving the console configuration materializes every public non-sensitive setting into
``rasai-console.ini``. Explicit session/environment values win, then state projections,
then the public runtime default. Settings without an effective value are still listed as
blank so the INI remains a complete inventory. Secrets are never written.
"""
from __future__ import annotations

import os
from typing import Any

from rasai.console_config import is_secret

_INSTALLED = False


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
    """Resolve the value that a newly saved INI should reproduce."""
    name = str(spec.name)
    for candidate in (
        os.environ.get(name),
        projected.get(name),
        getattr(spec, "default", None),
    ):
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text
    return ""


def persisted_environment_values(state: Any) -> dict[str, str]:
    """Materialize every public non-secret setting, including effective defaults."""
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
