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



def test_worker_cli_requires_aud_scope_before_any_network(tmp_path, monkeypatch):
    import sys
    from rasai import network_active_probe as p
    _audit(tmp_path)
    def forbidden(*_a, **_kw):
        raise AssertionError("network must not start")
    monkeypatch.setattr(p, "_worker_probe", forbidden)
    monkeypatch.setattr(sys, "argv", [
        "rasai.network_active_probe", "--worker",
        "--host", "other.example.org", "--port", "443",
        "--authorize-active-network", "--workspace", str(tmp_path),
        "--audit-id", "AUD-G2", "--permit-exact-host", "other.example.org",
    ])
    with pytest.raises(SystemExit) as exc:
        p.main()
    assert exc.value.code != 0
    monkeypatch.setattr(sys, "argv", [
        "rasai.network_active_probe", "--worker",
        "--host", "website.example.org", "--port", "443",
        "--authorize-active-network",
    ])
    with pytest.raises(SystemExit) as exc:
        p.main()
    assert exc.value.code != 0


def test_child_command_carries_original_audit_scope(tmp_path, monkeypatch):
    _audit(tmp_path)
    from rasai import network_active_probe as p
    def controlled_child(cmd, **kwargs):
        assert "--audit-id" in cmd and cmd[cmd.index("--audit-id") + 1] == "AUD-G2"
        assert "--workspace" in cmd and cmd[cmd.index("--workspace") + 1] == str(tmp_path)
        assert "--permit-exact-host" in cmd
        assert "--authorize-active-network" in cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "contract": p.CONTRACT, "hostname": "website.example.org",
            "port": 443, "state": "BLOCKED", "metrics": {},
        }))
    monkeypatch.setattr(p.subprocess, "run", controlled_child)
    assert p.collect_authorized_probe(
        tmp_path, "AUD-G2", "website.example.org",
        permitted_hostname="website.example.org", authorized=True,
    ).is_file()


def test_traceroute_survives_tcp_connection_failure(monkeypatch):
    monkeypatch.setattr(p.socket, "getaddrinfo", lambda *a, **k: [
        (p.socket.AF_INET, p.socket.SOCK_STREAM, p.socket.IPPROTO_TCP, "",
         ("8.8.8.8", 443))
    ])
    class BrokenSocket:
        def settimeout(self, value):
            pass
        def connect(self, target):
            raise OSError("simulated tcp failure")
        def close(self):
            pass
    monkeypatch.setattr(p.socket, "socket", lambda *a, **k: BrokenSocket())
    observed = []
    def fake_trace(ip, port, *, max_hops):
        observed.append((ip, port, max_hops))
        return {"state": "OBSERVED", "value": {"hops": [
            {"hop": 1, "public_ip": "8.8.4.4", "state": "PUBLIC_HOP"}
        ], "target_reached": False}, "error": "ROUTE_NOT_CONFIRMED"}
    monkeypatch.setattr(p, "bounded_trace", fake_trace)
    item = p._worker_probe("website.example.org", 443, include_traceroute=True)
    assert item["state"] == "COLLECTION_FAILED"
    assert item["metrics"]["traceroute"]["state"] == "OBSERVED"
    assert observed == [("8.8.8.8", 443, 8)]



def test_transient_dns_recovers_once_without_unapproved_fallback(monkeypatch):
    """#666 H2/H3: a transient resolver answer can recover without changing scope."""
    approved_host = "www.hetzner.com"
    calls = []
    sleeps = []
    def dns(host, port, *, type, proto):
        calls.append((host, port, type, proto))
        if len(calls) == 1:
            raise p.socket.gaierror(p.socket.EAI_AGAIN, "temporary")
        return [(p.socket.AF_INET, p.socket.SOCK_STREAM,
                 p.socket.IPPROTO_TCP, "", ("213.133.116.44", 443))]

    monkeypatch.setattr(p.socket, "getaddrinfo", dns)
    monkeypatch.setattr(p.time, "sleep", lambda duration: sleeps.append(duration))
    class RefusedSocket:
        def settimeout(self, value):
            pass
        def connect(self, address):
            raise OSError("TCP not available")
        def close(self):
            pass
    monkeypatch.setattr(p.socket, "socket", lambda *args: RefusedSocket())
    traces = []
    def trace(ip, port, *, max_hops):
        traces.append((ip, port, max_hops))
        return {"state": "OBSERVED", "value": {
            "hops": [{"hop": 1, "state": "PUBLIC_HOP",
                      "public_ip": "8.8.8.8", "rtt_ms": 4.0}]},
            "error": "ROUTE_NOT_CONFIRMED"}
    monkeypatch.setattr(p, "bounded_trace", trace)
    row = p._worker_probe(approved_host, 443, include_traceroute=True)
    assert len(calls) == 2
    assert all(call[:2] == (approved_host, 443) for call in calls)
    assert sleeps == [p._DNS_TRANSIENT_RETRY_DELAY_SECONDS]
    assert row["resolver_diagnostics"] == {
        "source": "SYSTEM_GETADDRINFO", "attempts": 2, "status": "RESOLVED",
    }
    assert row["metrics"]["dns_resolution"]["state"] == "OBSERVED"
    assert row["metrics"]["dns_resolution"]["value"] == ["213.133.116.44"]
    assert row["metrics"]["traceroute"]["state"] == "OBSERVED"
    assert traces == [("213.133.116.44", 443, 8)]


def test_permanent_dns_failure_does_not_retry_or_infer_route(monkeypatch):
    calls = []
    def fail_dns(*args, **kwargs):
        calls.append(1)
        raise p.socket.gaierror(p.socket.EAI_NONAME, "opaque resolver error")
    monkeypatch.setattr(p.socket, "getaddrinfo", fail_dns)
    monkeypatch.setattr(p.time, "sleep", lambda _: pytest.fail("must not retry"))
    monkeypatch.setattr(p.socket, "socket",
                        lambda *args: pytest.fail("must not connect"))
    monkeypatch.setattr(p, "bounded_trace", lambda *args, **kwargs:
                        pytest.fail("must not trace"))
    row = p._worker_probe("www.hetzner.com", 443, include_traceroute=True)
    assert calls == [1]
    assert row["state"] == "COLLECTION_FAILED"
    assert row["metrics"]["dns_resolution"]["error"] == "DNS_NAME_RESOLUTION_FAILED"
    assert row["metrics"]["traceroute"]["state"] == "NOT_OBSERVED"
    assert row["resolver_diagnostics"]["category"] == "NAME_RESOLUTION"
    assert "opaque resolver error" not in json.dumps(row)


def test_transient_dns_failure_stops_after_two_queries(monkeypatch):
    calls = []
    def fail_dns(*args, **kwargs):
        calls.append(1)
        raise p.socket.gaierror(p.socket.EAI_AGAIN, "private exception text")
    monkeypatch.setattr(p.socket, "getaddrinfo", fail_dns)
    monkeypatch.setattr(p.time, "sleep", lambda _: None)
    monkeypatch.setattr(p.socket, "socket",
                        lambda *args: pytest.fail("must not connect"))
    monkeypatch.setattr(p, "bounded_trace", lambda *args, **kwargs:
                        pytest.fail("must not trace"))
    row = p._worker_probe("www.hetzner.com", 443, include_traceroute=True)
    assert len(calls) == 2
    assert row["metrics"]["dns_resolution"]["error"] == "DNS_TEMPORARY_FAILURE"
    assert row["resolver_diagnostics"]["attempts"] == 2
    assert "private exception text" not in json.dumps(row)


def test_resolver_other_os_error_is_not_misreported_as_dns_name_failure(monkeypatch):
    def fail_os(*args, **kwargs):
        raise OSError(12345, "confidential OS text")
    monkeypatch.setattr(p.socket, "getaddrinfo", fail_os)
    monkeypatch.setattr(p.time, "sleep", lambda _: pytest.fail("must not retry"))
    row = p._worker_probe("www.hetzner.com", 443)
    assert row["metrics"]["dns_resolution"]["error"] == "DNS_RESOLVER_OS_ERROR"
    assert row["resolver_diagnostics"]["category"] == "OS_ERROR"
    assert "confidential OS text" not in json.dumps(row)


def test_dns_private_answer_is_never_retried_after_public_only_guard(monkeypatch):
    calls = []
    def private_dns(*args, **kwargs):
        calls.append(1)
        return [(p.socket.AF_INET, p.socket.SOCK_STREAM, p.socket.IPPROTO_TCP,
                 "", ("192.168.0.1", 443))]
    monkeypatch.setattr(p.socket, "getaddrinfo", private_dns)
    monkeypatch.setattr(p.time, "sleep", lambda _: pytest.fail("unsafe answer must not retry"))
    monkeypatch.setattr(p.socket, "socket", lambda *args:
                        pytest.fail("unsafe answer must not connect"))
    row = p._worker_probe("www.hetzner.com", 443, include_traceroute=True)
    assert calls == [1]
    assert row["state"] == "BLOCKED"
    assert row["metrics"]["dns_resolution"]["error"] == "UNSAFE_DNS_ANSWER"
    assert row["metrics"]["traceroute"]["state"] == "NOT_OBSERVED"
