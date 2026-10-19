"""Adapter for opt-in architecture selection inside canonical AUD configuration.

No SQL, INI or environment writes. Existing sealed configuration storage can
carry the extra top-level key without introducing a parallel source of truth.
"""
from __future__ import annotations

from typing import Any, Mapping, Callable, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from rasai.domain import DeviceContext
    from rasai.architecture_acquisition_service import DiscoveryExecution
    from rasai.architecture_context import ArchitectureContext

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


def observe_auto_architecture_before_audit(
    url: str, device: "DeviceContext", *, mode: str,
    consent: "Callable[[str], bool]",
) -> "DiscoveryExecution":
    """Advisory-only AUTO discovery for a new AUD; never change its sealed config.

    The menu 8 preference controls acquisition, not the declared audit choice.
    The caller must explicitly select AUTO, and invoke this only for a new AUD,
    never silently during RPR or complementary processing.
    """
    from rasai.architecture_acquisition_service import run_optional_discovery
    return run_optional_discovery(url, device, mode=mode, consent=consent)


def read_architecture_choice_for_reprocess(
    audits_root: "str | Path", audit_id: str,
) -> ResolvedChoice | None:
    """Read only the sealed choice for RPR/complements; never reacquire a site.

    Absence of a historical configuration is legitimate. Corrupted or modified
    snapshots are not promoted to observed architecture evidence.
    """
    from rasai.audit_configuration_reuse import load_reusable_audit_configuration
    try:
        saved = load_reusable_audit_configuration(audits_root, audit_id)
        return read_sealed_audit_choice(
            saved.configuration, expected_hash=saved.configuration_hash,
        )
    except (FileNotFoundError, OSError, ValueError, KeyError, TypeError):
        return None


def resolve_historical_architecture_for_consumer(
    audits_root: "str | Path", audit_id: str, *,
    requested_url: str, final_url: str, device: str,
    page_id: str, snapshot_id: str, consumer_id: str,
) -> "ArchitectureContext":
    """Resolve persisted M6/choice exclusively for approved advisory consumers.

    No network, reprocessing or complementary acquisition is performed.
    A missing/tampered configuration abstains rather than inheriting preferences
    from the current operator session.
    """
    from rasai.architecture_context import resolve_architecture
    from rasai.architecture_m6_evidence import read_audit_architecture_observations

    choice = read_architecture_choice_for_reprocess(audits_root, audit_id)
    if choice is None:
        mode, declared = "UNFORCED", None
    else:
        mode = choice.choice.mode
        declared = choice.choice.declared_architecture
    return resolve_architecture(
        mode=mode, declared_architecture=declared,
        observations=read_audit_architecture_observations(audits_root, audit_id),
        requested_url=requested_url, final_url=final_url,
        device=device, audit_id=audit_id, page_id=page_id,
        snapshot_id=snapshot_id, consumer_id=consumer_id,
        advisory_consumers=frozenset({"descriptive_report", "m6_read_only_diagnostic"}),
        phase="POST_COLLECTION",
    )
