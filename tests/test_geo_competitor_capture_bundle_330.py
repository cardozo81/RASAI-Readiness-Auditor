"""#330: physically linked SERP -> immutable opt-in competitor sidecar."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

import pytest

from rasai import geo_competitor_capture_bundle_330 as capture


_URL = "https://competitor.example.org/seguro"
_OBS = "SERP-OBS-330"


def _audit(tmp_path):
    folder = tmp_path / "AUD-REAL"
    folder.mkdir()
    with sqlite3.connect(folder / "audit.db") as con:
        con.executescript("""
            CREATE TABLE audits(
                audit_id TEXT,status TEXT,completion_status TEXT
            );
            CREATE TABLE serp_observations(
                observation_id TEXT,audit_id TEXT,query TEXT,collected_at TEXT,
                observation_status TEXT,data_mode TEXT,
                engine TEXT,country TEXT,region TEXT,language TEXT,device TEXT
            );
            CREATE TABLE serp_results(
                observation_id TEXT,position INTEGER,url TEXT
            );
            INSERT INTO audits VALUES ('AUD-REAL','COMPLETED','COMPLETE');
        """)
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (_OBS, "AUD-REAL", "seguro de vida", "2026-10-10T10:00:00Z",
             "OBSERVED", "OBSERVED_API", "google", "BR", "São Paulo",
             "pt-BR", "mobile"),
        )
        con.execute("INSERT INTO serp_results VALUES (?,?,?)", (_OBS, 1, _URL))
    return folder


def _response(**changes):
    out = {
        "status": "STATIC_HTML_FEATURES_OBSERVED",
        "contract_version": "RASAI-COMPETITOR-ROBOTS-LOCAL-001",
        "role": "COMPETITOR_CANDIDATE",
        "robots_fetch_status": "ALLOWED",
        "requested_url": _URL, "final_url": _URL,
        "http_status": 200,
        "content_sha256": "f"*64,
        "html_fetch_timestamp": "2026-10-10T10:15:00Z",
        "html_rendering": "STATIC_HTTP_ONLY_NO_JS",
        "title": "Seguro de vida", "headings": ["Proteção"],
        "query_body_terms": ["seguro", "vida"],
        "word_count": 50,
        "primary_content_proven": False,
        "provider_requests": 2,
        "audit_writes": 0,
        "score_changed": False,
    }
    out.update(changes)
    return out


def _fake(monkeypatch, data=None):
    seen = []
    def inspect(url, **kwargs):
        seen.append((url, kwargs))
        return data if data is not None else _response()
    monkeypatch.setattr(capture, "inspect_consented_public_html", inspect)
    return seen


def _run(root, tmp_path, **kwargs):
    return capture.capture_competitor_sidecar(
        root, _OBS, _URL, output_root=tmp_path / "output",
        consented_hostnames=("competitor.example.org",),
        **kwargs,
    )


def test_source_provenance_and_versioned_output_not_written_into_aud(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    original = (folder/"audit.db").read_bytes()
    first = _run(folder, tmp_path)
    assert first["status"] == "MATERIALIZED"
    assert first["companion_files_written"] == 1
    assert first["provider_requests"] == 2
    assert len(calls) == 1
    assert calls[0][0] == _URL
    assert calls[0][1]["query"] == "seguro de vida"
    assert calls[0][1]["role"] == "COMPETITOR_CANDIDATE"
    manifest = json.loads(
        open(first["manifest_path"], encoding="utf-8").read()
    )
    assert manifest["contract_version"] == "RASAI-COMPETITOR-CAPTURE-SIDECAR-330-001"
    assert manifest["source_audit_id"] == folder.name
    assert manifest["source_audit_db_sha256"] == sha256(original).hexdigest()
    assert manifest["source_serp_observation_id"] == _OBS
    assert manifest["source_serp_scope"]["country"] == "BR"
    assert manifest["content_sha256"] == "f"*64
    assert manifest["content_comparison_eligible"] is False
    assert manifest["locale_equivalence_proven"] is False
    assert manifest["device_equivalence_proven"] is False
    assert manifest["temporal_equivalence_proven"] is False
    assert manifest["raw_html_persisted"] is False
    assert manifest["audit_writes"] == 0
    assert (folder/"audit.db").read_bytes() == original
    assert not list(folder.glob("COBS-*"))
    again = _run(folder, tmp_path)
    assert again["status"] == "IDEMPOTENT_EXISTING"
    assert again["package_id"] == first["package_id"]
    assert again["companion_files_written"] == 0
    assert (folder/"audit.db").read_bytes() == original


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'", "AUD identity"),
        ("UPDATE audits SET audit_id='AUD-OTHER'", "AUD identity"),
        ("UPDATE serp_observations SET audit_id='AUD-OTHER'", "foreign SERP"),
        ("UPDATE serp_observations SET data_mode='NOT_OBSERVED'", "foreign SERP"),
        ("UPDATE serp_observations SET language=NULL", "context not proven"),
        ("DELETE FROM serp_results", "not in persisted SERP"),
    ],
    ids=("partial", "foreign-aud", "foreign-serp", "unobserved-serp",
         "missing-locale", "absent-candidate"),
)
def test_bad_serp_or_aud_identity_blocks_http_and_does_not_create_package(
    tmp_path, monkeypatch, statement, expected,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    with sqlite3.connect(folder/"audit.db") as con:
        con.execute(statement)
    before = (folder/"audit.db").read_bytes()
    with pytest.raises(ValueError, match=expected):
        _run(folder, tmp_path)
    assert calls == []
    assert (folder/"audit.db").read_bytes() == before
    assert not (tmp_path/"output").exists()


def test_unverified_robots_or_html_does_not_publish_evidence(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    _fake(monkeypatch, _response(status="ROBOTS_DISALLOWED"))
    result = _run(folder, tmp_path)
    assert result["status"] == "NOT_CAPTURED"
    assert result["reason"] == "ROBOTS_DISALLOWED"
    assert result["companion_files_written"] == 0
    assert result["content_comparison_eligible"] is False
    assert not (tmp_path/"output").exists()


def test_no_write_into_source_aud_and_no_followed_redirect(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    with pytest.raises(ValueError, match="outside the AUD"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _URL,
            output_root=folder / "artifacts", consented_hostnames=(),
        )
    assert not calls
    _fake(monkeypatch, _response(final_url="https://wrong.example.org/path"))
    with pytest.raises(ValueError, match="final fetched URL"):
        _run(folder, tmp_path)
    assert not (tmp_path/"output").exists()


def test_source_change_during_fetch_fails_before_persistence(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    def mutate_then_return(url, **kwargs):
        with sqlite3.connect(folder/"audit.db") as con:
            con.execute("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'")
        return _response()
    monkeypatch.setattr(capture, "inspect_consented_public_html", mutate_then_return)
    with pytest.raises(ValueError, match="changed during capture"):
        _run(folder, tmp_path)
    assert not (tmp_path/"output").exists()


def test_existing_corrupted_evidence_cannot_be_overwritten(tmp_path, monkeypatch):
    folder = _audit(tmp_path)
    _fake(monkeypatch)
    result = _run(folder, tmp_path)
    manifest = result["manifest_path"]
    with open(manifest, "wb") as f:
        f.write(b"tampered")
    with pytest.raises(ValueError, match="refusing overwrite"):
        _run(folder, tmp_path)
    with open(manifest, "rb") as f:
        assert f.read() == b"tampered"


def test_cli_requires_explicit_network_flag_without_reaching_network(tmp_path, capsys):
    folder = _audit(tmp_path)
    with pytest.raises(SystemExit) as exc:
        capture.main([
            "--audit-dir", str(folder), "--serp-observation-id", _OBS,
            "--candidate-url", _URL,
            "--output-root", str(tmp_path/"output"),
            "--consent-host", "competitor.example.org",
        ])
    assert exc.value.code == 2
    assert "explicit --allow-public-html-requests" in capsys.readouterr().err
    assert not (tmp_path/"output").exists()


@pytest.mark.parametrize(
    "package_relative",
    (
        "AUD-OTHER/artifacts/competitor-evidence",
        "consolidated/CONS-FOREIGN/artifacts",
        "RPR-ANOTHER/artifacts/cobs",
    ),
)
def test_capture_never_writes_inside_foreign_aud_cons_rpr_packages(
    tmp_path, monkeypatch, package_relative,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    # Output roots must be isolated even when they belong to a DIFFERENT
    # physical package; an unrelated AUD is not writable capture storage.
    target = tmp_path / package_relative
    assert not target.exists()
    original = (folder / "audit.db").read_bytes()
    with pytest.raises(ValueError, match="outside every AUD/CONS/RPR"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _URL,
            output_root=target,
            consented_hostnames=("competitor.example.org",),
        )
    assert calls == []
    assert not target.exists()
    assert (folder / "audit.db").read_bytes() == original


def test_capture_relative_parent_traversal_to_other_aud_rejected_before_network(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path)
    calls = _fake(monkeypatch)
    other = tmp_path / "AUD-OTHER"
    other.mkdir()
    misleading_root = folder / ".." / "AUD-OTHER" / "artifacts"
    with pytest.raises(ValueError, match="outside every AUD/CONS/RPR"):
        capture.capture_competitor_sidecar(
            folder, _OBS, _URL, output_root=misleading_root,
            consented_hostnames=("competitor.example.org",),
        )
    assert calls == []
    assert not (other / "artifacts").exists()
