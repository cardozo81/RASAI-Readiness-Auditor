from __future__ import annotations

import io
from unittest.mock import patch

from rasai.console_secret_input import _read_masked_chars, install_masked_secret_input, masked_secret_input


def _reader(sequence: str):
    iterator = iter(sequence)
    return lambda: next(iterator)


def test_masked_reader_echoes_only_asterisks_and_returns_real_secret() -> None:
    output = io.StringIO()
    secret = _read_masked_chars(
        "TOKEN: ",
        _reader("abc123\n"),
        output.write,
        output.flush,
    )
    assert secret == "abc123"
    assert output.getvalue() == "TOKEN: ******\n"
    assert "abc123" not in output.getvalue()


def test_masked_reader_handles_backspace_without_changing_stored_result() -> None:
    output = io.StringIO()
    secret = _read_masked_chars(
        "KEY: ",
        _reader("ab\bcd\n"),
        output.write,
        output.flush,
    )
    assert secret == "acd"
    assert "ab" not in output.getvalue()
    assert "acd" not in output.getvalue()
    assert "\b \b" in output.getvalue()


def test_non_tty_uses_hidden_fallback_never_plain_input() -> None:
    with patch("rasai.console_secret_input._fallback", return_value="real-secret") as fallback, patch(
        "rasai.console_secret_input.sys.stdin.isatty", return_value=False
    ):
        assert masked_secret_input("Secret: ") == "real-secret"
        fallback.assert_called_once_with("Secret: ")


def test_installer_rebinds_all_local_console_secret_entry_points() -> None:
    from rasai import (
        console_configuration_presentation,
        console_environment,
        console_provider_environment,
        interactive_console,
    )

    originals = (
        console_environment.getpass,
        console_provider_environment.getpass,
        console_configuration_presentation.getpass,
        interactive_console.getpass,
    )
    try:
        install_masked_secret_input()
        assert console_environment.getpass is masked_secret_input
        assert console_provider_environment.getpass is masked_secret_input
        assert console_configuration_presentation.getpass is masked_secret_input
        assert interactive_console.getpass is masked_secret_input
    finally:
        console_environment.getpass = originals[0]
        console_provider_environment.getpass = originals[1]
        console_configuration_presentation.getpass = originals[2]
        interactive_console.getpass = originals[3]


def test_masked_reader_masks_pasted_chunk_character_by_character() -> None:
    output = io.StringIO()
    chunks = iter(("sk-live-", "ABC123", "\n"))
    secret = _read_masked_chars(
        "Chave: ",
        lambda: next(chunks),
        output.write,
        output.flush,
    )

    assert secret == "sk-live-ABC123"
    assert output.getvalue() == "Chave: " + ("*" * len(secret)) + "\n"
    assert secret not in output.getvalue()


def test_sensitive_console_owners_import_canonical_masked_reader() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src" / "rasai"
    module_paths = (
        root / "interactive_console.py",
        root / "console_environment.py",
        root / "console_provider_environment.py",
        root / "console_configuration_presentation.py",
        root / "console_ui_catalog.py",
    )
    for module_path in module_paths:
        text = module_path.read_text(encoding="utf-8")
        assert "masked_secret_input" in text, module_path
        assert "from getpass import getpass\n" not in text, module_path
