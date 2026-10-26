"""#659: local acceptance uses read-only preflight and bounded active consent."""
import sqlite3
from pathlib import Path

from rasai import network_acceptance as a
from rasai import network_active_probe as p


def _workspace(tmp_path):
    (tmp_path / "artifacts").mkdir()
    with sqlite3.connect(tmp_path / "audit.db") as connection:
        connection.executescript("""
            CREATE TABLE audits (audit_id TEXT);
            CREATE TABLE pages (audit_id TEXT, normalized_url TEXT);
            INSERT INTO audits VALUES ('AUD-659');
            INSERT INTO pages VALUES ('AUD-659', 'https://approved.example.org/');
        """)


def test_preflight_is_read_only_and_does_not_probe(tmp_path, monkeypatch):
    _workspace(tmp_path)
    original = a._sha256_file(tmp_path / "audit.db")
    def forbid(*_args, **_kwargs):
        raise AssertionError("Preflight must not initiate a probe")
    monkeypatch.setattr(p, "collect_authorized_probe", forbid)
    output = a.run_acceptance(tmp_path, "AUD-659", host="approved.example.org")
    assert output["status"] == "PREFLIGHT_READ_ONLY"
    assert output["target_in_original_audit"] is True
    assert not output["active_probe_executed"]
    assert output["audit_database_unchanged"] is True
    assert a._sha256_file(tmp_path / "audit.db") == original


def test_active_mismatched_scope_is_rejected_without_probe(tmp_path, monkeypatch):
    _workspace(tmp_path)
    def forbid(*_args, **_kwargs):
        raise AssertionError("Unauthorized target must not be contacted")
    monkeypatch.setattr(p, "collect_authorized_probe", forbid)
    output = a.run_acceptance(
        tmp_path, "AUD-659", host="other.example.org",
        permitted_hostname="other.example.org", authorized=True,
    )
    assert output["status"] == "ACTIVE_SCOPE_NOT_AUTHORIZED"
    assert not output["active_probe_executed"]
