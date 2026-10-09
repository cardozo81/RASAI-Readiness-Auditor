"""#322: isolated sidecar integrity tests; no collectors, browser or network."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3

import pytest

from rasai.apdex_content_readiness_observation import (
    PrimaryContentReadiness, STRICT_PROVENANCE_VERSION,
)
from rasai.apdex_readiness_sidecar_322 import (
    read_readiness_sidecar, write_readiness_sidecar,
)


@pytest.fixture(autouse=True)
def isolate_catalog_verifier(monkeypatch):
    # These fixtures test the advisory storage contract. Full report package
    # verification already has its own real-manifest test suite.
    monkeypatch.setattr(
        "rasai.catalog_report_site.catalog_report_is_fresh",
        lambda *, audit_id, workspace: True,
    )


def aud(tmp_path, *, audit_id="AUD-SAMPLE-1", complete=True):
    folder = tmp_path / audit_id
    folder.mkdir()
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "CREATE TABLE audits(audit_id TEXT PRIMARY KEY,status TEXT,completion_status TEXT)"
        )
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)",
            (audit_id, "COMPLETED", "COMPLETE" if complete else "PARTIAL"),
        )
    report = folder / "report-catalog"
    report.mkdir()
    (report / "manifest.json").write_text('{"contract":"TEST"}', encoding="utf-8")
    return folder


def observed(**updates):
    fields = dict(
        sample_id="M25-1", context_id="CTX-1", page_id="PAGE-1",
        device="MOBILE", architecture="CSR_SPA",
        method_version=STRICT_PROVENANCE_VERSION, status="OBSERVED",
        load_ms=200.0, primary_content_ms=390.0,
        post_load_delta_ms=190.0, observation_window_ms=1200,
        reason="stable_primary_dom_text",
    )
    fields.update(updates)
    return PrimaryContentReadiness(**fields)


def test_immutable_same_sample_sidecar_outside_original(tmp_path):
    source = aud(tmp_path)
    original = (source / "audit.db").read_bytes()
    manifest = (source / "report-catalog" / "manifest.json").read_bytes()
    path = write_readiness_sidecar(source, observed())
    assert source not in path.parents
    assert path.parent.name == source.name
    first_bytes = path.read_bytes()
    replay = write_readiness_sidecar(source, observed())
    assert replay == path and replay.read_bytes() == first_bytes
    stored = read_readiness_sidecar(source, path)
    assert stored["advisory_only"] is True
    assert stored["measurement_provenance"] == "PRODUCER_DECLARED_SAME_SAMPLE"
    assert stored["observation"]["post_load_delta_ms"] == 190.0
    assert (source / "audit.db").read_bytes() == original
    assert (source / "report-catalog" / "manifest.json").read_bytes() == manifest


@pytest.mark.parametrize("change", [
    {"status": "TIMEOUT"},
    {"status": "OBSERVED", "post_load_delta_ms": 999.0},
    {"method_version": "APP_PRIMARY_CONTENT_READINESS-EXPERIMENTAL-001"},
    {"page_id": ""},
    {"load_ms": float("nan")},
    {"primary_content_ms": float("inf")},
    {"architecture": "MADE_UP"},
])
def test_invalid_or_fabricated_observation_is_never_materialized(tmp_path, change):
    source = aud(tmp_path)
    with pytest.raises(ValueError):
        write_readiness_sidecar(source, observed(**change))
    assert not (tmp_path / ".rasai-readiness-sidecars").exists()


def test_timeout_is_censored_and_never_reports_ready(tmp_path):
    source = aud(tmp_path)
    point = observed(
        status="TIMEOUT", primary_content_ms=None,
        post_load_delta_ms=None, reason="window_censored",
    )
    path = write_readiness_sidecar(source, point)
    stored = read_readiness_sidecar(source, path)
    assert stored["observation"]["status"] == "TIMEOUT"
    assert stored["observation"]["primary_content_ms"] is None
    assert stored["observation"]["post_load_delta_ms"] is None


def test_source_db_and_report_manifest_mutations_break_source_binding(tmp_path):
    source = aud(tmp_path)
    path = write_readiness_sidecar(source, observed())
    with sqlite3.connect(source / "audit.db") as con:
        con.execute("CREATE TABLE post_source_marker(x INTEGER)")
    with pytest.raises(ValueError, match="source or contract mismatch"):
        read_readiness_sidecar(source, path)
    # With a deliberately stubbed catalog verifier, a changed input source
    # binds to a DIFFERENT immutable digest, never overwriting old evidence.
    newer = write_readiness_sidecar(source, observed())
    assert newer != path and newer.is_file()
    assert path.is_file()


def test_manifest_change_invalidates_read_without_touching_aud(tmp_path):
    source = aud(tmp_path)
    path = write_readiness_sidecar(source, observed())
    (source / "report-catalog" / "manifest.json").write_text(
        '{"contract":"DIFFERENT"}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="source or contract mismatch"):
        read_readiness_sidecar(source, path)


def test_sidecar_corruption_and_cross_aud_link_fail_closed(tmp_path):
    source = aud(tmp_path)
    other = aud(tmp_path, audit_id="AUD-SAMPLE-2")
    path = write_readiness_sidecar(source, observed())
    with pytest.raises(ValueError, match="outside sealed AUD scope"):
        read_readiness_sidecar(other, path)
    original = path.read_bytes()
    path.write_bytes(original + b"extra")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_readiness_sidecar(source, path)
    with pytest.raises(ValueError, match="checksum mismatch"):
        write_readiness_sidecar(source, observed())


def test_missing_or_partial_aud_is_not_considered_proven_source(tmp_path):
    source = aud(tmp_path, complete=False)
    with pytest.raises(ValueError, match="not complete"):
        write_readiness_sidecar(source, observed())
    assert not (tmp_path / ".rasai-readiness-sidecars").exists()



def test_source_report_package_must_pass_freshness_gate(tmp_path, monkeypatch):
    source = aud(tmp_path)
    monkeypatch.setattr(
        "rasai.catalog_report_site.catalog_report_is_fresh",
        lambda *, audit_id, workspace: False,
    )
    with pytest.raises(ValueError, match="stale or invalid"):
        write_readiness_sidecar(source, observed())
    assert not (tmp_path / ".rasai-readiness-sidecars").exists()
