"""Read-only M6 SQLite bridge tests with synthetic databases."""
from pathlib import Path
import sqlite3

import pytest

from rasai.architecture_observation_reader import observed_architecture_for_snapshot


def _call(path):
    return observed_architecture_for_snapshot(
        path, audit_id="AUD", page_id="P", snapshot_id="S",
        requested_url="https://example.org/a", final_url="https://example.org/b",
        device="mobile",
    )


def _db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE pages (page_id TEXT, audit_id TEXT)")
        con.execute(
            "CREATE TABLE page_snapshots (snapshot_id TEXT, page_id TEXT, "
            "requested_url TEXT, final_url TEXT, device TEXT, "
            "architecture_classification TEXT,"
            "raw_artifact_ref TEXT, rendered_artifact_ref TEXT)"
        )
        con.execute("INSERT INTO pages VALUES ('P','AUD')")
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)",
            ("S", "P", "https://example.org/a", "https://example.org/b",
             "mobile", "CSR_SPA", "artifacts/raw.html", "artifacts/rendered.html"),
        )


def test_bridge_observation_is_scoped_and_read_only(tmp_path):
    db = tmp_path / "AUD" / "audit.db"
    _db(db)
    before = db.read_bytes()
    result = _call(db)
    assert result.effective_architecture == "CSR_SPA"
    assert result.source == "AUTO_DISCOVERY"
    assert result.evidence_ref == "artifacts/raw.html"
    assert db.read_bytes() == before


def test_bridge_rejects_ambiguous_snapshot_identifier(tmp_path):
    db = tmp_path / "AUD" / "audit.db"
    _db(db)
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO page_snapshots VALUES ('S','OTHER','x','x','desktop','MIXED','artifacts/r.html','artifacts/d.html')")
    assert _call(db).effective_architecture is None


def test_bridge_abstains_for_missing_classification(tmp_path):
    db = tmp_path / "AUD" / "audit.db"
    _db(db)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE page_snapshots SET architecture_classification='UNKNOWN'")
    assert _call(db).effective_architecture is None


def test_bridge_requires_regular_source(tmp_path):
    with pytest.raises(ValueError):
        _call(tmp_path / "missing.db")


def test_bridge_rejects_symlink(tmp_path):
    db = tmp_path / "AUD" / "audit.db"
    _db(db)
    link = tmp_path / "link.db"
    try:
        link.symlink_to(db)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError):
        _call(link)

def test_bridge_rejects_noncanonical_database_location(tmp_path):
    db = tmp_path / "audit.db"
    _db(db)
    with pytest.raises(ValueError, match="Canonical physical AUD"):
        _call(db)


def test_bridge_inherits_signature_policy_and_binding_verification(tmp_path, monkeypatch):
    import json
    from rasai.architecture_attestation import VERIFY_KEY
    from rasai.architecture_m6_evidence import capture_artifact_binding

    db = tmp_path / "AUD" / "audit.db"
    _db(db)
    artifacts = db.parent / "artifacts"
    artifacts.mkdir()
    raw = artifacts / "raw.html"
    dom = artifacts / "rendered.html"
    raw.write_bytes(b"<main>server</main>")
    dom.write_bytes(b"<main>rendered</main>")
    binding = capture_artifact_binding(
        db.parent, "artifacts/raw.html", "artifacts/rendered.html",
    )
    with sqlite3.connect(db) as con:
        con.execute("ALTER TABLE page_snapshots ADD COLUMN browser_metadata TEXT")
        con.execute("UPDATE page_snapshots SET browser_metadata=?", (
            json.dumps({"architecture_artifact_binding": binding}),))
    assert _call(db).effective_architecture == "CSR_SPA"
    dom.write_bytes(b"mutated")
    assert _call(db).effective_architecture is None
    dom.write_bytes(b"<main>rendered</main>")
    monkeypatch.setenv(VERIFY_KEY, str(tmp_path / "trusted-public.pem"))
    assert _call(db).effective_architecture is None
    monkeypatch.delenv(VERIFY_KEY, raising=False)
    assert _call(db).effective_architecture == "CSR_SPA"


def test_bridge_rejects_uncheckpointed_audit_even_with_valid_classification(tmp_path):
    db = tmp_path / "AUD" / "audit.db"
    _db(db)
    sidecar = db.parent / "audit.db-shm"
    sidecar.write_bytes(b"in-progress")
    assert _call(db).effective_architecture is None
    assert sidecar.read_bytes() == b"in-progress"
