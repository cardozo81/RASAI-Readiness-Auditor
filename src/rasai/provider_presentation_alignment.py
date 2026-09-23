"""Presentation-only alignment for provider help text.

The runtime provider registry is authoritative. This module removes historical help
wording that described AUTO as a fixed three-provider chain without changing routing,
credentials, scoring or provider execution.
"""
from __future__ import annotations

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import cli_extensions

    original = cli_extensions.build_parser
    if getattr(original, "_rasai_provider_presentation_alignment", False):
        _INSTALLED = True
        return

    def build_parser():
        parser = original()
        subparsers = next(
            action
            for action in parser._actions
            if getattr(action, "choices", None) and "audit" in action.choices
        )
        audit_parser = subparsers.choices["audit"]
        ai_action = next(action for action in audit_parser._actions if action.dest == "ai_provider")
        ai_action.help = (
            "semantic analysis provider; AUTO derives its eligible pool from the canonical "
            "provider registry and current configuration; providers marked explicit-only, "
            "such as GitHub Copilot, never enter AUTO; explicit providers keep their own "
            "model/reasoning policy"
        )
        return parser

    build_parser._rasai_provider_presentation_alignment = True
    build_parser._rasai_original = original
    cli_extensions.build_parser = build_parser
    _INSTALLED = True
