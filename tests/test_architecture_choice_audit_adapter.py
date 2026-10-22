"""Audit configuration adapter must preserve fingerprints and legacy payloads."""
import pytest

from rasai.audit_configuration_reuse import configuration_hash
from rasai.architecture_choice import ArchitectureChoice
from rasai.architecture_choice_audit_adapter import (
    prepare_audit_choice_configuration, read_sealed_audit_choice,
)


def test_legacy_configuration_keeps_exact_hash_and_absence():
    original = {"settings": {"console": {"device": "mobile"}}, "targets": ["https://example.org"]}
    before = configuration_hash(original)
    adapted = prepare_audit_choice_configuration(original)
    assert adapted == original
    assert configuration_hash(adapted) == before
    result = read_sealed_audit_choice(adapted, expected_hash=before)
    assert result.choice.mode == "UNFORCED"
    assert result.source == "LEGACY_ABSENT"


@pytest.mark.parametrize("mode,architecture", [
    ("AUTO", None), ("UNFORCED", None),
    ("DECLARED", "CSR_SPA"), ("DECLARED", "HYDRATED"),
])
def test_explicit_choice_is_sealed_with_audit_configuration(mode, architecture):
    original = {"settings": {"console": {"device": "mobile"}}, "targets": ["https://example.org"]}
    adapted = prepare_audit_choice_configuration(
        original, choice=ArchitectureChoice(mode, architecture))
    assert original.get("architecture_choice") is None
    result = read_sealed_audit_choice(adapted, expected_hash=configuration_hash(adapted))
    assert result.choice == ArchitectureChoice(mode, architecture)
    assert result.source == "SNAPSHOT"


def test_tampered_frozen_selection_is_rejected_by_hash():
    payload = prepare_audit_choice_configuration({}, choice=ArchitectureChoice("AUTO"))
    sealed_hash = configuration_hash(payload)
    payload["architecture_choice"]["mode"] = "UNFORCED"
    with pytest.raises(ValueError, match="fingerprint"):
        read_sealed_audit_choice(payload, expected_hash=sealed_hash)


def test_conflicting_preexisting_choice_never_overwritten():
    payload = prepare_audit_choice_configuration({}, choice=ArchitectureChoice("AUTO"))
    with pytest.raises(ValueError, match="Conflicting"):
        prepare_audit_choice_configuration(
            payload, choice=ArchitectureChoice("DECLARED", "CSR_SPA"))
