"""Architecture-consumer cross-product: provenance, mode and phase remain advisory.

No database, filesystem, browser, network or scoring action is performed.
"""
from __future__ import annotations

import pytest

from rasai.architecture_context import (
    ArchitectureObservation, CLASSES, resolve_architecture,
)

ADVISORY = frozenset({"descriptive_report"})
TARGET = "https://example.org/a"
FINAL = "https://example.org/final"


@pytest.mark.parametrize("mode", ["AUTO", "DECLARED", "UNFORCED"])
@pytest.mark.parametrize("observed", sorted(CLASSES))
@pytest.mark.parametrize("phase", ["PRE_COLLECTION", "POST_COLLECTION"])
@pytest.mark.parametrize("consumer", ["descriptive_report", "sari"])
@pytest.mark.parametrize("device", ["mobile", "desktop"])
def test_context_isolated_policy_matrix(mode, observed, phase, consumer, device):
    """120 mode/evidence/phase/consumer/device combinations."""
    valid = ArchitectureObservation(
        observed, TARGET, device, "snapshot-a", "evidence-a",
        audit_id="AUD-A", page_id="PAGE-A", final_url=FINAL,
    )
    context = resolve_architecture(
        mode=mode,
        declared_architecture="HYDRATED" if mode == "DECLARED" else None,
        observations=(valid,), requested_url=TARGET, device=device,
        snapshot_id="snapshot-a", audit_id="AUD-A", page_id="PAGE-A",
        final_url=FINAL, consumer_id=consumer,
        advisory_consumers=ADVISORY, phase=phase,
    )
    assert context.observed_architecture == observed
    assert context.evidence_ref == "evidence-a"
    assert context.contract_version == "architecture-context-v1"
    assert context.consumer_id == consumer
    assert context.selected_mode == mode
    if consumer != "descriptive_report":
        assert context.effective_architecture is None
        assert context.applicability == "INAPPLICABLE"
        assert context.abstention_reason == "CONSUMER_NOT_APPROVED"
    elif mode == "DECLARED":
        assert context.effective_architecture == "HYDRATED"
        assert context.source == "USER_DECLARED"
        assert context.discrepancy == (observed not in {"HYDRATED", "UNKNOWN"})
    elif mode == "UNFORCED":
        assert context.effective_architecture is None
        assert context.abstention_reason == "UNFORCED"
    elif phase == "PRE_COLLECTION":
        assert context.effective_architecture is None
        assert context.abstention_reason == "OBSERVATION_NOT_AVAILABLE_BEFORE_COLLECTION"
    elif observed == "UNKNOWN":
        assert context.effective_architecture is None
        assert context.abstention_reason == "UNKNOWN_OBSERVED_ARCHITECTURE"
    else:
        assert context.effective_architecture == observed
        assert context.source == "AUTO_DISCOVERY"


@pytest.mark.parametrize("spoof", ["requested_url", "device", "snapshot_id",
                                   "audit_id", "page_id", "final_url"])
def test_cross_audit_identity_never_promotes_foreign_observation(spoof):
    evidence = ArchitectureObservation(
        "CSR_SPA", TARGET, "mobile", "snapshot-a", "evidence-a",
        audit_id="AUD-A", page_id="PAGE-A", final_url=FINAL,
    )
    inputs = dict(
        requested_url=TARGET, device="mobile", snapshot_id="snapshot-a",
        audit_id="AUD-A", page_id="PAGE-A", final_url=FINAL,
    )
    inputs[spoof] = "https://different.example/" if "url" in spoof else "OTHER"
    value = resolve_architecture(
        mode="AUTO", declared_architecture=None,
        observations=(evidence,), consumer_id="descriptive_report",
        advisory_consumers=ADVISORY, **inputs,
    )
    assert value.effective_architecture is None
    assert value.evidence_ref is None
    assert value.abstention_reason == "MISSING_CONFLICTING_OR_INVALID_EVIDENCE"


def test_duplicate_same_snapshot_observations_abstain_even_if_agree():
    evidence = ArchitectureObservation(
        "CSR_SPA", TARGET, "mobile", "snapshot-a", "evidence-a",
        audit_id="AUD-A", page_id="PAGE-A", final_url=FINAL,
    )
    value = resolve_architecture(
        mode="AUTO", declared_architecture=None,
        observations=(evidence, evidence), requested_url=TARGET,
        device="mobile", snapshot_id="snapshot-a",
        audit_id="AUD-A", page_id="PAGE-A", final_url=FINAL,
        consumer_id="descriptive_report", advisory_consumers=ADVISORY,
    )
    assert value.effective_architecture is None
    assert value.abstention_reason == "MISSING_CONFLICTING_OR_INVALID_EVIDENCE"



def test_approved_advisory_ids_are_fixed_and_no_score_consumer_is_allowed():
    from rasai.architecture_context import APPROVED_ADVISORY_CONSUMERS
    assert APPROVED_ADVISORY_CONSUMERS == frozenset({
        "descriptive_report", "m6_read_only_diagnostic",
    })
    assert not APPROVED_ADVISORY_CONSUMERS.intersection({
        "sari", "score_geo", "apdex", "synthetic_navigation",
        "synthetic_experience", "ai_recommendation", "crawler",
    })
