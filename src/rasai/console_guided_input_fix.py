"""Keep guided configuration prompts visible under the console input wrapper.

The final console information-architecture layer temporarily replaces ``builtins.input``
so buffered presentation text is flushed before each prompt.  A function signature such
as ``input_fn=input`` captures the pre-wrapper input callable at import time and bypasses
that mechanism.  Closed-domain choices can therefore become invisible even though the
selection code is running.

This module is presentation-only.  It resolves the input callable at call time and
rebinds the public guided prompt aliases used by the canonical configuration surfaces.
"""
from __future__ import annotations

import builtins
from typing import Any, Callable


def _runtime_prompt_guided_value(
    spec: Any,
    input_fn: Callable[[str], str] | None = None,
) -> str | None:
    """Prompt a closed domain using the input callable active at interaction time."""
    from rasai import console_configuration_guidance as guidance

    if not spec.accepted:
        raise ValueError("variável não possui domínio fechado conhecido")
    reader = builtins.input if input_fn is None else input_fn
    if str(spec.value_type).casefold() in {"lista csv", "lista", "csv"}:
        return guidance._multi_choice(spec, reader)
    return guidance._single_choice(spec, reader)


def install() -> None:
    """Install the runtime-resolved guided prompt in every active console facade."""
    from rasai import console_configuration_guidance as guidance

    guidance.prompt_guided_value = _runtime_prompt_guided_value

    # Keep configuration facades synchronized so every variable with a known domain behaves alike.
    try:
        from rasai import console_provider_environment as provider_environment

        provider_environment.prompt_guided_value = _runtime_prompt_guided_value
    except ImportError:
        pass
