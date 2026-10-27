"""#659 G1: sidecar should never mutate frozen audit bytes."""
import json
import pytest

from rasai.network_observation_store import (
    persist_network_observations, read_network_observations, sidecar_path,
)
from rasai.network_reporting import materialize_network_report


def test_legacy_report_is_neutral(tmp_path):
    page = materialize_network_report(tmp_path, "AUD-LEGACY")
    assert "Dados ainda indisponíveis" in page.read_text(encoding="utf-8")
    assert not sidecar_path(tmp_path).exists()


def test_sidecar_requires_audit_and_valid_id(tmp_path):
    assert persist_network_observations(tmp_path, "AUD-LEGACY") is None
    with pytest.raises(ValueError):
        persist_network_observations(tmp_path, "../escape")


def test_reader_rejects_foreign_audit(tmp_path):
    dest = sidecar_path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_text(json.dumps({"contract": "rasai-network-observation-v1", "audit_id": "AUD-OTHER", "observations": []}))
    assert read_network_observations(tmp_path, "AUD-LEGACY") == []


def test_tampered_sidecar_is_rejected(tmp_path):
    from rasai.network_observation import CONTRACT
    import hashlib
    dest = sidecar_path(tmp_path)
    dest.parent.mkdir(parents=True)
    row = {"contract": CONTRACT, "audit_id": "AUD-X", "observation_id": "SN-X",
           "metrics": {"http_status": {"state": "OBSERVED", "value": 200}}}
    canonical = json.dumps(row, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False).encode("utf-8")
    row["sha256"] = hashlib.sha256(canonical).hexdigest()
    row["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
    payload = {"contract": CONTRACT, "audit_id": "AUD-X", "observations": [row]}
    dest.write_text(json.dumps(payload), encoding="utf-8")
    assert len(read_network_observations(tmp_path, "AUD-X")) == 1
    payload["observations"][0]["metrics"]["http_status"]["value"] = 500
    dest.write_text(json.dumps(payload), encoding="utf-8")
    assert read_network_observations(tmp_path, "AUD-X") == []


def test_report_does_not_mutate_sealed_catalog_directory(tmp_path):
    page = materialize_network_report(tmp_path, "AUD-LEGACY")
    assert page.parent.name == "report"
    assert "network" in page.parts
    assert not (tmp_path / "report-catalog").exists()

def test_network_body_is_read_only_on_legacy(tmp_path):
    from rasai.network_reporting import network_report_body
    assert "Dados ainda indisponíveis" in network_report_body(tmp_path, "AUD-LEGACY")
    assert not (tmp_path / "report-catalog").exists()


def test_invalid_packet_is_explicitly_reported(tmp_path):
    from rasai.network_reporting import network_report_body
    path = sidecar_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('{"contract":"invalid"}', encoding="utf-8")
    page = network_report_body(tmp_path, "AUD-X")
    assert "Dados de rede não verificáveis" in page
    assert "não passou na validação" in page
    assert "Endereço público da conexão observada</th><td>" not in page


def test_reader_handles_missing_and_oversized_packet(tmp_path):
    assert read_network_observations(tmp_path, "AUD-X") == []
    path = sidecar_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * 2_000_001)
    assert read_network_observations(tmp_path, "AUD-X") == []



def test_network_metric_presentation_localizes_only_display_values() -> None:
    from rasai.network_reporting import _display_observed_metric

    assert _display_observed_metric("dns_elapsed_ms", 91.62) == "91,62"
    assert _display_observed_metric("tcp_handshake_ms", 24.57) == "24,57"
    assert _display_observed_metric("tls_handshake_ms", 32.11) == "32,11"
    assert _display_observed_metric("tls_protocol", "TLSv1.3") == "TLS 1.3"
    assert _display_observed_metric("connected_public_ip", "54.207.44.85") == "54.207.44.85"
    assert _display_observed_metric("dns_resolution", None) == "Sem medição disponível"


def test_network_capture_and_complement_are_explained_before_map(tmp_path, monkeypatch) -> None:
    from rasai import network_reporting as report

    root = tmp_path
    audit_id = "AUD-659"
    original = {
        "audit_id": audit_id,
        "target_host": "example.org",
        "device": "MOBILE",
        "capture_utc": "2026-10-25T12:00:00Z",
        "capture_time_state": "OBSERVED",
        "metrics": {"tcp_handshake_ms": {"state": "NOT_OBSERVED"}},
    }
    complementary = {
        "audit_id": audit_id,
        "hostname": "example.org",
        "capture_utc": "2026-10-26T12:00:00Z",
        "metrics": {"tcp_handshake_ms": {"state": "OBSERVED", "value": 24.57}},
    }
    monkeypatch.setattr(report, "read_network_observations", lambda *_: [original])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [complementary])
    html = report.network_report_body(root, audit_id)
    assert "Como interpretar as medições" in html
    assert "registros independentes" in html
    assert "24,57" in html
    assert html.index("Como interpretar as medições") < html.index("Observação do dispositivo")
    assert html.index("Medição complementar autorizada") < html.index("Mapa e caminho de rede")


@pytest.mark.parametrize(
    "error, expected",
    [
        ("TRACE_TIME_BUDGET_EXCEEDED", "Tempo limite excedido durante o rastreamento"),
        ("UNTRUSTED_SECRET_VALUE", "Rastreamento inconclusivo por falha técnica"),
    ],
)
def test_trace_failure_is_explained_without_exposing_raw_errors_or_hops(
        tmp_path, monkeypatch, error, expected) -> None:
    from rasai import network_reporting as report

    monkeypatch.setattr(report, "read_network_observations", lambda *_: [])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [{
        "audit_id": "AUD-666",
        "hostname": "example.org",
        "capture_utc": "2026-10-26T22:49:48Z",
        "metrics": {
            "traceroute": {
                "state": "INCONCLUSIVE",
                "error": error,
                "value": None,
            },
        },
    }])

    page = report.network_report_body(tmp_path, "AUD-666")
    assert "Saltos lógicos de rede" in page
    assert expected in page
    assert error not in page
    assert "Etapas conhecidas do caminho" not in page
    assert not (tmp_path / "report-catalog").exists()
