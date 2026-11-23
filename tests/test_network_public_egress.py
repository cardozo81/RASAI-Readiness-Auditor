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
    assert e.discover_public_egress({e.ENABLED: "false"}, opener=opener)["state"] == "NOT_REQUESTED"
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


def test_default_enabled_can_be_disabled_per_session_or_ini():
    assert e.enabled_providers({}) == ("IPIFY", "IDENTME")
    assert e.enabled_providers({e.ENABLED: "false"}) == ()
    assert e.enabled_providers({e.ENABLED: "true", e.IPIFY_ENABLED: "false"}) == ("IDENTME",)
    assert e.enabled_providers({e.ENABLED: "true", e.IDENTME_ENABLED: "false"}) == ("IPIFY",)


def test_standalone_packet_persisted_with_provenance_unmodified_main_db(tmp_path, monkeypatch):
    from rasai import network_public_egress_capture as capture
    workspace = tmp_path / "AUD-TEST"
    workspace.mkdir()
    db = workspace / "audit.db"
    with sqlite3.connect(db) as cx:
        cx.execute("CREATE TABLE audits (audit_id TEXT)")
        cx.execute("INSERT INTO audits VALUES ('AUD-TEST')")
    baseline = db.read_bytes()
    expected = e.discover_public_egress(
        SETTINGS, opener=ScriptedOpener({
            e.ENDPOINTS["IPIFY"][4]: b'{"ip":"8.8.8.8"}',
            e.ENDPOINTS["IPIFY"][6]: URLError(TimeoutError()),
            e.ENDPOINTS["IDENTME"][6]: URLError(TimeoutError()),
        })
    )
    assert expected["state"] == "PARTIAL"
    monkeypatch.setattr(capture, "collect_bounded", lambda _env: expected)
    # The GeoIP import happens inside capture: disable enrichment explicitly.
    monkeypatch.setenv("RASAI_NETWORK_GEOIP_SOURCE", "DISABLED")
    monkeypatch.setenv(e.ENABLED, "true")
    path = capture.capture_public_egress(workspace, "AUD-TEST")
    assert path is not None and path.is_file()
    assert db.read_bytes() == baseline
    assert capture.capture_public_egress(workspace, "AUD-TEST") is None
    probe_row = capture.read_public_egress_probe(workspace, "AUD-TEST")
    assert probe_row and probe_row["hostname"] is None
    assert probe_row["metrics"] == {}
    assert origin_evidence([], [probe_row])[0]["egress_ip"] == "IPv4: 8.8.8.8"
    topology = logical_network_sections([], [probe_row], "America/Sao_Paulo")
    assert "IPv4" in topology and "8.8.8.8" in topology
    assert "Destino da conexão TCP" not in topology
    assert "8.8.8.8" in public_egress_panel([probe_row], "America/Sao_Paulo")
    tampered = path.read_text(encoding="utf-8").replace("8.8.8.8", "1.1.1.1")
    path.write_text(tampered, encoding="utf-8")
    assert capture.read_public_egress_probe(workspace, "AUD-TEST") is None


def test_auto_dispatch_default_without_target_probe_and_saved_disable(tmp_path, monkeypatch):
    from rasai import network_auto_probe as auto
    from rasai import network_public_egress_capture as capture
    root = tmp_path / "AUD-TEST"
    root.mkdir()
    (root / "audit.db").write_bytes(b"fixture")
    monkeypatch.setattr(auto, "_approved_host", lambda: None)
    monkeypatch.setattr(auto, "resolve_config_path", lambda: tmp_path / "rasai-console.ini")
    monkeypatch.delenv(e.ENABLED, raising=False)
    monkeypatch.delenv(e.IPIFY_ENABLED, raising=False)
    monkeypatch.delenv(e.IDENTME_ENABLED, raising=False)
    observed = []
    monkeypatch.setattr(auto.subprocess, "Popen", lambda cmd, **kw: observed.append((cmd,kw)))
    result = auto.dispatch_for_new_audit(root, "AUD-TEST")
    assert result["state"] == "NOT_AUTHORIZED"  # Target TCP probe stays disabled.
    assert result["egress_state"] == "DISPATCHED"
    assert len(observed) == 1
    assert "rasai.network_public_egress_capture" in observed[0][0]
    assert observed[0][1]["env"][e.ENABLED] == "true"
    assert "HTTPS_PROXY" not in observed[0][1]["env"]
    assert "RASAI_PROVIDER_API_KEY" not in observed[0][1]["env"]
    config = tmp_path / "rasai-console.ini"
    config.write_text(
        "[environment]\nRASAI_NETWORK_EGRESS_ENABLED = false\n",
        encoding="utf-8",
    )
    observed.clear()
    result = auto.dispatch_for_new_audit(root, "AUD-TEST")
    assert result["egress_state"] == "DISABLED"
    assert not observed


def test_whole_external_subprocess_timeout_does_not_block_audit(monkeypatch):
    import subprocess
    def forced_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=kwargs["timeout"])
    monkeypatch.setattr(e.subprocess, "run", forced_timeout)
    result = e.collect_bounded(SETTINGS)
    assert result["state"] == "UNAVAILABLE"
    assert "prazo" in e.error_summary(result)

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
