"""#646: contract matrix for advisory architecture resolution, with no network.

Never grants permission to change collection, APDEX, SARI or GEO scoring.
"""
from __future__ import annotations

import pytest

from rasai.architecture_context import ArchitectureObservation, resolve_architecture


@pytest.mark.parametrize("mode", ["AUTO", "DECLARED", "UNFORCED"])
@pytest.mark.parametrize("architecture", [
    "STATIC_OR_SSR", "HYDRATED", "CSR_SPA", "MIXED", "UNKNOWN",
])
@pytest.mark.parametrize("identity_matches", [True, False])
@pytest.mark.parametrize("consumer", [
    "descriptive_report", "m6_read_only_diagnostic", "apdex", "sari", "score_geo",
])
def test_architecture_resolution_matrix(mode, architecture, identity_matches, consumer):
    """150 combinations prevent cross-URL inheritance and unauthorized scoring."""
    original_url = "https://example.org/a"
    requested = original_url if identity_matches else "https://example.org/b"
    obs = ArchitectureObservation(
        architecture=architecture, requested_url=original_url,
        final_url=original_url, device="mobile", snapshot_id="SNAP-1",
        evidence_ref="artifacts/a/raw.html", audit_id="AUD-1", page_id="PAGE-1",
    )
    result = resolve_architecture(
        mode=mode, declared_architecture="HYDRATED" if mode == "DECLARED" else None,
        observations=(obs,), requested_url=requested, final_url=original_url,
        device="mobile", snapshot_id="SNAP-1", audit_id="AUD-1",
        page_id="PAGE-1", consumer_id=consumer,
        advisory_consumers=frozenset({"descriptive_report", "m6_read_only_diagnostic"}),
    )
    approved = consumer in {"descriptive_report", "m6_read_only_diagnostic"}
    assert (result.applicability == "ADVISORY_SAFE") is approved
    assert result.observed_architecture == (architecture if identity_matches else "UNKNOWN")
    expected = (
        None if not approved or mode == "UNFORCED" else
        "HYDRATED" if mode == "DECLARED" else
        architecture if identity_matches and architecture != "UNKNOWN" else None
    )
    assert result.effective_architecture == expected
    assert (result.discrepancy is True) == (
        mode == "DECLARED" and identity_matches and architecture not in {"HYDRATED", "UNKNOWN"}
    )


@pytest.mark.parametrize("device,snapshot_id,final_url,page_id", [
    ("desktop", "SNAP-1", "https://example.org/a", "PAGE-1"),
    ("mobile", "SNAP-2", "https://example.org/a", "PAGE-1"),
    ("mobile", "SNAP-1", "https://example.org/redirect", "PAGE-1"),
    ("mobile", "SNAP-1", "https://example.org/a", "PAGE-2"),
])
def test_auto_never_inherits_architecture_across_physical_identity(
    device, snapshot_id, final_url, page_id,
):
    obs = ArchitectureObservation(
        architecture="CSR_SPA", requested_url="https://example.org/a",
        final_url="https://example.org/a", device="mobile", snapshot_id="SNAP-1",
        evidence_ref="artifacts/a/raw.html", audit_id="AUD-1", page_id="PAGE-1",
    )
    result = resolve_architecture(
        mode="AUTO", declared_architecture=None, observations=(obs,),
        requested_url="https://example.org/a", final_url=final_url,
        device=device, snapshot_id=snapshot_id, page_id=page_id,
        audit_id="AUD-1", consumer_id="descriptive_report",
        advisory_consumers=frozenset({"descriptive_report"}),
    )
    assert result.effective_architecture is None
    assert result.observed_architecture == "UNKNOWN"
    assert result.abstention_reason == "MISSING_CONFLICTING_OR_INVALID_EVIDENCE"


def test_precollection_auto_cannot_retroactively_change_execution():
    obs = ArchitectureObservation(
        architecture="CSR_SPA", requested_url="https://example.org/a",
        final_url="https://example.org/a", device="mobile", snapshot_id="SNAP-1",
        evidence_ref="artifacts/a/raw.html", audit_id="AUD-1", page_id="PAGE-1",
    )
    result = resolve_architecture(
        mode="AUTO", declared_architecture=None, observations=(obs,),
        requested_url="https://example.org/a", final_url="https://example.org/a",
        device="mobile", snapshot_id="SNAP-1", page_id="PAGE-1", audit_id="AUD-1",
        consumer_id="descriptive_report",
        advisory_consumers=frozenset({"descriptive_report"}),
        phase="PRE_COLLECTION",
    )
    assert result.effective_architecture is None
    assert result.abstention_reason == "OBSERVATION_NOT_AVAILABLE_BEFORE_COLLECTION"


def test_duplicate_conflicting_observations_fail_closed():
    first = ArchitectureObservation(
        architecture="HYDRATED", requested_url="https://example.org/a",
        final_url="https://example.org/a", device="mobile", snapshot_id="SNAP-1",
        evidence_ref="artifacts/a/raw.html", audit_id="AUD-1", page_id="PAGE-1",
    )
    second = ArchitectureObservation(**{**vars(first), "architecture": "CSR_SPA"})
    result = resolve_architecture(
        mode="AUTO", declared_architecture=None, observations=(first, second),
        requested_url="https://example.org/a", final_url="https://example.org/a",
        device="mobile", snapshot_id="SNAP-1", page_id="PAGE-1", audit_id="AUD-1",
        consumer_id="descriptive_report",
        advisory_consumers=frozenset({"descriptive_report"}),
    )
    assert result.effective_architecture is None
    assert result.abstention_reason == "MISSING_CONFLICTING_OR_INVALID_EVIDENCE"
