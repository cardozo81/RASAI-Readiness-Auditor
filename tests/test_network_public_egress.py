"""Offline and isolated coverage for opt-in public-IP service fallback."""
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

from rasai import network_public_egress as e
from rasai import network_active_probe as probe
from rasai.network_connection_origin import origin_evidence
from rasai.network_logical_topology import logical_network_sections
from rasai.network_map import network_geographic_panel, network_map_locations
from rasai.network_public_egress_view import egress_label, public_egress_panel


class Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return self.body[:size]


class ScriptedOpener:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        response = self.responses[request.full_url]
        if isinstance(response, Exception):
            raise response
        return Response(response)


SETTINGS = {
    e.ENABLED: "true",
    e.IPIFY_ENABLED: "true",
    e.IDENTME_ENABLED: "true",
}


def test_disabled_globally_performs_no_external_request():
    opener = ScriptedOpener({})
    assert e.discover_public_egress({e.ENABLED: "false"}, opener=opener)["state"] == "NOT_REQUESTED"
    assert e.discover_public_egress({}, opener=opener)["state"] == "NOT_REQUESTED"
    assert not opener.calls


def test_each_provider_can_be_individually_disabled():
    outputs = {
        "https://4.ident.me": b"8.8.8.8\n",
        "https://6.ident.me": b"2606:4700:4700::1111\n",
    }
    env = {**SETTINGS, e.IPIFY_ENABLED: "false"}
    op = ScriptedOpener(outputs)
    result = e.discover_public_egress(env, opener=op)
    assert result["state"] == "OBSERVED"
    assert result["providers_enabled"] == ["IDENTME"]
    assert len(op.calls) == 2
    assert all("ident.me" in url for url, _ in op.calls)
    assert e.verified_families(result)[4]["ip"] == "8.8.8.8"
    assert e.verified_families(result)[6]["ip"] == "2606:4700:4700::1111"
    assert e.discover_public_egress({**SETTINGS, e.IPIFY_ENABLED: "false",
                                      e.IDENTME_ENABLED: "false"},
                                     opener=ScriptedOpener({}))["state"] == "NOT_REQUESTED"


def test_primary_failure_triggers_independent_family_fallback():
    op = ScriptedOpener({
        e.ENDPOINTS["IPIFY"][4]: URLError(TimeoutError()),
        e.ENDPOINTS["IPIFY"][6]: HTTPError(e.ENDPOINTS["IPIFY"][6], 429, "busy", None, None),
        e.ENDPOINTS["IDENTME"][4]: b"8.8.4.4",
        e.ENDPOINTS["IDENTME"][6]: b"2606:4700:4700::1001",
    })
    result = e.discover_public_egress(SETTINGS, opener=op)
    assert result["state"] == "OBSERVED"
    assert [r["provider"] for r in e.verified_families(result).values()] == ["IDENTME", "IDENTME"]
    assert result["families"]["ipv4"]["attempts"][0]["reason"] == "TIMEOUT"
    assert result["families"]["ipv6"]["attempts"][0]["reason"] == "RATE_LIMITED"
    assert len(op.calls) == 4
    assert all(timeout == e.TIMEOUT_SECONDS for _, timeout in op.calls)
    assert e.error_summary(result) is None


def test_family_unavailable_is_partial_and_notice_has_humanized_reason():
    op = ScriptedOpener({
        e.ENDPOINTS["IPIFY"][4]: b'{"ip":"8.8.8.8"}',
        e.ENDPOINTS["IPIFY"][6]: URLError(OSError("unreachable")),
        e.ENDPOINTS["IDENTME"][6]: URLError(TimeoutError()),
    })
    result = e.discover_public_egress(SETTINGS, opener=op)
    assert result["state"] == "PARTIAL"
    assert e.verified_families(result)[4]["ip"] == "8.8.8.8"
    assert 6 not in e.verified_families(result)
    assert "IPv6" in e.error_summary(result)
    html = public_egress_panel([{"public_egress": result}], "America/Sao_Paulo")
    assert "Descoberta de IPs parcial" in html
    assert "O serviço não respondeu" in html
    assert "RasaiInternalToken" not in html
    assert "8.8.8.8" in html


def test_wrong_family_private_or_invalid_data_uses_fallback_without_false_ip():
    op = ScriptedOpener({
        e.ENDPOINTS["IPIFY"][4]: b'{"ip":"192.168.1.20"}',
        e.ENDPOINTS["IPIFY"][6]: b'{"ip":"8.8.8.8"}',
        e.ENDPOINTS["IDENTME"][4]: b"1.1.1.1",
        e.ENDPOINTS["IDENTME"][6]: b"2606:4700:4700::1111",
    })
    result = e.discover_public_egress(SETTINGS, opener=op)
    assert result["state"] == "OBSERVED"
    assert all(result["families"]["ipv" + str(n)]["attempts"][0]["reason"] ==
               "INVALID_RESPONSE" for n in (4, 6))
    assert e.verified_families(result)[4]["ip"] == "1.1.1.1"
    assert e.verified_families(result)[6]["ip"] == "2606:4700:4700::1111"


def test_total_service_failure_does_not_forge_results():
    op = ScriptedOpener({url: URLError(TimeoutError()) for endpoints in
                         e.ENDPOINTS.values() for url in endpoints.values()})
    result = e.discover_public_egress(SETTINGS, opener=op)
    assert result["state"] == "UNAVAILABLE"
    assert e.verified_families(result) == {}
    assert "IPv4" in e.error_summary(result) and "IPv6" in e.error_summary(result)


def test_packet_persisted_with_provenance_and_unmodified_main_db(tmp_path, monkeypatch):
    workspace = tmp_path / "AUD-TEST"
    workspace.mkdir()
    db = workspace / "audit.db"
    with sqlite3.connect(db) as cx:
        cx.execute("CREATE TABLE audits (audit_id TEXT)")
        cx.execute("INSERT INTO audits VALUES ('AUD-TEST')")
        cx.execute("CREATE TABLE pages (audit_id TEXT, normalized_url TEXT)")
        cx.execute("INSERT INTO pages VALUES ('AUD-TEST', 'https://www.example.org')")
    baseline = db.read_bytes()
    record = {
        "contract": probe.CONTRACT, "hostname": "www.example.org",
        "port": 443, "capture_utc": "2026-11-23T10:00:00Z",
        "measurement_origin": "LOCAL_OPERATOR_PROCESS",
        "method": "EXPLICIT_DNS_TCP_TLS_PROBE", "source": "LOCAL_SOCKET_STACK",
        "state": "OBSERVED", "metrics": {
            "connected_public_ip": {"state": "OBSERVED", "value": "1.1.1.1"},
            "local_socket_ip": {"state": "OBSERVED", "value": "192.168.0.7",
                "source": "SOCKET_GETSOCKNAME_AFTER_CONNECT"},
        },
    }
    def fake_run(*_, **__):
        return SimpleNamespace(returncode=0, stdout=json.dumps(record))
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    monkeypatch.setattr(probe, "local_databases", lambda: {"city_database": None, "asn_database": None})
    monkeypatch.setenv(e.ENABLED, "true")
    monkeypatch.setenv(e.IPIFY_ENABLED, "true")
    monkeypatch.setenv(e.IDENTME_ENABLED, "false")
    monkeypatch.setattr(e, "_opener", lambda: ScriptedOpener({
        e.ENDPOINTS["IPIFY"][4]: b'{"ip":"8.8.8.8"}',
        e.ENDPOINTS["IPIFY"][6]: URLError(TimeoutError()),
    }))
    saved = probe.collect_authorized_probe(
        workspace, "AUD-TEST", "www.example.org",
        permitted_hostname="www.example.org", authorized=True,
    )
    assert saved.is_file()
    assert db.read_bytes() == baseline
    loaded = probe.read_authorized_probes(workspace, "AUD-TEST")
    assert len(loaded) == 1
    assert loaded[0]["public_egress"]["state"] == "PARTIAL"
    assert origin_evidence([], loaded)[0]["egress_ip"] == "IPv4: 8.8.8.8"
    topology = logical_network_sections([], loaded, "America/Sao_Paulo")
    assert "IPv4" in topology and "8.8.8.8" in topology
    assert "192.168.0.7" in topology
    assert "1.1.1.1" in topology


def test_geoip_map_only_for_verified_egress_position():
    packet = {
        "state": "PARTIAL",
        "families": {
            "ipv4": {
                "state": "OBSERVED", "ip": "8.8.8.8", "provider": "IPIFY",
                "capture_utc": "2026-11-23T10:00:00Z",
                "enrichment": {"geoip": {"state": "OBSERVED", "value": {
                    "latitude": -30.03, "longitude": -51.22,
                    "accuracy_radius_km": 25, "source": "LOCAL_MMDB_CITY",
                }}, "asn": {"state": "NOT_OBSERVED", "value": None}},
            },
            "ipv6": {"state": "UNAVAILABLE", "attempts": []},
        },
    }
    probes = [{"hostname": "example.org", "capture_utc": "2026-11-23T10:00:00Z",
               "metrics": {}, "public_egress": packet}]
    assert network_map_locations(probes)
    html = network_geographic_panel(probes, presentation_mode=True)
    assert "Saída pública IPv4: 8.8.8.8" in html
    assert "Ponto" in html
    packet["families"]["ipv4"]["enrichment"]["geoip"]["value"]["accuracy_radius_km"] = None
    assert network_map_locations(probes) == {}
