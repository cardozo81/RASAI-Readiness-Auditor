from __future__ import annotations

import contextlib
import io
import unittest

from rasai import cli as legacy_cli
from rasai.cli import build_parser as legacy_build_parser
from rasai.cli_extensions import build_parser, main
from rasai.provider_registry import extension_cli_choices


class CLIProviderExtensionTests(unittest.TestCase):
    def test_extension_cli_adds_registry_explicit_provider_choices(self) -> None:
        parser = build_parser()
        for provider in extension_cli_choices():
            with self.subTest(provider=provider):
                parsed = parser.parse_args([
                    "audit", "https://example.com", "--ai-provider", provider,
                ])
                self.assertEqual(parsed.ai_provider, provider)

    def test_legacy_parser_surface_is_not_mutated(self) -> None:
        parser = legacy_build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if getattr(action, "choices", None) and "audit" in action.choices
        )
        audit_parser = subparsers.choices["audit"]
        ai_action = next(action for action in audit_parser._actions if action.dest == "ai_provider")
        self.assertEqual(tuple(ai_action.choices), ("none", "openai", "deepseek", "mimo", "auto"))

    def test_auto_remains_an_available_legacy_choice(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "audit", "https://example.com", "--ai-provider", "auto",
        ])
        self.assertEqual(args.ai_provider, "auto")

    def test_public_main_builds_parser_without_recursion_and_restores_legacy_globals(self) -> None:
        original_parser = legacy_cli.build_parser
        original_builder = legacy_cli.build_semantic_provider
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                main(["audit"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("provide at least one target", stderr.getvalue())
        self.assertIs(legacy_cli.build_parser, original_parser)
        self.assertIs(legacy_cli.build_semantic_provider, original_builder)


if __name__ == "__main__":
    unittest.main()
