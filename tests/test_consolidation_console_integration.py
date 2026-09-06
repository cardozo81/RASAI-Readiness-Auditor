from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from searchgeo.consolidation.integration import install


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
        self.assertIn("Histórico / relatórios consolidados", output.getvalue())
        console._configure(state, choice)
        self.assertEqual(console.configured, ["R"])

    def test_consolidation_choice_does_not_call_legacy_configure(self) -> None:
        console = _FakeConsole()
        install(console)
        state = SimpleNamespace(audits_root="audits", status="READY", operation="LOCAL:MENU", error="")
        with patch("searchgeo.consolidation.integration.run_consolidation_console") as run:
            console._configure(state, "C")
        run.assert_called_once_with("audits")
        self.assertEqual(console.configured, [])
        self.assertEqual(state.status, "READY")
        self.assertEqual(state.operation, "LOCAL:MENU")

    def test_consolidation_failure_is_fail_open(self) -> None:
        console = _FakeConsole()
        install(console)
        state = SimpleNamespace(audits_root="audits", status="READY", operation="LOCAL:MENU", error="")
        with patch("searchgeo.consolidation.integration.run_consolidation_console", side_effect=RuntimeError("boom")):
            console._configure(state, "C")
        self.assertEqual(state.status, "READY")
        self.assertEqual(state.operation, "LOCAL:CONSOLIDATION_ERROR")
        self.assertIn("boom", state.error)
        console._configure(state, "R")
        self.assertEqual(console.configured, ["R"])


if __name__ == "__main__":
    unittest.main()
