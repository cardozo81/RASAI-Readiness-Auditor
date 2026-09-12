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
    from rasai import console_environment, console_provider_environment, interactive_console

    install_masked_secret_input()
    assert console_environment.getpass is masked_secret_input
    assert console_provider_environment.getpass is masked_secret_input
    assert interactive_console.getpass is masked_secret_input
