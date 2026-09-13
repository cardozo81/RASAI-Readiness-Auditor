from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rasai.consolidation.integration import install


class _FakeConsole:
    """Module-like fake that resolves input through its own namespace first."""

    def __init__(self) -> None:
        self.configured: list[str] = []

    def _menu(self, state):
        reader = getattr(self, "input", builtins.input)
        return reader("Escolha: ").strip().upper()

    def _configure(self, state, choice):
        self.configured.append(choice)


class ConsolidationConsoleIntegrationTests(unittest.TestCase):
    def test_existing_choices_are_delegated_unchanged(self) -> None:
        console = _FakeConsole()
        install(console)
        state = SimpleNamespace(audits_root="audits", status="READY", operation="LOCAL:MENU", error="")
        with patch("builtins.input", return_value="R"), redirect_stdout(StringIO()) as output:
            choice = console._menu(state)
        self.assertEqual(choice, "R")
        self.assertEqual(output.getvalue(), "")
        console._configure(state, choice)
        self.assertEqual(console.configured, ["R"])

    def test_consolidation_choice_passes_current_ai_policy_without_calling_legacy_configure(self) -> None:
        console = _FakeConsole()
        install(console)
        state = SimpleNamespace(
            audits_root="audits",
            status="READY",
            operation="LOCAL:MENU",
            error="",
            ai_provider="auto",
            ai_model=None,
            ai_reasoning=None,
            ai_timeout=123.0,
            runtime_blocks={},
        )
        capability = SimpleNamespace(available=True, reason="ready")
        with patch("rasai.consolidation.integration.provider_capabilities", return_value={"auto": capability}), patch(
            "rasai.consolidation.integration.run_consolidation_console"
        ) as run:
            console._configure(state, "C")
        run.assert_called_once_with(
            "audits",
            ai_provider="auto",
            ai_model=None,
            ai_reasoning=None,
            ai_timeout=123.0,
            ai_available=True,
            ai_unavailable_reason=None,
        )
        self.assertEqual(console.configured, [])
        self.assertEqual(state.status, "READY")
        self.assertEqual(state.operation, "LOCAL:MENU")

    def test_consolidation_without_ai_remains_available(self) -> None:
        console = _FakeConsole()
        install(console)
        state = SimpleNamespace(audits_root="audits", status="READY", operation="LOCAL:MENU", error="", ai_provider="none")
        with patch("rasai.consolidation.integration.run_consolidation_console") as run:
            console._configure(state, "C")
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["ai_provider"], "none")
        self.assertTrue(kwargs["ai_available"])

    def test_consolidation_failure_is_fail_open(self) -> None:
        console = _FakeConsole()
        install(console)
        state = SimpleNamespace(audits_root="audits", status="READY", operation="LOCAL:MENU", error="")
        with patch("rasai.consolidation.integration.run_consolidation_console", side_effect=RuntimeError("boom")):
            console._configure(state, "C")
        self.assertEqual(state.status, "READY")
        self.assertEqual(state.operation, "LOCAL:CONSOLIDATION_ERROR")
        self.assertIn("boom", state.error)
        console._configure(state, "R")
        self.assertEqual(console.configured, ["R"])


if __name__ == "__main__":
    unittest.main()
