"""Safe masked input for secrets in the interactive console.

The real secret is kept only in memory and returned to the existing validation/storage
path. The terminal sees one ``*`` per entered character; the secret itself is never
echoed. Non-interactive/unsupported terminals fall back to stdlib ``getpass`` (no echo).
"""
from __future__ import annotations

from getpass import getpass as _hidden_getpass
import os
import sys
from typing import Callable


def _fallback(prompt: str) -> str:
    return _hidden_getpass(prompt)


def _read_masked_chars(
    prompt: str,
    read_char: Callable[[], str],
    write: Callable[[str], object],
    flush: Callable[[], object],
) -> str:
    """Read characters while exposing only asterisks to the terminal."""
    write(prompt)
    flush()
    chars: list[str] = []
    while True:
        char = read_char()
        if char == "":
            raise EOFError("entrada de secret encerrada antes de Enter")
        if char in {"\r", "\n"}:
            write("\n")
            flush()
            return "".join(chars)
        if char == "\x03":
            raise KeyboardInterrupt
        if char in {"\b", "\x7f"}:
            if chars:
                chars.pop()
                write("\b \b")
                flush()
            continue
        if not char.isprintable():
            continue
        chars.append(char)
        write("*")
        flush()


def _masked_windows(prompt: str) -> str:
    import msvcrt

    def read_char() -> str:
        char = msvcrt.getwch()
        if char in {"\x00", "\xe0"}:
            # Consume Windows extended/special-key code and ignore it.
            msvcrt.getwch()
            return "\x00"
        return char

    try:
        return _read_masked_chars(prompt, read_char, sys.stdout.write, sys.stdout.flush)
    except BaseException:
        sys.stdout.write("\n")
        sys.stdout.flush()
        raise


def _masked_posix(prompt: str) -> str:
    import termios

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    updated = termios.tcgetattr(fd)
    # Keep ISIG enabled so Ctrl+C/Ctrl+Z retain normal terminal semantics. Disable
    # canonical line buffering and echo only for the duration of this prompt.
    updated[3] &= ~(termios.ECHO | termios.ICANON)
    updated[6][termios.VMIN] = 1
    updated[6][termios.VTIME] = 0

    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, updated)
        return _read_masked_chars(prompt, lambda: sys.stdin.read(1), sys.stdout.write, sys.stdout.flush)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def masked_secret_input(prompt: str = "Secret: ") -> str:
    """Read a secret while echoing only ``*`` characters when a TTY supports it."""
    stdin_tty = getattr(sys.stdin, "isatty", lambda: False)()
    stdout_tty = getattr(sys.stdout, "isatty", lambda: False)()
    if not (stdin_tty and stdout_tty):
        return _fallback(prompt)
    try:
        return _masked_windows(prompt) if os.name == "nt" else _masked_posix(prompt)
    except KeyboardInterrupt:
        raise
    except Exception:
        # Security-preserving fallback: if direct terminal control is unavailable,
        # revert to no-echo getpass rather than ever exposing the secret in clear text.
        return _fallback(prompt)


def install_masked_secret_input() -> None:
    """Patch console modules that historically imported ``getpass`` directly."""
    from rasai import console_environment, console_provider_environment, interactive_console

    console_environment.getpass = masked_secret_input
    console_provider_environment.getpass = masked_secret_input
    interactive_console.getpass = masked_secret_input
