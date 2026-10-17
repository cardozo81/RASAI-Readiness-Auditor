"""Pure architecture choice precedence; no INI, SQLite or runtime mutation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rasai.architecture_choice import ArchitectureChoice, CHOICE_KEY, read_choice

SOURCES = ("SNAPSHOT", "SESSION", "BASE")


@dataclass(frozen=True)
class ResolvedChoice:
    choice: ArchitectureChoice
    source: str
    explicitly_configured: bool


def resolve_choice_precedence(
    *,
    base: Mapping[str, object] | None = None,
    session: Mapping[str, object] | None = None,
    snapshot: Mapping[str, object] | None = None,
) -> ResolvedChoice:
    """Explicit snapshot > session > base; missing everywhere means UNFORCED.

    Malformed explicit higher-priority records raise instead of falling back.
    A higher-priority UNFORCED record intentionally suppresses lower AUTO or
    DECLARED choices. No field-level merging or ambient operator defaults.
    """
    for name, layer in (("SNAPSHOT", snapshot), ("SESSION", session), ("BASE", base)):
        if layer is None:
            continue
        if not isinstance(layer, Mapping):
            raise ValueError("Architecture choice layer must be a mapping")
        if CHOICE_KEY in layer:
            return ResolvedChoice(read_choice(layer), name, True)
    return ResolvedChoice(ArchitectureChoice(), "LEGACY_ABSENT", False)
