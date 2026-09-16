"""Final console action-scope contract for nested operator screens.

Presentation/navigation only. Global destinations belong to the INÍCIO screen; nested
screens expose only actions that operate on the current entity/context plus Voltar.
No audit, scoring, provider, retry, cost or fulfillment rule is changed here.
"""
from __future__ import annotations

import builtins
from contextlib import contextmanager
from types import ModuleType
from typing import Any, Callable, Iterator


_GLOBAL_CONFIGURATION_LINES = frozenset(
    {
        "C. Configuração avançada / todas as variáveis",
        "C. Abrir catálogo completo de configuração",
    }
)
_EXIT_LINES = frozenset({"Q. Sair"})


def _filtered_text(text: str, forbidden_lines: frozenset[str]) -> str:
    """Remove forbidden action rows while preserving surrounding output."""
    lines = str(text).splitlines()
    kept = [line for line in lines if line.strip() not in forbidden_lines]
    result = "\n".join(kept)
    if str(text).endswith("\n") and result:
        result += "\n"
    return result


@contextmanager
def _scoped_io(
    state: Any,
    *,
    forbidden_lines: frozenset[str],
    blocked_keys: frozenset[str],
    blocked_message: str,
    blocked_fallback: str,
    rewrite_invalid: bool = False,
) -> Iterator[None]:
    original_print = builtins.print
    original_input = builtins.input

    def scoped_print(*args: Any, **kwargs: Any) -> None:
        rewritten: list[Any] = []
        for arg in args:
            if not isinstance(arg, str):
                rewritten.append(arg)
                continue
            text = _filtered_text(arg, forbidden_lines)
            if rewrite_invalid:
                text = text.replace("use R, P, I, V ou Q", "use R, P, I ou V")
            if text:
                rewritten.append(text)
        if rewritten:
            original_print(*rewritten, **kwargs)

    def scoped_input(prompt: str = "") -> str:
        raw = original_input(prompt)
        normalized = str(raw).strip().upper()
        if normalized in blocked_keys:
            if hasattr(state, "error"):
                state.error = blocked_message
            return blocked_fallback
        return raw

    builtins.print = scoped_print
    builtins.input = scoped_input
    try:
        yield
    finally:
        builtins.print = original_print
        builtins.input = original_input


def _wrap_integration_surface(fn: Callable[..., Any]) -> Callable[..., Any]:
    if bool(getattr(fn, "_rasai_context_actions_only", False)):
        return fn

    def wrapped(console_module: ModuleType, state: Any, *args: Any, **kwargs: Any):
        with _scoped_io(
            state,
            forbidden_lines=_GLOBAL_CONFIGURATION_LINES,
            blocked_keys=frozenset({"C"}),
            blocked_message=(
                "Acesso global de configuração disponível somente em "
                "INÍCIO > Todas as configurações."
            ),
            blocked_fallback="__GLOBAL_CONFIG_ONLY_AT_HOME__",
        ):
            return fn(console_module, state, *args, **kwargs)

    wrapped._rasai_context_actions_only = True  # type: ignore[attr-defined]
    wrapped._rasai_original = fn  # type: ignore[attr-defined]
    return wrapped


def _wrap_post_run_actions(fn: Callable[..., Any]) -> Callable[..., Any]:
    if bool(getattr(fn, "_rasai_context_actions_only", False)):
        return fn

    def wrapped(state: Any, *args: Any, **kwargs: Any):
        with _scoped_io(
            state,
            forbidden_lines=_EXIT_LINES,
            blocked_keys=frozenset({"Q"}),
            blocked_message="Sair está disponível somente no menu INÍCIO.",
            blocked_fallback="V",
        ):
            return fn(state, *args, **kwargs)

    wrapped._rasai_context_actions_only = True  # type: ignore[attr-defined]
    wrapped._rasai_original = fn  # type: ignore[attr-defined]
    return wrapped


def _wrap_reprocess_post_actions(fn: Callable[..., Any]) -> Callable[..., Any]:
    if bool(getattr(fn, "_rasai_context_actions_only", False)):
        return fn

    def wrapped(console_module: ModuleType, state: Any, *args: Any, **kwargs: Any):
        with _scoped_io(
            state,
            forbidden_lines=_EXIT_LINES,
            blocked_keys=frozenset({"Q"}),
            blocked_message="Sair está disponível somente no menu INÍCIO.",
            blocked_fallback="V",
            rewrite_invalid=True,
        ):
            return fn(console_module, state, *args, **kwargs)

    wrapped._rasai_context_actions_only = True  # type: ignore[attr-defined]
    wrapped._rasai_original = fn  # type: ignore[attr-defined]
    return wrapped


def _wrap_reprocess_confirmation(fn: Callable[..., Any]) -> Callable[..., Any]:
    if bool(getattr(fn, "_rasai_context_actions_only", False)):
        return fn

    def wrapped(console_module: ModuleType, state: Any, *args: Any, **kwargs: Any):
        with _scoped_io(
            state,
            forbidden_lines=frozenset(),
            blocked_keys=frozenset({"Q"}),
            blocked_message="Use V para voltar; Sair está disponível somente no menu INÍCIO.",
            blocked_fallback="__INVALID__",
        ):
            return fn(console_module, state, *args, **kwargs)

    wrapped._rasai_context_actions_only = True  # type: ignore[attr-defined]
    wrapped._rasai_original = fn  # type: ignore[attr-defined]
    return wrapped


def install(console_module: ModuleType) -> None:
    """Install after all other console presentation owners."""
    if getattr(console_module, "_rasai_submenu_action_scope", False):
        return

    from rasai import console_reprocess_final_refinements as reprocess
    from rasai import console_reprocess_parity as parity
    from rasai import integration_diagnostics_console as integrations

    integrations.integration_menu = _wrap_integration_surface(integrations.integration_menu)
    integrations._detail_menu = _wrap_integration_surface(integrations._detail_menu)

    console_module._post_run_actions = _wrap_post_run_actions(console_module._post_run_actions)

    reprocess._run_post_actions = _wrap_reprocess_post_actions(reprocess._run_post_actions)
    parity._run_post_actions = reprocess._run_post_actions

    reprocess._confirm_reprocess_with_feedback = _wrap_reprocess_confirmation(
        reprocess._confirm_reprocess_with_feedback
    )

    console_module._rasai_submenu_action_scope = True
