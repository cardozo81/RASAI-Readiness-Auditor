from __future__ import annotations

from pathlib import Path
import sqlite3
import time
from types import SimpleNamespace

from rasai.domain import DeviceContext
from rasai.m23_apdex import _classification as navigation_classification
from rasai.m23_apdex_profiles import NavigationMeasurement
from rasai.m25_apdex_experience import Calibration, UxMeasurement, allocate_samples, classify_measurement
from rasai.persistence import AuditWorkspace
from rasai.synthetic_apdex_shared_runtime import (
    SharedAwareNavigationGateway,
    _TimedPageProxy,
    acquisition_stats,
    consume_navigation_acquisition,
    prepare_acquisition_run,
    publish_experience_acquisition,
)


def _workspace(tmp_path: Path) -> AuditWorkspace:
    root = tmp_path / "AUD-SHARED"
    root.mkdir()
    (root / "artifacts").mkdir()
    sqlite3.connect(root / "audit.db").close()
    return AuditWorkspace(root)


def _profile(device: DeviceContext = DeviceContext.MOBILE, profile_id: str = "PROFILE-MOBILE"):
    return SimpleNamespace(device=device, profile_id=profile_id)


def _ux_measurement(*, status: str = "SUCCESS", http_status: int = 200):
    return SimpleNamespace(
        status=status,
        profile_applied=True,
        http_status=http_status,
        final_url="https://example.test/",
        cpu_method="CDP:CPU",
        network_method="CDP:NETWORK",
    )


def test_same_cold_acquisition_can_feed_both_methods_without_reusing_score(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RASAI_APDEX_ACQUISITION_MODE", "auto")
    workspace = _workspace(tmp_path)
    prepare_acquisition_run(audit_id="AUD-1", workspace=workspace, mode="auto")

    published = publish_experience_acquisition(
        audit_id="AUD-1",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile=_profile(),
        session_mode="cold",
        measurement=_ux_measurement(),
        load_duration_ms=1_000.0,
    )
    assert published is not None

    consumed = consume_navigation_acquisition(
        audit_id="AUD-1",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile_id="PROFILE-MOBILE",
        timeout_seconds=45.0,
    )
    assert consumed is not None
    assert consumed.acquisition_id == published.acquisition_id
    assert consumed.load_duration_ms == 1_000.0

    nav = NavigationMeasurement(
        status="SUCCESS",
        duration_ms=1_000,
        http_status=200,
        final_url="https://example.test/",
        error_code=None,
        error_message=None,
        profile_applied=True,
        cpu_method="CDP:CPU",
        network_method="CDP:NETWORK",
    )
    # T=0.5 => 1s is TOLERATING under Navigation T/4T.
    assert navigation_classification(nav, 0.5) == "TOLERATING"

    ux = UxMeasurement(status="SUCCESS", user_action_duration_ms=1_000.0)
    calibration = Calibration(
        source="TEST",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=2.0,
        frustrated_threshold_seconds=4.0,
        errors_affect_apdex=False,
        metadata={},
    )
    # The same physical occurrence can be SATISFIED under the independent UX method.
    assert classify_measurement(ux, calibration, error_scope="navigation")[0] == "SATISFIED"


def test_device_mix_remains_independent_from_navigation_targets() -> None:
    assert allocate_samples(100, {"MOBILE": 60.0, "DESKTOP": 35.0, "TABLET": 5.0}) == {
        "MOBILE": 60,
        "DESKTOP": 35,
        "TABLET": 5,
    }


def test_warm_or_isolated_experience_is_not_shared(tmp_path, monkeypatch) -> None:
    workspace = _workspace(tmp_path)
    monkeypatch.setenv("RASAI_APDEX_ACQUISITION_MODE", "auto")
    prepare_acquisition_run(audit_id="AUD-2", workspace=workspace, mode="auto")
    assert publish_experience_acquisition(
        audit_id="AUD-2",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile=_profile(),
        session_mode="warm",
        measurement=_ux_measurement(),
        load_duration_ms=500.0,
    ) is None

    monkeypatch.setenv("RASAI_APDEX_ACQUISITION_MODE", "isolated")
    assert publish_experience_acquisition(
        audit_id="AUD-2",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile=_profile(),
        session_mode="cold",
        measurement=_ux_measurement(),
        load_duration_ms=500.0,
    ) is None


def test_profile_device_and_timeout_must_be_compatible(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RASAI_APDEX_ACQUISITION_MODE", "auto")
    workspace = _workspace(tmp_path)
    prepare_acquisition_run(audit_id="AUD-3", workspace=workspace, mode="auto")
    publish_experience_acquisition(
        audit_id="AUD-3",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile=_profile(),
        session_mode="cold",
        measurement=_ux_measurement(),
        load_duration_ms=5_000.0,
    )

    assert consume_navigation_acquisition(
        audit_id="AUD-3",
        workspace=workspace,
        url="https://example.test/",
        device="DESKTOP",
        profile_id="PROFILE-MOBILE",
        timeout_seconds=45.0,
    ) is None
    assert consume_navigation_acquisition(
        audit_id="AUD-3",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile_id="OTHER-PROFILE",
        timeout_seconds=45.0,
    ) is None
    assert consume_navigation_acquisition(
        audit_id="AUD-3",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile_id="PROFILE-MOBILE",
        timeout_seconds=1.0,
    ) is None
    assert acquisition_stats(audit_id="AUD-3", workspace=workspace)["timeout_incompatible"] == 1


class _Delegate:
    def __init__(self) -> None:
        self.calls = 0

    def environment(self):
        return {"delegate": True}

    def close(self):
        return None

    def measure(self, *, url, profile, timeout_seconds):
        self.calls += 1
        return NavigationMeasurement(
            status="SUCCESS",
            duration_ms=999,
            http_status=200,
            final_url=url,
            error_code=None,
            error_message=None,
            profile_applied=True,
            cpu_method="DIRECT",
            network_method="DIRECT",
        )


def test_navigation_gateway_reuses_compatible_experience_before_network(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RASAI_APDEX_ACQUISITION_MODE", "auto")
    workspace = _workspace(tmp_path)
    prepare_acquisition_run(audit_id="AUD-4", workspace=workspace, mode="auto")
    publish_experience_acquisition(
        audit_id="AUD-4",
        workspace=workspace,
        url="https://example.test/",
        device="MOBILE",
        profile=_profile(),
        session_mode="cold",
        measurement=_ux_measurement(),
        load_duration_ms=432.4,
    )
    delegate = _Delegate()
    gateway = SharedAwareNavigationGateway(audit_id="AUD-4", workspace=workspace, delegate=delegate)
    measured = gateway.measure(url="https://example.test/", profile=_profile(), timeout_seconds=45.0)
    assert delegate.calls == 0
    assert measured.duration_ms == 432
    assert measured.browser_diagnostics[0]["type"] == "SHARED_ACQUISITION"


def test_load_boundary_timer_is_frozen_before_post_load_observation() -> None:
    class Page:
        def goto(self, *args, **kwargs):
            time.sleep(0.002)
            return "response"

    capture: dict[str, float] = {}
    proxy = _TimedPageProxy(Page(), capture)
    assert proxy.goto("https://example.test/", wait_until="load") == "response"
    assert capture["load_duration_ms"] >= 1.0
