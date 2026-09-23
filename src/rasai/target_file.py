"""Shared parsing for user-authored URL target files.

Windows editors commonly emit UTF-8 with a BOM.  RASAi accepts both UTF-8 forms and
reports the exact source line when a non-comment target is invalid instead of silently
removing it from previews or execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class TargetFileEntry:
    line_number: int
    value: str


def read_target_entries(path: Path) -> tuple[TargetFileEntry, ...]:
    """Read meaningful entries from a UTF-8 / UTF-8-BOM target file."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise ValueError(f"não foi possível ler TXT {path}: {exc}") from exc
    except UnicodeError as exc:
        raise ValueError(f"TXT {path} não é UTF-8 válido: {exc}") from exc

    entries: list[TargetFileEntry] = []
    for line_number, line in enumerate(lines, start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        entries.append(TargetFileEntry(line_number=line_number, value=raw))
    return tuple(entries)


def validated_target_file(
    path: Path,
    validator: Callable[[str], str],
) -> tuple[str, ...]:
    """Validate every target while preserving source-line diagnostics."""
    entries = read_target_entries(path)
    if not entries:
        raise ValueError("TXT não contém targets")

    targets: list[str] = []
    for entry in entries:
        try:
            targets.append(validator(entry.value))
        except ValueError as exc:
            excerpt = entry.value if len(entry.value) <= 160 else entry.value[:157] + "..."
            raise ValueError(
                f"TXT inválido na linha {entry.line_number}: {exc} | {excerpt}"
            ) from exc
    return tuple(targets)
