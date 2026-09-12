"""Safe masked input for secrets in the interactive console.

The real secret is kept only in memory and returned to the existing validation/storage
path. The terminal sees one ``*`` per entered character; the secret itself is never
echoed. Non-interactive/unsupported terminals fall back to stdlib ``getpass`` (no echo).
"""
from __future__ import annotations

from getpass import getpass as _hidden_getpass
import os
import sys


def _fallback(prompt: str) -> str:
    return _hidden_getpass(prompt)


def _masked_windows(prompt: str) -> str:
    import msvcrt

    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars: list[str] = []
    try:
        while True:
            char = msvcrt.getwch()
            if char in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars)
            if char == "\x03":
                raise KeyboardInterrupt
            if char in {"\b", "\x7f"}:
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            # Ignore Windows extended/special-key prefixes and consume their code.
            if char in {"\x00", "\xe0"}:
                msvcrt.getwch()
                continue
            if not char.isprintable():
                continue
            chars.append(char)
            sys.stdout.write("*")
            sys.stdout.flush()
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

    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars: list[str] = []
    try:
        termios.tcsetattr(fd, termios.TCSADRAIN, updated)
        while True:
            char = sys.stdin.read(1)
            if char in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(chars)
            if char == "\x03":
                raise KeyboardInterrupt
            if char in {"\b", "\x7f"}:
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if not char or not char.isprintable():
                continue
            chars.append(char)
            sys.stdout.write("*")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


def masked_secret_input(prompt: str = "Secret: ") -> str:
    """Read a secret while echoing only ``*`` characters when a TTY supports it."""
    if not (getattr(sys.stdin, "isatty", lambda: False)() and getattr(sys.stdout, "isatty", lambda: False)()):
        return _fallback(prompt)
    try:
        return _masked_windows(prompt) if os.name == "nt" else _masked_posix(prompt)
    except (ImportError, AttributeError, OSError, ValueError, termios_error_type()):
        return _fallback(prompt)


def termios_error_type():
    """Return the platform termios error type without importing termios on Windows."""
    try:
        import termios
        return termios.error
    except ImportError:
        return OSError


def install_masked_secret_input() -> None:
    """Patch the console modules that historically imported ``getpass`` directly."""
    from rasai import console_environment, console_provider_environment, interactive_console

    console_environment.getpass = masked_secret_input
    console_provider_environment.getpass = masked_secret_input
    interactive_console.getpass = masked_secret_input
