"""Uniform input contract for editable fields in the interactive console.

Navigation prompts (Escolha, Número/ID, ENTER) remain owned by their menus. This module
is only for values that can change session/configuration state.
"""
from __future__ import annotations

from typing import Callable


class EditCancelled(Exception):
    """Raised when the operator explicitly abandons an edit before commit."""


def _display_current(current: object | None) -> str:
    if current is None:
        return ""
    text = str(current)
    return f" [{text if text else 'vazio'}]"


def prompt_text(
    label: str,
    *,
    current: object | None = None,
    input_fn: Callable[[str], str] | None = None,
    empty_keeps_current: bool = True,
) -> str:
    prompt = f"{label}{_display_current(current)} [V=voltar sem salvar]: "
    reader = input if input_fn is None else input_fn
    raw = reader(prompt)
    if raw.strip().upper() == "V":
        raise EditCancelled()
    if empty_keeps_current and not raw.strip() and current is not None:
        return str(current)
    return raw.strip()


def prompt_secret(
    label: str,
    *,
    input_fn: Callable[[str], str],
) -> str:
    raw = input_fn(f"{label} [V=voltar sem salvar]: ")
    if raw.strip().upper() == "V":
        raise EditCancelled()
    return raw


def prompt_number(
    label: str,
    current: float | int,
    *,
    input_fn: Callable[[str], str] | None = None,
    integer: bool = False,
) -> float | int:
    raw = prompt_text(label, current=current, input_fn=input_fn)
    return int(raw) if integer else float(raw)


def prompt_yes_no(
    label: str,
    current: bool,
    *,
    input_fn: Callable[[str], str] | None = None,
) -> bool:
    suffix = "S/n" if current else "s/N"
    reader = input if input_fn is None else input_fn
    raw = reader(f"{label} [{suffix}] [V=voltar sem salvar]: ").strip().casefold()
    if raw == "v":
        raise EditCancelled()
    if not raw:
        return current
    if raw in {"s", "sim", "y", "yes", "1", "true", "on"}:
        return True
    if raw in {"n", "nao", "não", "no", "0", "false", "off"}:
        return False
    raise ValueError("responda S, N ou V")


__all__ = [
    "EditCancelled",
    "prompt_number",
    "prompt_secret",
    "prompt_text",
    "prompt_yes_no",
]
