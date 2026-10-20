"""Opt-in M25 sample ID is identical in live-page callback and persisted sample."""
from __future__ import annotations

from types import SimpleNamespace

from rasai import m25_apdex_experience as m25


class ObserverGateway:
    def __init__(self, enabled):
        self.advisory_same_page_observer = (lambda **kwargs: kwargs) if enabled else None
        self.scopes = []
        self.calls = 0

    def set_experimental_sample_scope(self, **kwargs):
        self.scopes.append(kwargs)

    def measure(self, **kwargs):
        self.calls += 1
        return m25.UxMeasurement(
            status="SUCCESS", user_action_duration_ms=240.0,
            navigation_duration_ms=240.0, final_url=kwargs["url"],
        )


class Pacer:
    def wait_for_slot(self):
        pass


def _run(monkeypatch, *, enabled):
    gateway = ObserverGateway(enabled)
    # No DB/network calls; only check the explicit sample handoff contract.
    monkeypatch.setattr(m25, "_log_progress", lambda *args: None)
    monkeypatch.setattr(
        m25, "classify_measurement", lambda *args, **kwargs:
        ("SATISFIED", 240.0, False),
    )
    calibration = m25.Calibration(
        source="MANUAL", kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=1.0, frustrated_threshold_seconds=4.0,
        errors_affect_apdex=True, metadata={},
    )
    config = m25.ExperienceApdexConfig()
    items = m25._measure_device(
        audit_id="AUD-M25-1", page_id="PAGE-1",
        workspace=SimpleNamespace(),
        url="https://example.test/ready",
        device="MOBILE", target=1, max_attempts=1,
        page_index=1, page_total=1, calibration=calibration,
        config=config, pacer=Pacer(), shared_gateway=gateway,
        factory=lambda: gateway,
    )
    return gateway, items, config, calibration


def test_optin_preallocates_exactly_persisted_sample_identity(monkeypatch):
    gateway, items, config, calibration = _run(monkeypatch, enabled=True)
    assert gateway.calls == 1
    assert len(gateway.scopes) == 1
    assert gateway.scopes[0]["audit_id"] == "AUD-M25-1"
    assert gateway.scopes[0]["page_id"] == "PAGE-1"
    assert gateway.scopes[0]["sample_id"] == items[0].experimental_sample_id
    assert gateway.scopes[0]["context_id"].startswith("UXC-")
    saved = m25._persisted_sample(
        "AUD-M25-1", "PAGE-1", "https://example.test/ready",
        m25.MOBILE_STANDARD_PROFILE, config, calibration, items[0],
    )
    assert saved.sample_id == gateway.scopes[0]["sample_id"]
    assert saved.classification == "SATISFIED"
    assert saved.kpm_value_ms == 240.0


def test_default_m25_does_not_preallocate_or_set_probe_scope(monkeypatch):
    gateway, items, config, calibration = _run(monkeypatch, enabled=False)
    assert gateway.scopes == []
    assert items[0].experimental_sample_id is None
    sample = m25._persisted_sample(
        "AUD-M25-1", "PAGE-1", "https://example.test/ready",
        m25.MOBILE_STANDARD_PROFILE, config, calibration, items[0],
    )
    assert sample.sample_id.startswith("UXA-")
    assert sample.classification == "SATISFIED"
