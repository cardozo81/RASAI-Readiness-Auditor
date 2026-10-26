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



def test_authorized_end_to_end_gate_checks_probed_metric_and_read_only_report(
        tmp_path, monkeypatch):
    from types import SimpleNamespace
    from rasai import network_acceptance as a
    from rasai import network_active_probe as p
    from rasai import report_completion as completion
    from rasai import catalog_report_site as catalog
    _workspace(tmp_path)
    original = a._sha256_file(tmp_path / "audit.db")
    def store(*_args, **_kwargs):
        return tmp_path / "artifacts" / "network" / "probes" / "synthetic.json"
    monkeypatch.setattr(p, "collect_authorized_probe", store)
    def read(*_args, **_kwargs):
        return [{
            "audit_id": "AUD-659", "hostname": "approved.example.org",
            "port": 443, "series_id": "test",
            "state": "OBSERVED",
            "metrics": {"tcp_handshake_ms": {"state": "OBSERVED", "value": 12.0}},
        }]
    monkeypatch.setattr(p, "read_authorized_probes", read)
    def materialize(*, audit_id, workspace, read_only):
        assert audit_id == "AUD-659" and read_only is True
        dest = workspace.root / "report-catalog"
        dest.mkdir(exist_ok=True)
        (dest / "network.html").write_text(
            "Medição complementar autorizada: approved.example.org",
            encoding="utf-8")
        return SimpleNamespace(renderer_errors=())
    monkeypatch.setattr(completion, "materialize_catalog_report_projection", materialize)
    monkeypatch.setattr(catalog, "verify_catalog_report_package",
                        lambda *a: (True, ()))
    monkeypatch.setattr(catalog, "catalog_report_is_fresh",
                        lambda **kwargs: True)
    result = a.run_acceptance(
        tmp_path, "AUD-659", host="approved.example.org",
        permitted_hostname="approved.example.org", authorized=True,
        series_id="test")
    assert result["status"] == "TECHNICAL_ACCEPTANCE_READY_FOR_HUMAN_REVIEW"
    assert result["catalog_integrity_verified"]
    assert result["audit_database_unchanged"]
    assert a._sha256_file(tmp_path / "audit.db") == original


def test_blocked_probe_does_not_pass_field_acceptance(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from rasai import network_acceptance as a
    from rasai import network_active_probe as p
    from rasai import report_completion as completion
    from rasai import catalog_report_site as catalog
    _workspace(tmp_path)
    monkeypatch.setattr(p, "collect_authorized_probe", lambda *args, **kw: tmp_path / "packet")
    monkeypatch.setattr(p, "read_authorized_probes", lambda *args: [{
        "audit_id": "AUD-659", "hostname": "approved.example.org",
        "port": 443, "state": "BLOCKED",
        "metrics": {"tcp_handshake_ms": {"state": "NOT_OBSERVED", "value": None}},
    }])
    def build(**kw):
        directory = tmp_path / "report-catalog"
        directory.mkdir(exist_ok=True)
        (directory / "network.html").write_text(
            "Medição complementar autorizada: approved.example.org",
            encoding="utf-8")
        return SimpleNamespace(renderer_errors=())
    monkeypatch.setattr(completion, "materialize_catalog_report_projection", build)
    monkeypatch.setattr(catalog, "verify_catalog_report_package", lambda *args: (True, ()))
    monkeypatch.setattr(catalog, "catalog_report_is_fresh", lambda **kw: True)
    result = a.run_acceptance(
        tmp_path, "AUD-659", host="approved.example.org",
        permitted_hostname="approved.example.org", authorized=True)
    assert result["status"] == "NETWORK_METRICS_OR_REPORT_INCOMPLETE"
    assert result["observed_tcp"] is False
