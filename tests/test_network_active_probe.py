"""Focused G2 safety cases; no network traffic in tests."""
import hashlib
import json
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest

from rasai import network_active_probe as p


def _audit(tmp_path):
    with sqlite3.connect(tmp_path / "audit.db") as db:
        db.executescript("""
            CREATE TABLE audits (audit_id TEXT);
            CREATE TABLE pages (audit_id TEXT, normalized_url TEXT);
            INSERT INTO audits VALUES ('AUD-G2');
            INSERT INTO pages VALUES ('AUD-G2', 'https://website.example.org/home');
        """)


def test_host_scope_and_fail_closed_dns():
    assert p._host("Website.Example.Org.") == "website.example.org"
    for host in ("localhost", "app.internal", "127.0.0.1", "bad/path", "bad..com"):
        with pytest.raises(ValueError):
            p._host(host)
    with pytest.raises(ValueError):
        p._public_ips([
            (p.socket.AF_INET, None, None, None, ("8.8.8.8", 443)),
            (p.socket.AF_INET, None, None, None, ("10.0.0.1", 443)),
        ])
    assert p._public_ips([
        (p.socket.AF_INET, None, None, None, ("8.8.8.8", 443))
    ]) == [(p.socket.AF_INET, "8.8.8.8")]


def test_probes_require_explicit_consent_and_matching_aud_scope(tmp_path, monkeypatch):
    _audit(tmp_path)
    def should_not_spawn(*a, **k):
        raise AssertionError("no child process permitted")
    monkeypatch.setattr(p.subprocess, "run", should_not_spawn)
    with pytest.raises(ValueError):
        p.collect_authorized_probe(tmp_path, "AUD-G2", "website.example.org",
                                   permitted_hostname="website.example.org", authorized=False)
    with pytest.raises(ValueError):
        p.collect_authorized_probe(tmp_path, "AUD-G2", "other.example.org",
                                   permitted_hostname="other.example.org", authorized=True)
    with pytest.raises(ValueError):
        p.collect_authorized_probe(tmp_path, "AUD-G2", "website.example.org",
                                   permitted_hostname="other.example.org", authorized=True)


def test_authorized_probe_writes_immutable_verified_sidecar(tmp_path, monkeypatch):
    _audit(tmp_path)
    def fake_worker(cmd, **kwargs):
        assert cmd[3] == "--worker" and "--authorize-active-network" in cmd and kwargs["timeout"] == 10
        row = p._worker_probe.__name__
        assert row
        payload = {
            "contract": p.CONTRACT, "hostname": "website.example.org", "port": 443,
            "capture_utc": "2026-10-26T10:00:00Z", "state": "COLLECTION_FAILED",
            "metrics": {"dns_resolution": {"state": "COLLECTION_FAILED", "value": None}},
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))
    monkeypatch.setattr(p.subprocess, "run", fake_worker)
    path = p.collect_authorized_probe(
        tmp_path, "AUD-G2", "website.example.org",
        permitted_hostname="website.example.org", authorized=True,
    )
    assert path.is_file()
    assert len(p.read_authorized_probes(tmp_path, "AUD-G2")) == 1
    original = (tmp_path / "audit.db").read_bytes()
    with pytest.raises(FileExistsError):
        p.collect_authorized_probe(
            tmp_path, "AUD-G2", "website.example.org",
            permitted_hostname="website.example.org", authorized=True,
        )
    assert (tmp_path / "audit.db").read_bytes() == original
    row = json.loads(path.read_text(encoding="utf-8"))
    row["metrics"]["dns_resolution"]["state"] = "OBSERVED"
    path.write_text(json.dumps(row), encoding="utf-8")
    assert p.read_authorized_probes(tmp_path, "AUD-G2") == []


def test_worker_dns_private_answer_blocks_tcp(monkeypatch):
    monkeypatch.setattr(p.socket, "getaddrinfo", lambda *a, **k: [
        (p.socket.AF_INET, p.socket.SOCK_STREAM, p.socket.IPPROTO_TCP, "",
         ("192.168.0.1", 443)),
    ])
    monkeypatch.setattr(p.socket, "socket", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not open socket")))
    item = p._worker_probe("website.example.org", 443)
    assert item["state"] == "BLOCKED"
    assert item["metrics"]["tcp_handshake_ms"]["state"] == "NOT_OBSERVED"


def test_parent_enforces_end_to_end_timeout(tmp_path, monkeypatch):
    _audit(tmp_path)
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=10)
    monkeypatch.setattr(p.subprocess, "run", timeout)
    with pytest.raises(TimeoutError):
        p.collect_authorized_probe(
            tmp_path, "AUD-G2", "website.example.org",
            permitted_hostname="website.example.org", authorized=True,
        )
    assert not list((tmp_path / "artifacts").glob("**/*.json"))
