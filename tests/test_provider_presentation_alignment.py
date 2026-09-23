from __future__ import annotations

from rasai import cli_extensions
from rasai.provider_presentation_alignment import install
from rasai.provider_registry import provider_registrations
from rasai.web.ui_runtime import render_pilot_ui


def _audit_parser():
    parser = cli_extensions.build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if getattr(action, "choices", None) and "audit" in action.choices
    )
    return subparsers.choices["audit"]


def test_effective_audit_help_describes_dynamic_auto_registry() -> None:
    install()
    audit_parser = _audit_parser()
    action = next(item for item in audit_parser._actions if item.dest == "ai_provider")

    assert "canonical provider registry" in action.help
    assert "explicit-only" in action.help
    assert "GitHub Copilot" in action.help
    assert "OpenAI/DeepSeek/MiMo chain" not in action.help


def test_effective_ai_choices_include_registered_canonical_ids_and_aliases() -> None:
    install()
    audit_parser = _audit_parser()
    action = next(item for item in audit_parser._actions if item.dest == "ai_provider")
    choices = set(action.choices or ())

    assert {"none", "auto"} <= choices
    for registration in provider_registrations():
        assert registration.id in choices
        assert set(registration.aliases) <= choices


def test_web_selector_exposes_only_canonical_provider_ids() -> None:
    html = render_pilot_ui("trusted-header")
    for registration in provider_registrations():
        assert f'<option value="{registration.id}">{registration.display_name}</option>' in html
        for alias in registration.aliases:
            assert f'<option value="{alias}">' not in html
