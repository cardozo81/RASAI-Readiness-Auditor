"""Terminal presentation helpers for the optional interactive console."""
from __future__ import annotations

from functools import lru_cache
import os
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"


@lru_cache(maxsize=1)
def _windows_vt_available() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if handle in (0, -1) or not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        enable_virtual_terminal_processing = 0x0004
        return bool(kernel32.SetConsoleMode(handle, mode.value | enable_virtual_terminal_processing))
    except (AttributeError, OSError, ValueError):
        return False


def supports_color() -> bool:
    """Return whether ANSI presentation should be emitted."""
    if os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return _windows_vt_available()
    return os.environ.get("TERM", "").casefold() != "dumb"


def paint(text: object, color: str, *, bold: bool = False) -> str:
    raw = str(text)
    if not supports_color():
        return raw
    prefix = (BOLD if bold else "") + color
    return f"{prefix}{raw}{RESET}"


def clear_screen() -> None:
    """Redraw the interactive console as one logical screen instead of stacking menus."""
    if not sys.stdout.isatty():
        return
    if supports_color():
        print("\033[2J\033[H", end="", flush=True)
        return
    if os.name == "nt":
        os.system("cls")
    else:
        # ANSI color may be disabled by NO_COLOR while cursor control can still be used.
        print("\033[2J\033[H", end="", flush=True)


def status_color(status: str) -> str:
    normalized = status.strip().upper()
    if normalized in {"COMPLETE", "READY", "SUCCESS", "OK"} or normalized.startswith("COMPLETE"):
        return GREEN
    if any(token in normalized for token in ("FAIL", "ERROR", "BLOCK", "CRITICAL", "QUARANTIN")):
        return RED
    if any(token in normalized for token in ("START", "DISCOVER", "ACQUIR", "ANALYZ", "SCOR", "REPORT", "WEB_PERFORMANCE", "FINALIZ")):
        return YELLOW
    return CYAN


def bool_badge(enabled: bool) -> str:
    return paint("ON" if enabled else "OFF", GREEN if enabled else DIM)


def availability_badge(available: bool) -> str:
    return paint("APTO" if available else "INDISPONÍVEL", GREEN if available else RED, bold=True)


def cost_color(level: str) -> str:
    normalized = level.strip().upper()
    return {
        "NENHUM": GREEN,
        "BAIXO": CYAN,
        "MÉDIO": YELLOW,
        "MEDIO": YELLOW,
        "ALTO": MAGENTA,
        "EXCESSIVO": RED,
    }.get(normalized, WHITE)
