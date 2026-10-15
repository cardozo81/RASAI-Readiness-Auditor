"""#206: RPR reuses canonical synthetic acquisitions before live recollection."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from rasai import m25_apdex_experience as m25
from rasai import synthetic_acquisition_engine as acquisition_engine
from rasai.m23_apdex import SyntheticApdexConfig, execute_m23_apdex
from rasai.m23_apdex_profiles import NavigationMeasurement
from rasai.reprocess_measurements import recover_experience_apdex, recover_synthetic_apdex
from tests.test_m23_integration import _workspace as m23_workspace
from tests.test_m25_synthetic_user_experience import _ux, _workspace as m25_workspace


class _NavGateway:
    def __init__(self, duration_ms: int = 500) -> None:
        self.duration_ms = duration_ms
        self.calls = 0

    def environment(self):
        return {"system": "TEST"}

    def measure(self, *, url, profile, timeout_seconds):
        self.calls += 1
        return NavigationMeasurement(
            status="SUCCESS",
            duration_ms=self.duration_ms,
            http_status=200,
            final_url=url,
            error_code=None,
            error_message=None,
            profile_applied=True,
            cpu_method="TEST_CPU",
            network_method="TEST_NETWORK",
        )

    def close(self):
        return None


class _UxGateway:
    def __init__(self, *, allow_measure: bool) -> None:
        self.allow_measure = allow_measure
        self.calls = 0

    def environment(self):
        return {"system": "TEST"}

    def measure(self, **_kwargs):
        self.calls += 1
        if not self.allow_measure:
            raise AssertionError("RPR visited the site despite reusable FULL evidence")
        return _ux(700)

    def close(self):
        return None


def test_cat06_replays_persisted_full_without_live_navigation(tmp_path, monkeypatch) -> None:
    workspace = m23_workspace(str(tmp_path))
    initial = _NavGateway(500)
    execute_m23_apdex(
        audit_id="AUD-M23",
        workspace=workspace,
        config=SyntheticApdexConfig(
            enabled=True,
            threshold_seconds=1.0,
            target_valid_samples=1,
            max_attempts_per_context=1,
            max_pages=1,
            timeout_seconds=5.0,
            delay_seconds=0.0,
            concurrency=1,
        ),
        gateway=initial,
    )
    with sqlite3.connect(workspace.database) as db:
        profile_id = db.execute(
            "SELECT profile_id FROM synthetic_apdex_samples WHERE audit_id='AUD-M23'"
        ).fetchone()[0]
        db.execute(
            "UPDATE synthetic_apdex_runs SET target_valid_samples=2,max_attempts_per_context=3 "
            "WHERE audit_id='AUD-M23'"
        )
        db.commit()

    full = acquisition_engine.record_acquisition(
        audit_id="AUD-M23",
        workspace=workspace,
        url="https://example.com/",
        device="MOBILE",
        profile_id=profile_id,
        envelope_kind=acquisition_engine.FULL_EXPERIENCE,
        session_mode="cold",
        load_duration_ms=600.0,
        status="SUCCESS",
        http_status=200,
        final_url="https://example.com/",
        full_observables={"user_action_duration_ms": 900.0, "network_settled": True},
        source="TEST_FULL",
        reusable_for_load=False,
        planning_ordinal=2,
    )
    assert full is not None

    class _Forbidden:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("live Navigation gateway must not be created")

    from rasai import m23_apdex_profiles
    monkeypatch.setattr(m23_apdex_profiles, "PlaywrightSyntheticNavigationGateway", _Forbidden)

    assert recover_synthetic_apdex(
        workspace=workspace,
        audit_id="AUD-M23",
        item=SimpleNamespace(configuration={"timeout_seconds": 5.0}),
    ) is True

    with sqlite3.connect(workspace.database) as db:
        samples = db.execute(
            "SELECT run_index,classification,captured_at,browser_diagnostics "
            "FROM synthetic_apdex_samples WHERE audit_id='AUD-M23' ORDER BY run_index"
        ).fetchall()
        links = db.execute(
            "SELECT acquisition_id,consumer,phase FROM synthetic_acquisition_replay_links"
        ).fetchall()
    assert len(samples) == 2
    assert samples[1][1] == "SATISFIED"
    assert "CANONICAL_ACQUISITION_REPLAY" in samples[1][3]
    assert links == [(full.acquisition_id, "CAT-06", "RPR")]


def test_cat07_replays_full_offline_and_preserves_acquisition_provenance(tmp_path, monkeypatch) -> None:
    workspace = m25_workspace(str(tmp_path))
    config = m25.ExperienceApdexConfig(
        enabled=True,
        target_samples_per_page=1,
        max_attempts_per_page=1,
        max_pages=1,
        device_mix=(("MOBILE", 100.0),),
        session_mode="cold",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=1.0,
        frustrated_threshold_seconds=4.0,
        errors_affect_apdex=False,
        settle_seconds=1.0,
        delay_seconds=0.0,
        concurrency=1,
    ).validate()
    first = _UxGateway(allow_measure=True)
    m25.execute_m25_experience(
        audit_id="AUD-M25",
        workspace=workspace,
        config=config,
        gateway=first,
    )
    with sqlite3.connect(workspace.database) as db:
        profile_id = db.execute(
            "SELECT profile_id FROM synthetic_ux_apdex_samples WHERE audit_id='AUD-M25'"
        ).fetchone()[0]
        db.execute(
            "UPDATE synthetic_ux_apdex_runs SET target_samples_per_page=2,max_attempts_per_page=3 "
            "WHERE audit_id='AUD-M25'"
        )
        db.commit()

    measurement = _ux(700)
    full = acquisition_engine.record_acquisition(
        audit_id="AUD-M25",
        workspace=workspace,
        url="https://example.com/",
        device="MOBILE",
        profile_id=profile_id,
        envelope_kind=acquisition_engine.FULL_EXPERIENCE,
        session_mode="cold",
        load_duration_ms=550.0,
        status="SUCCESS",
        http_status=200,
        final_url="https://example.com/",
        full_observables=acquisition_engine.full_observables_from_measurement(measurement),
        source="TEST_FULL",
        reusable_for_load=False,
        planning_ordinal=2,
        captured_at="2026-10-05T12:00:00+00:00",
    )
    assert full is not None

    no_live = _UxGateway(allow_measure=False)
    monkeypatch.setattr(m25, "PlaywrightSyntheticUxGateway", lambda **_kwargs: no_live)

    assert recover_experience_apdex(
        workspace=workspace,
        audit_id="AUD-M25",
        item=SimpleNamespace(configuration=config.as_dict()),
    ) is True
    assert no_live.calls == 0

    with sqlite3.connect(workspace.database) as db:
        samples = db.execute(
            "SELECT run_index,classification,captured_at FROM synthetic_ux_apdex_samples "
            "WHERE audit_id='AUD-M25' ORDER BY run_index"
        ).fetchall()
        links = db.execute(
            "SELECT acquisition_id,consumer,phase,sample_id FROM synthetic_acquisition_replay_links"
        ).fetchall()
    assert len(samples) == 2
    assert samples[1] == (2, "SATISFIED", "2026-10-05T12:00:00+00:00")
    assert len(links) == 1
    assert links[0][0:3] == (full.acquisition_id, "CAT-07", "RPR")


def test_load_only_never_fabricates_cat07_and_forces_live_deficit(tmp_path, monkeypatch) -> None:
    workspace = m25_workspace(str(tmp_path))
    config = m25.ExperienceApdexConfig(
        enabled=True,
        target_samples_per_page=1,
        max_attempts_per_page=1,
        max_pages=1,
        device_mix=(("MOBILE", 100.0),),
        session_mode="cold",
        kpm="USER_ACTION_DURATION",
        satisfied_threshold_seconds=1.0,
        frustrated_threshold_seconds=4.0,
        errors_affect_apdex=False,
        settle_seconds=1.0,
        delay_seconds=0.0,
        concurrency=1,
    ).validate()
    first = _UxGateway(allow_measure=True)
    m25.execute_m25_experience(
        audit_id="AUD-M25",
        workspace=workspace,
        config=config,
        gateway=first,
    )
    with sqlite3.connect(workspace.database) as db:
        profile_id = db.execute(
            "SELECT profile_id FROM synthetic_ux_apdex_samples WHERE audit_id='AUD-M25'"
        ).fetchone()[0]
        db.execute(
            "UPDATE synthetic_ux_apdex_runs SET target_samples_per_page=2,max_attempts_per_page=3 "
            "WHERE audit_id='AUD-M25'"
        )
        db.commit()

    load_only = acquisition_engine.record_acquisition(
        audit_id="AUD-M25",
        workspace=workspace,
        url="https://example.com/",
        device="MOBILE",
        profile_id=profile_id,
        envelope_kind=acquisition_engine.LOAD_ONLY,
        session_mode="cold",
        load_duration_ms=450.0,
        status="SUCCESS",
        source="TEST_LOAD_ONLY",
        reusable_for_load=False,
    )
    assert load_only is not None

    live = _UxGateway(allow_measure=True)
    monkeypatch.setattr(m25, "PlaywrightSyntheticUxGateway", lambda **_kwargs: live)

    assert recover_experience_apdex(
        workspace=workspace,
        audit_id="AUD-M25",
        item=SimpleNamespace(configuration=config.as_dict()),
    ) is True
    assert live.calls == 1

    with sqlite3.connect(workspace.database) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM synthetic_acquisition_replay_links WHERE consumer='CAT-07'"
        ).fetchone()[0] == 0
