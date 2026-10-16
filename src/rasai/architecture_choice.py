"""Isolated architecture choice serialization; never grants execution permission."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rasai.architecture_context import CLASSES

CHOICE_VERSION = "architecture-choice-v1"
CHOICE_KEY = "architecture_choice"
MODES = frozenset({"AUTO", "DECLARED", "UNFORCED"})


@dataclass(frozen=True)
class ArchitectureChoice:
    mode: str = "UNFORCED"
    declared_architecture: str | None = None
    contract_version: str = CHOICE_VERSION

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError("Unrecognized architecture choice mode")
        if self.mode == "DECLARED":
            if self.declared_architecture not in CLASSES - {"UNKNOWN"}:
                raise ValueError("Declared architecture must be a concrete supported class")
        elif self.declared_architecture is not None:
            raise ValueError("Non-declared modes cannot silently retain a declared value")
        if self.contract_version != CHOICE_VERSION:
            raise ValueError("Unsupported architecture choice version")

    def as_record(self) -> dict[str, str | None]:
        return {
            "contract_version": self.contract_version,
            "mode": self.mode,
            "declared_architecture": self.declared_architecture,
        }


def read_choice(settings: Mapping[str, object]) -> ArchitectureChoice:
    """Legacy absence abstains; malformed explicit input fails closed."""
    if CHOICE_KEY not in settings:
        return ArchitectureChoice()
    record = settings[CHOICE_KEY]
    if not isinstance(record, dict):
        raise ValueError("Invalid architecture choice record")
    if set(record) != {"contract_version", "mode", "declared_architecture"}:
        raise ValueError("Architecture choice fields do not match contract")
    return ArchitectureChoice(
        mode=record["mode"], declared_architecture=record["declared_architecture"],
        contract_version=record["contract_version"],
    )


def write_choice(settings: Mapping[str, object], choice: ArchitectureChoice) -> dict[str, object]:
    """Copy-on-write projection for temporary snapshots, not an INI writer."""
    result = dict(settings)
    result[CHOICE_KEY] = choice.as_record()
    return result
