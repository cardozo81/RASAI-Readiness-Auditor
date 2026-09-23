"""Canonical confirmation contract for the interactive console."""
from __future__ import annotations

from typing import Callable

from rasai.console_ui import destructive_text, title_text


def confirm_continue(
    action_label: str,
    *,
    back_label: str = "Voltar sem continuar",
    input_fn: Callable[[str], str] | None = None,
    show_options: bool = True,
) -> bool:
    """Confirm a non-destructive advance with the canonical C/V contract."""
    reader = input if input_fn is None else input_fn
    if show_options:
        print(f"C. {action_label}")
        print(f"V. {back_label}")
    while True:
        raw = reader("Escolha [C/V]: ").strip().upper()
        if raw == "C":
            return True
        if raw in {"V", ""}:
            return False
        print("Opção inválida. Use C para confirmar ou V para voltar.")


def confirm_sensitive(
    required_phrase: str,
    *,
    action_label: str,
    back_label: str,
    input_fn: Callable[[str], str] | None = None,
    emphasize_phrase: bool = True,
    colorize: bool = True,
) -> bool:
    """Confirm a destructive/sensitive action by an explicit phrase."""
    reader = input if input_fn is None else input_fn
    expected = required_phrase.strip().upper()
    rendered_expected = destructive_text(expected) if emphasize_phrase and colorize else expected
    confirmation_title = title_text("CONFIRMAÇÃO OBRIGATÓRIA") if colorize else "CONFIRMAÇÃO OBRIGATÓRIA"
    print("\n" + confirmation_title)
    print(f"Ação            : {action_label}")
    print("Digite exatamente: " + rendered_expected)
    print(f"V. {back_label}")
    while True:
        raw = reader("Confirmação: ").strip().upper()
        if raw == expected:
            return True
        if raw in {"V", ""}:
            return False
        print("Confirmação inválida. Digite " + rendered_expected + " ou V para voltar.")


__all__ = ["confirm_continue", "confirm_sensitive"]
