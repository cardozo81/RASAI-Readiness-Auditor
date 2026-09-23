from __future__ import annotations

import builtins
from contextlib import redirect_stdout
from io import StringIO
import sys
from types import ModuleType, SimpleNamespace

from rasai import console_ui_refactor as ui


class _TTYBuffer(StringIO):
    def isatty(self) -> bool:
        return True


def test_top_level_capture_delegates_isatty_to_real_stdout(monkeypatch) -> None:
    console = ModuleType("test_console_ui_stdout_tty_regression")

    def original_menu(state):
        print("INÍCIO")
        assert sys.stdout.isatty() is True
        return builtins.input("Escolha: ").strip().upper()

    console._menu = original_menu
    ui._install_top_level_menu(console)
    state = SimpleNamespace(project="Projeto", target="https://example.com/", audit_id="")
    monkeypatch.setattr(builtins, "input", lambda prompt="": "Q")

    output = _TTYBuffer()
    with redirect_stdout(output):
        assert console._menu(state) == "Q"

    assert "INÍCIO" in output.getvalue()
