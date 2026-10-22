"""Offline contract checks for advisory architectural context."""
import pytest

from rasai.architecture_context import (
    ArchitectureObservation, resolve_architecture, CLASSES,
)


def resolve(**overrides):
    params = dict(
        mode="AUTO", declared_architecture=None,
        observations=(ArchitectureObservation("CSR_SPA", "https://example.org/a",
                    "mobile", "snapshot-a", "evidence-a"),),
        requested_url="https://example.org/a", device="mobile",
        snapshot_id="snapshot-a", consumer_id="descriptive_report",
        advisory_consumers=frozenset({"descriptive_report"}),
    )
    params.update(overrides)
    return resolve_architecture(**params)


def test_auto_observes_exact_snapshot():
    value = resolve()
    assert (value.effective_architecture, value.source, value.evidence_ref) == (
        "CSR_SPA", "AUTO_DISCOVERY", "evidence-a")


@pytest.mark.parametrize("key,value", [
    ("requested_url", "https://example.org/b"),
    ("device", "desktop"),
    ("snapshot_id", "snapshot-b"),
    ("observations", ()),
])
def test_auto_abstains_without_exact_evidence(key, value):
    result = resolve(**{key: value})
    assert result.effective_architecture is None
    assert result.source == "UNFORCED"
    assert result.abstention_reason == "MISSING_CONFLICTING_OR_INVALID_EVIDENCE"


def test_conflicting_observations_abstain():
    a = ArchitectureObservation("CSR_SPA", "https://example.org/a",
                                "mobile", "snapshot-a", "one")
    b = ArchitectureObservation("HYDRATED", "https://example.org/a",
                                "mobile", "snapshot-a", "two")
    assert resolve(observations=(a, b)).effective_architecture is None


@pytest.mark.parametrize("architecture", sorted(CLASSES - {"UNKNOWN"}))
def test_declared_is_separate_from_observed(architecture):
    v = resolve(mode="DECLARED", declared_architecture=architecture)
    assert v.effective_architecture == architecture
    assert v.observed_architecture == "CSR_SPA"
    assert v.source == "USER_DECLARED"
    assert v.discrepancy is (architecture != "CSR_SPA")


def test_unforced_is_not_implicit_auto():
    assert resolve(mode="UNFORCED").effective_architecture is None


def test_precollection_never_backpropagates_discovery():
    value = resolve(phase="PRE_COLLECTION")
    assert value.effective_architecture is None
    assert value.abstention_reason == "OBSERVATION_NOT_AVAILABLE_BEFORE_COLLECTION"


def test_unapproved_consumer_cannot_inherit_user_override():
    value = resolve(consumer_id="sari", mode="DECLARED",
                    declared_architecture="STATIC_OR_SSR")
    assert value.effective_architecture is None
    assert value.abstention_reason == "CONSUMER_NOT_APPROVED"


@pytest.mark.parametrize("bad", ["UNKNOWN", "", "OTHER"])
def test_declared_requires_known_concrete_value(bad):
    with pytest.raises(ValueError):
        resolve(mode="DECLARED", declared_architecture=bad)


def test_unknown_observation_abstains():
    obs = ArchitectureObservation("UNKNOWN", "https://example.org/a",
                                  "mobile", "snapshot-a", "evidence-a")
    assert resolve(observations=(obs,)).effective_architecture is None


def test_missing_evidence_reference_abstains():
    obs = ArchitectureObservation("HYDRATED", "https://example.org/a",
                                  "mobile", "snapshot-a", "")
    assert resolve(observations=(obs,)).effective_architecture is None

def test_explicit_audit_page_and_final_url_identity():
    obs = ArchitectureObservation(
        "HYDRATED", "https://example.org/a", "mobile", "snapshot-a", "artifact-1",
        audit_id="AUD-A", page_id="PAGE-A", final_url="https://example.org/redirect",
    )
    matching = resolve(observations=(obs,), audit_id="AUD-A", page_id="PAGE-A",
                       final_url="https://example.org/redirect")
    assert matching.effective_architecture == "HYDRATED"
    for field, value in (
        ("audit_id", "AUD-B"), ("page_id", "PAGE-B"),
        ("final_url", "https://example.org/other"),
    ):
        request = dict(audit_id="AUD-A", page_id="PAGE-A",
                       final_url="https://example.org/redirect")
        request[field] = value
        assert resolve(observations=(obs,), **request).effective_architecture is None


def test_legacy_unscoped_observation_not_promoted_to_explicit_audit():
    assert resolve(audit_id="AUD-A").effective_architecture is None


def test_blank_evidence_reference_is_not_physical_proof():
    obs = ArchitectureObservation("CSR_SPA", "https://example.org/a",
                                  "mobile", "snapshot-a", "  ")
    result = resolve(observations=(obs,))
    assert result.effective_architecture is None
    assert result.evidence_ref is None


@pytest.mark.parametrize("unauthorized_consumer", [
    "sari", "score_geo", "apdex", "synthetic_navigation", "synthetic_experience",
    "ai_recommendation", "crawler", "collector", "advice", "unknown",
])
@pytest.mark.parametrize("selected_mode", ["AUTO", "DECLARED", "UNFORCED"])
def test_caller_cannot_expand_methodological_consumer_allowlist(
    unauthorized_consumer, selected_mode,
):
    """The caller's claimed allowlist cannot bypass the central F3 policy."""
    value = resolve(
        mode=selected_mode,
        declared_architecture="CSR_SPA" if selected_mode == "DECLARED" else None,
        consumer_id=unauthorized_consumer,
        advisory_consumers=frozenset({unauthorized_consumer}),
    )
    assert value.effective_architecture is None
    assert value.applicability == "INAPPLICABLE"
    assert value.abstention_reason == "CONSUMER_NOT_APPROVED"


def test_can_narrow_but_never_self_authorize_descriptive_policy():
    result = resolve(advisory_consumers=frozenset())
    assert result.effective_architecture is None
    assert result.abstention_reason == "CONSUMER_NOT_APPROVED"
