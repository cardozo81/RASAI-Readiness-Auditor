"""Regression tests for a network-probe sidecar race at console finalization."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai import catalog_report_site
from rasai import console_artifacts
from rasai import execution_adherence_refinement as finalization


PROBE_DRIFT = (
    "catalog report source dependency changed before promotion: "
    "source_dependency divergente: artifacts/network/probes"
)


def _boundary(tmp_path, monkeypatch):
    audit_id = "AUD-841204BDCD4740C5AA9649BB43FF5F13"
    root = tmp_path / audit_id
    root.mkdir()
    (root / "audit.db").touch()
    state = SimpleNamespace(audit_id=audit_id, operation="LOCAL:DONE")
    monkeypatch.setattr(console_artifacts, "artifact_status", lambda _state: (root, None))
    monkeypatch.setattr(catalog_report_site, "catalog_report_is_fresh", lambda **_kw: True)
    delays = []
    monkeypatch.setattr(finalization, "sleep", delays.append)
    return state, root, delays


@pytest.mark.parametrize("error", [
    PROBE_DRIFT,
    "catalog report source dependency changed during materialization: "
    "source_dependency divergente: artifacts/network/probes",
    "catalog source dependency changed during materialization: artifacts/network/probes",
])
def test_network_probe_race_rebuilds_a_fresh_projection(tmp_path, monkeypatch, error):
    state, root, delays = _boundary(tmp_path, monkeypatch)
    expected = root / "report-catalog" / "index.html"
    calls = []

    def materialize(**_kw):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError(error)
        return expected

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", materialize)

    assert finalization.finalize_catalog_projection(state) == expected
    assert len(calls) == 2
    assert delays == [0.25]


def test_persistent_network_probe_drift_remains_a_hard_failure(tmp_path, monkeypatch):
    state, _root, delays = _boundary(tmp_path, monkeypatch)
    calls = []

    def materialize(**_kw):
        calls.append(True)
        raise RuntimeError(PROBE_DRIFT)

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", materialize)

    with pytest.raises(RuntimeError, match="artifacts/network/probes"):
        finalization.finalize_catalog_projection(state)
    assert len(calls) == 3
    assert delays == [0.25, 0.5]


def test_unrelated_source_change_is_not_retried(tmp_path, monkeypatch):
    state, _root, delays = _boundary(tmp_path, monkeypatch)
    calls = []

    def materialize(**_kw):
        calls.append(True)
        raise RuntimeError(
            "catalog report source dependency changed before promotion: "
            "source_dependency divergente: artifacts/source-quality.json"
        )

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", materialize)

    with pytest.raises(RuntimeError, match="artifacts/source-quality.json"):
        finalization.finalize_catalog_projection(state)
    assert len(calls) == 1
    assert delays == []
