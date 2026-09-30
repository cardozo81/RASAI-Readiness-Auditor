"""#126/#127: an unfinished M25 stage restarts without recycling progress events."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from rasai import m25_apdex_experience as m25
from rasai.reprocess_measurements import recover_experience_apdex
from tests.test_m25_synthetic_user_experience import _ux, _workspace


class _InterruptAfterTwo:
    def __init__(self):
        self.calls = 0
        self.closed = False

    def environment(self):
        return {"system": "TEST"}

    def measure(self, **_kwargs):
        self.calls += 1
        if self.calls == 3:
            raise KeyboardInterrupt()
        return _ux(500)

    def close(self):
        self.closed = True


class _RetryGateway:
    def __init__(self, count):
        self.remaining = count
        self.calls = 0
        self.closed = False

    def environment(self):
        return {"system": "TEST"}

    def measure(self, **_kwargs):
        self.calls += 1
        if self.remaining <= 0:
            raise AssertionError("completed M25 stage was measured again")
        self.remaining -= 1
        return _ux(500)

    def close(self):
        self.closed = True


def test_m25_interrupted_stage_restarts_from_one_and_preserves_original_contract(
    tmp_path, monkeypatch,
):
    workspace = _workspace(str(tmp_path))
    config = m25.ExperienceApdexConfig(
        enabled=True,
        target_samples_per_page=4,
        max_attempts_per_page=4,
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
    interrupted = _InterruptAfterTwo()
    with pytest.raises(KeyboardInterrupt):
        m25.execute_m25_experience(
            audit_id="AUD-M25", workspace=workspace, config=config,
            gateway=interrupted,
        )
    assert interrupted.calls == 3
    with sqlite3.connect(workspace.database) as connection:
        # An in-memory progress event is not a completed stage/checkpoint.
        assert connection.execute(
            "SELECT COUNT(*) FROM synthetic_ux_apdex_runs"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM synthetic_ux_apdex_samples"
        ).fetchone()[0] == 0

    retried = _RetryGateway(4)
    monkeypatch.setattr(
        m25, "PlaywrightSyntheticUxGateway",
        lambda **_kwargs: retried,
    )
    assert recover_experience_apdex(
        workspace=workspace, audit_id="AUD-M25",
        item=SimpleNamespace(configuration=config.as_dict()),
    ) is True
    assert retried.calls == 4  # Whole M25 stage, not 4 minus the two lost events.
    with sqlite3.connect(workspace.database) as connection:
        run = connection.execute(
            "SELECT status,target_samples_per_page,max_attempts_per_page,"
            "attempted_samples,valid_samples FROM synthetic_ux_apdex_runs"
        ).fetchone()
        rows = connection.execute(
            "SELECT run_index,classification FROM synthetic_ux_apdex_samples"
            " ORDER BY run_index"
        ).fetchall()
    assert run == ("SUCCESS", 4, 4, 4, 4)
    assert rows == [(i, "SATISFIED") for i in range(1, 5)]

    repeated = _RetryGateway(0)
    monkeypatch.setattr(
        m25, "PlaywrightSyntheticUxGateway",
        lambda **_kwargs: repeated,
    )
    assert recover_experience_apdex(
        workspace=workspace, audit_id="AUD-M25",
        item=SimpleNamespace(configuration=config.as_dict()),
    ) is True
    assert repeated.calls == 0
