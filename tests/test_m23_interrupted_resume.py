"""Regression: interrupted M23 must checkpoint samples and RPR must reuse them."""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from rasai.m23_apdex import SyntheticApdexConfig, execute_m23_apdex
from rasai.reprocess_measurements import recover_synthetic_apdex
from tests.test_m23_integration import _measurement, _workspace


class _InterruptedGateway:
    def __init__(self):
        self.calls = 0
        self.closed = False

    def environment(self):
        return {"system": "TEST"}

    def measure(self, **_kwargs):
        self.calls += 1
        if self.calls == 3:
            raise KeyboardInterrupt()
        return _measurement(500)

    def close(self):
        self.closed = True


class _RecoveryGateway:
    def __init__(self, measurements):
        self.measurements = list(measurements)
        self.calls = 0
        self.closed = False

    def measure(self, **_kwargs):
        self.calls += 1
        if not self.measurements:
            raise AssertionError("RPR tried more measurements than its remaining budget")
        return self.measurements.pop(0)

    def close(self):
        self.closed = True


def test_interrupted_m23_preserves_each_sample_and_rpr_uses_original_budget(tmp_path, monkeypatch):
    workspace = _workspace(str(tmp_path))
    original = _InterruptedGateway()
    cfg = SyntheticApdexConfig(
        enabled=True,
        threshold_seconds=1.0,
        target_valid_samples=3,
        max_attempts_per_context=3,
        max_pages=1,
        timeout_seconds=5.0,
        delay_seconds=0.0,
        concurrency=1,
    )

    with pytest.raises(KeyboardInterrupt):
        execute_m23_apdex(
            audit_id="AUD-M23", workspace=workspace, config=cfg, gateway=original,
        )
    with sqlite3.connect(workspace.database) as db:
        first_run = db.execute(
            "SELECT status,target_valid_samples,max_attempts_per_context "
            "FROM synthetic_apdex_runs WHERE audit_id='AUD-M23'"
        ).fetchone()
        first_samples = db.execute(
            "SELECT sample_id,run_index,classification "
            "FROM synthetic_apdex_samples WHERE audit_id='AUD-M23' ORDER BY run_index"
        ).fetchall()

    assert first_run == ("RUNNING", 3, 3)
    from rasai.m23_apdex import persisted_target_fulfilled
    assert not persisted_target_fulfilled(workspace, "AUD-M23", 3)
    assert [row[1] for row in first_samples] == [1, 2]
    assert [row[2] for row in first_samples] == ["SATISFIED", "SATISFIED"]

    recovery = _RecoveryGateway([_measurement(500)])
    from rasai import m23_apdex_profiles
    monkeypatch.setattr(
        m23_apdex_profiles,
        "PlaywrightSyntheticNavigationGateway",
        lambda: recovery,
    )
    completed = recover_synthetic_apdex(
        workspace=workspace, audit_id="AUD-M23",
        item=SimpleNamespace(configuration={"timeout_seconds": 5.0}),
    )
    # Both AUD and RPR classify a group below 100 samples as PARTIAL,
    # despite reaching the explicitly configured lower target.
    assert completed is True
    assert recovery.calls == 1
    assert recovery.closed

    with sqlite3.connect(workspace.database) as db:
        final_run = db.execute(
            "SELECT status,attempted_samples,valid_samples "
            "FROM synthetic_apdex_runs WHERE audit_id='AUD-M23'"
        ).fetchone()
        final_samples = db.execute(
            "SELECT sample_id,run_index,classification "
            "FROM synthetic_apdex_samples WHERE audit_id='AUD-M23' ORDER BY run_index"
        ).fetchall()
    assert final_run == ("PARTIAL", 3, 3)
    # Methodological PARTIAL (<100) and operational fulfillment SUCCESS differ.
    from rasai.audit_fulfillment_runtime import _m23_effective_success
    from rasai.m23_apdex import persisted_target_fulfilled
    assert persisted_target_fulfilled(workspace, "AUD-M23", 3)
    assert _m23_effective_success(workspace, "AUD-M23", 3)
    assert not persisted_target_fulfilled(workspace, "AUD-M23", 4)
    assert final_samples[:2] == first_samples
    assert [row[1] for row in final_samples] == [1, 2, 3]

    # With the original three-attempt ceiling exhausted, repeated RPR must
    # preserve all samples and make zero further calls.
    no_budget = _RecoveryGateway([])
    monkeypatch.setattr(m23_apdex_profiles, "PlaywrightSyntheticNavigationGateway", lambda: no_budget)
    assert recover_synthetic_apdex(
        workspace=workspace, audit_id="AUD-M23",
        item=SimpleNamespace(configuration={"timeout_seconds": 5.0}),
    ) is True
    assert no_budget.calls == 0
    with sqlite3.connect(workspace.database) as db:
        assert db.execute(
            "SELECT COUNT(*) FROM synthetic_apdex_samples WHERE audit_id='AUD-M23'"
        ).fetchone()[0] == 3
