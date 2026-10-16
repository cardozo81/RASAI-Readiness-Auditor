"""Adapter for opt-in architecture selection inside canonical AUD configuration.

No SQL, INI or environment writes. Existing sealed configuration storage can
carry the extra top-level key without introducing a parallel source of truth.
"""
from __future__ import annotations

from typing import Any, Mapping

from rasai.architecture_choice import ArchitectureChoice, CHOICE_KEY, read_choice, write_choice
from rasai.architecture_choice_precedence import ResolvedChoice, resolve_choice_precedence
from rasai.audit_configuration_reuse import configuration_hash


def prepare_audit_choice_configuration(
    effective_configuration: Mapping[str, Any],
    *,
    choice: ArchitectureChoice | None = None,
) -> dict[str, Any]:
    """Return the exact payload intended for the existing audit configuration seal.

    None means no opt-in and keeps historic fingerprint intact. Explicit choice
    is preserved, including UNFORCED, without altering any other field.
    """
    if choice is None:
        return dict(effective_configuration)
    if not isinstance(choice, ArchitectureChoice):
        raise ValueError("Architecture choice must be validated before freezing")
    if CHOICE_KEY in effective_configuration:
        existing = read_choice(effective_configuration)
        if existing != choice:
            raise ValueError("Conflicting frozen architecture choice")
    return write_choice(effective_configuration, choice)


def read_sealed_audit_choice(
    configuration: Mapping[str, Any],
    *,
    expected_hash: str,
) -> ResolvedChoice:
    """Require canonical configuration fingerprint before reading architecture."""
    if not isinstance(configuration, Mapping) or not isinstance(expected_hash, str):
        raise ValueError("Invalid sealed configuration")
    if configuration_hash(configuration) != expected_hash:
        raise ValueError("Audit configuration fingerprint mismatch")
    return resolve_choice_precedence(snapshot=configuration)
