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
    assert "IP remoto público da captura</th><td>" not in page


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


def test_incomplete_sealed_network_consent_is_explained_without_new_probe(tmp_path, monkeypatch):
    """#666 Windows H1: enabled=true + authorized host blank is NOT consent."""
    import sqlite3
    import json
    import hashlib
    from rasai.network_reporting import (
        _incomplete_network_consent_notice, network_report_body,
    )

    audit_id = "AUD-TEST-NETWORK"
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as cx:
        cx.execute(
            "CREATE TABLE audit_execution_configurations "
            "(audit_id TEXT, configuration_kind TEXT, configuration_json TEXT)"
        )
        payload = {"settings": {"environment": {
            "RASAI_NETWORK_ACTIVE_ENABLED": "true",
            "RASAI_NETWORK_ACTIVE_HOST": "",
            "RASAI_NETWORK_MAX_HOPS": "16",
        }}, "targets": ["https://www.hetzner.com/"]}
        cx.execute(
            "INSERT INTO audit_execution_configurations VALUES (?, ?, ?)",
            (audit_id, "CONSOLE", json.dumps(payload)),
        )
    original_hash = hashlib.sha256(db.read_bytes()).hexdigest()

    notice = _incomplete_network_consent_notice(tmp_path, audit_id)
    assert "Sonda ativa: autorização incompleta" in notice
    assert "hostname autorizado" in notice
    assert "www.hetzner.com" not in notice  # never infer a grant from target
    assert "bloqueio de rede" in notice
    # This focused SQLite fixture contains only the canonical consent record;
    # browser capture fallback is outside this test's scope.
    from rasai import network_reporting as report
    monkeypatch.setattr(report, "snapshots_from_audit", lambda *_: [])
    monkeypatch.setattr(
        "rasai.network_intelligence_reporting.network_intelligence_section",
        lambda *_: "<section class='panel'>Sem medição</section>",
    )
    html = network_report_body(tmp_path, audit_id)
    assert "Sonda ativa: autorização incompleta" in html
    assert "Mapa e caminho de rede" in html
    assert "nenhum ponto ou trajeto físico" in html
    assert hashlib.sha256(db.read_bytes()).hexdigest() == original_hash
    assert not (tmp_path / "artifacts" / "network" / "probes").exists()

    # An exact authorized hostname should not trigger the incomplete notice.
    payload["settings"]["environment"]["RASAI_NETWORK_ACTIVE_HOST"] = "www.hetzner.com"
    with sqlite3.connect(db) as cx:
        cx.execute(
            "UPDATE audit_execution_configurations SET configuration_json=? "
            "WHERE audit_id=?",
            (json.dumps(payload), audit_id),
        )
    assert _incomplete_network_consent_notice(tmp_path, audit_id) == ""


def test_incomplete_consent_notice_fails_closed_on_old_audit_without_config(tmp_path):
    from rasai.network_reporting import _incomplete_network_consent_notice

    assert _incomplete_network_consent_notice(tmp_path, "AUD-OLD") == ""
    (tmp_path / "audit.db").write_bytes(b"not-a-database")
    assert _incomplete_network_consent_notice(tmp_path, "AUD-OLD") == ""


def test_h2_dns_resolution_failure_explains_missing_traceroute_and_map(
    tmp_path, monkeypatch,
) -> None:
    """H2: authorization + valid probe with DNS failure never implies a route."""
    from rasai import network_reporting as report

    captured = {
        "audit_id": "AUD-H2",
        "hostname": "www.hetzner.com",
        "capture_utc": "2026-10-27T17:54:58Z",
        "metrics": {
            "dns_resolution": {
                "state": "COLLECTION_FAILED", "error": "DNS_LOOKUP_FAILED", "value": None,
            },
            "traceroute": {"state": "NOT_OBSERVED", "value": None, "error": None},
            "geoip": {"state": "NOT_OBSERVED", "value": None, "error": None},
        },
    }
    monkeypatch.setattr(report, "read_network_observations", lambda *_: [])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [captured])
    monkeypatch.setattr(
        "rasai.network_intelligence_reporting.network_intelligence_section",
        lambda *_: "<section class='panel'>Resumo das evidências</section>",
    )
    html = report.network_report_body(tmp_path, "AUD-H2")
    assert "Medição complementar autorizada" in html
    assert "Por que não há rastreamento ou mapa" in html
    assert "não conseguiu resolver o nome do destino" in html
    assert "encerrou antes de executar TCP, traceroute e enriquecimento" in html
    assert "presença das bases MaxMind não resolve" in html
    assert "<svg" not in html
    assert "destino bloqueou" not in html

    captured["metrics"]["dns_resolution"] = {
        "state": "OBSERVED", "value": ["203.0.113.7"], "error": None,
    }
    html = report.network_report_body(tmp_path, "AUD-H2")
    assert "Por que não há rastreamento ou mapa" not in html



@pytest.mark.parametrize("code,category,attempts,expected", [
    ("DNS_TEMPORARY_FAILURE", "TEMPORARY", 2,
     "O resolvedor informou indisponibilidade temporária"),
    ("DNS_NAME_RESOLUTION_FAILED", "NAME_RESOLUTION", 1,
     "rejeitou a resolução do hostname"),
    ("DNS_RESOLVER_OS_ERROR", "OS_ERROR", 1,
     "erro de sistema não classificado como falha de nome"),
])
def test_dns_failure_classification_is_visible_without_os_secrets(
    tmp_path, monkeypatch, code, category, attempts, expected,
) -> None:
    """#666: diagnostic from approved probe, bounded and without raw OS details."""
    from rasai import network_reporting as report
    row = {
        "hostname": "www.hetzner.com",
        "resolver_diagnostics": {
            "source": "SYSTEM_GETADDRINFO", "category": category,
            "status": "FAILED", "attempts": attempts,
        },
        "metrics": {
            "dns_resolution": {"state": "COLLECTION_FAILED", "error": code},
            "traceroute": {"state": "NOT_OBSERVED"},
        },
    }
    monkeypatch.setattr(report, "read_network_observations", lambda *_: [])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [row])
    monkeypatch.setattr(
        "rasai.network_intelligence_reporting.network_intelligence_section",
        lambda *_: "<section>Consulta local</section>",
    )
    html = report.network_report_body(tmp_path, "AUD-DNS")
    assert expected in html
    assert "Tentativas DNS registradas: " + str(attempts) in html
    assert "<svg" not in html
    assert "resolver exception message" not in html


def test_legacy_unclassified_dns_failure_remains_explicit(tmp_path, monkeypatch) -> None:
    from rasai import network_reporting as report
    monkeypatch.setattr(report, "read_network_observations", lambda *_: [])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [{
        "hostname": "www.hetzner.com",
        "metrics": {
            "dns_resolution": {
                "state": "COLLECTION_FAILED", "error": "DNS_LOOKUP_FAILED",
            },
            "traceroute": {"state": "NOT_OBSERVED"},
        },
    }])
    monkeypatch.setattr(
        "rasai.network_intelligence_reporting.network_intelligence_section",
        lambda *_: "",
    )
    html = report.network_report_body(tmp_path, "AUD-H2")
    assert "pacote histórico não distingue falha DNS temporária" in html



def test_network_time_evidence_panel_is_discoverable_without_inference(tmp_path, monkeypatch):
    from rasai import network_reporting as report
    observation = {"device": "MOBILE", "capture_utc": "2026-10-25T12:00:00Z",
                   "capture_time_state": "OBSERVED", "metrics": {}}
    monkeypatch.setattr(report, "read_network_observations", lambda *_: [observation])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [])
    html = report.network_report_body(tmp_path, "AUD-659")
    assert "id='network-time-evidence'" in html
    assert "Datas e horários da rede" in html
    assert "25/10/2026 09:00:00 (America/Sao_Paulo)" in html
    assert html.index("Datas e horários da rede") < html.index("Observação do dispositivo")
    observation["capture_time_state"] = "NOT_OBSERVED"
    rejected = report.network_report_body(tmp_path, "AUD-659")
    assert "N/D (instante não comprovado)" in rejected

def _origin_fixtures():
    passive = {
        "audit_id": "AUD-751", "target_host": "example.org", "device": "MOBILE",
        "capture_utc": "2026-10-26T09:00:00Z", "capture_time_state": "OBSERVED",
        "metrics": {
            "connected_public_ip": {"state": "OBSERVED", "value": "8.8.4.4"},
        },
    }
    probe = {
        "audit_id": "AUD-751", "hostname": "example.org", "port": 80,
        "capture_utc": "2026-10-26T09:15:00Z",
        "measurement_origin": "LOCAL_OPERATOR_PROCESS",
        "method": "EXPLICIT_DNS_TCP_TLS_PROBE",
        "source": "LOCAL_SOCKET_STACK", "state": "OBSERVED",
        "metrics": {
            "connected_public_ip": {"state": "OBSERVED", "value": "8.8.8.8"},
            "local_socket_ip": {
                "state": "OBSERVED", "value": "10.17.0.24",
                "source": "SOCKET_GETSOCKNAME_AFTER_CONNECT",
            },
        },
    }
    return passive, probe


def test_origin_classifies_browser_process_remote_and_egress_separately():
    from rasai.network_connection_origin import origin_evidence

    passive, probe = _origin_fixtures()
    origin = origin_evidence([passive], [probe])
    assert len(origin) == 2
    assert origin[0]["kind"] == "Navegador da auditoria"
    assert origin[0]["remote_ip"] == "8.8.4.4"
    assert origin[0]["local_ip"] is None
    assert origin[0]["local_state"] == "NOT_OBSERVED"
    assert origin[1]["kind"] == "Processo executor"
    assert origin[1]["remote_ip"] == "8.8.8.8"
    assert origin[1]["local_ip"] == "10.17.0.24"
    assert origin[1]["local_state"] == "OBSERVED"
    assert all(row["egress_ip"] is None for row in origin)
    assert all(row["egress_state"] == "NOT_OBSERVED" for row in origin)

    legacy = dict(probe, metrics={"connected_public_ip": probe["metrics"]["connected_public_ip"]})
    assert origin_evidence([], [legacy])[0]["local_state"] == "NOT_OBSERVED"

    wrong_source = dict(probe, metrics={
        **probe["metrics"],
        "local_socket_ip": {**probe["metrics"]["local_socket_ip"],
                            "source": "UNVERIFIED_EXTERNAL_RESULT"},
    })
    rejected = origin_evidence([], [wrong_source])[0]
    assert rejected["local_ip"] is None
    assert rejected["local_state"] == "INCONCLUSIVE"
    invalid_ip = dict(probe, metrics={
        **probe["metrics"],
        "local_socket_ip": {**probe["metrics"]["local_socket_ip"], "value": "<script>alert(1)</script>"},
    })
    assert origin_evidence([], [invalid_ip])[0]["local_state"] == "INCONCLUSIVE"
    assert origin_evidence([], [invalid_ip])[0]["local_ip"] is None
    assert origin_evidence([], []) == []


def test_origin_catalog_humanized_in_audit_timezone_without_network(tmp_path, monkeypatch):
    """No network access, no writes to original AUD, no public-egress inference."""
    import sqlite3
    from rasai import network_reporting as reporting

    with sqlite3.connect(tmp_path / "audit.db") as cx:
        cx.execute(
            "CREATE TABLE audit_execution_configurations "
            "(audit_id TEXT, configuration_kind TEXT, configuration_json TEXT)"
        )
        cx.execute(
            "INSERT INTO audit_execution_configurations VALUES (?,?,?)",
            ("AUD-751", "CONSOLE", json.dumps({"settings": {
                "presentation": {"timezone": "America/Sao_Paulo"},
            }})),
        )
    source_before = (tmp_path / "audit.db").read_bytes()
    passive, probe = _origin_fixtures()
    monkeypatch.setattr(reporting, "read_network_observations", lambda *_: [passive])
    monkeypatch.setattr(reporting, "read_authorized_probes", lambda *_: [probe])

    page = reporting.network_report_body(tmp_path, "AUD-751")

    assert "<h2>Origem da conexão</h2>" in page
    assert "10.17.0.24" in page and "8.8.8.8" in page
    assert "IP público de saída não identificado" in page
    assert "26/10/2026 06:15:00 (America/Sao_Paulo)" in page
    assert "SOCKET_GETSOCKNAME_AFTER_CONNECT" not in page
    assert (tmp_path / "audit.db").read_bytes() == source_before


def test_origin_presentation_reuses_verified_probes_and_never_uses_map_to_infer_ip(
    tmp_path, monkeypatch,
):
    from rasai.parallel_report import scope_context as view

    passive, probe = _origin_fixtures()
    monkeypatch.setattr(view, "read_network_observations", lambda *_: [passive])
    monkeypatch.setattr(view, "read_authorized_probes", lambda *_: [probe])
    monkeypatch.setattr(view, "build_network_assessment", lambda *_: None)
    monkeypatch.setattr(view, "network_geographic_panel", lambda *_a, **_k: "")
    monkeypatch.setattr(view, "unlocated_world_map", lambda **_k: "")
    monkeypatch.setattr(view, "register_payload", lambda *_: None)
    primary = {}

    body, events, inventory = view.network_context(
        tmp_path, "AUD-751", "America/Sao_Paulo", primary=primary,
    )

    assert "Origem da conexão" in primary["rede:primary"]
    assert "10.17.0.24" in primary["rede:primary"]
    assert "IP público de saída" in primary["rede:primary"]
    assert "Não identificado" in primary["rede:primary"]
    assert "26/10/2026 06:15:00" in primary["rede:primary"]
    assert "Navegador da auditoria" in primary["rede:primary"]
    assert "Processo executor" in primary["rede:primary"]
    assert "SOCKET_GETSOCKNAME_AFTER_CONNECT" not in primary["rede:primary"]
    assert "Origem da conexão" not in body
    assert events and inventory

def test_logical_topology_and_ip_inventory_evidence_bound_offline():
    from rasai.network_logical_topology import logical_network_sections

    passive, probe = _origin_fixtures()
    probe["metrics"]["dns_resolution"] = {
        "state": "OBSERVED", "value": ["8.8.8.8", "1.1.1.1", "10.0.0.1"],
    }
    probe["metrics"]["traceroute"] = {
        "state": "OBSERVED",
        "value": {"target_reached": False, "hops": [
            {"hop": 1, "state": "PRIVATE_HOP_REDACTED", "public_ip": None},
            {"hop": 2, "state": "PUBLIC_HOP", "public_ip": "9.9.9.9"},
            {"hop": 3, "state": "NO_REPLY", "public_ip": None},
        ]},
    }

    html = logical_network_sections([passive], [probe], "America/Sao_Paulo")

    assert "<h2>Topologia lógica observada</h2>" in html
    assert "<h2>Inventário de endereços IP observados</h2>" in html
    assert "Ponto inicial: endereço local do navegador não identificado" in html
    assert html.index("Ponto inicial do processo: 10.17.0.24") < html.index("Salto 1:")
    assert html.index("Salto 1:") < html.index("Salto 2: 9.9.9.9")
    assert html.index("Salto 3: sem resposta") < html.index("Destino da conexão TCP: 8.8.8.8")
    assert "Chegada pelo traceroute não confirmada" in html
    assert "Candidato DNS (conexão não comprovada)" in html
    assert "1.1.1.1" in html and "8.8.4.4" in html
    assert "Salto público 2" in html
    assert "10.0.0.1" not in html  # DNS privado nunca vira observação pública
    assert "26/10/2026 06:15:00 (America/Sao_Paulo)" in html
    assert "SOCKET_GETSOCKNAME_AFTER_CONNECT" not in html
    assert "IP público de saída: <strong>Não identificado</strong>" in html


def test_logical_topology_abstains_on_legacy_invalid_and_missing_evidence():
    from rasai.network_logical_topology import logical_network_sections

    passive, probe = _origin_fixtures()
    legacy = dict(probe, metrics={
        "connected_public_ip": {"state": "NOT_OBSERVED", "value": "8.8.8.8"},
        "dns_resolution": {"state": "COLLECTION_FAILED", "value": ["1.1.1.1"]},
        "local_socket_ip": {"state": "OBSERVED", "value": "10.17.0.24", "source": "UNKNOWN"},
        "traceroute": {"state": "OBSERVED", "value": {"hops": [
            {"hop": 1, "state": "PUBLIC_HOP", "public_ip": "bad<script>"},
            {"hop": 2, "state": "NO_REPLY", "public_ip": "9.9.9.9"},
        ]}},
    })
    html = logical_network_sections([], [legacy], "UTC")
    assert "Ponto inicial do processo: Não identificado" in html
    assert "Destino da conexão TCP: não identificado" in html
    assert "endereço não verificável" in html
    assert "10.17.0.24" not in html
    assert "8.8.8.8" not in html and "1.1.1.1" not in html
    assert "9.9.9.9" not in html  # NO_REPLY never becomes a public hop
    assert "<script>" not in html
    assert "Nenhum endereço IP verificável identificado" in html
    assert "Não identificado" in logical_network_sections([], [], "UTC")


def test_logical_inventory_is_shared_by_both_reports_without_new_network(
    tmp_path, monkeypatch,
):
    from rasai import network_reporting as report
    from rasai.parallel_report import scope_context as view

    passive, probe = _origin_fixtures()
    probe["metrics"]["dns_resolution"] = {
        "state": "OBSERVED", "value": ["8.8.8.8", "1.1.1.1"],
    }
    monkeypatch.setattr(report, "read_network_observations", lambda *_: [passive])
    monkeypatch.setattr(report, "read_authorized_probes", lambda *_: [probe])
    monkeypatch.setattr(view, "read_network_observations", lambda *_: [passive])
    monkeypatch.setattr(view, "read_authorized_probes", lambda *_: [probe])
    monkeypatch.setattr(view, "build_network_assessment", lambda *_: None)
    monkeypatch.setattr(view, "network_geographic_panel", lambda *_a, **_k: "")
    monkeypatch.setattr(view, "unlocated_world_map", lambda **_k: "")
    monkeypatch.setattr(view, "register_payload", lambda *_: None)
    db = tmp_path / "audit.db"
    db.write_bytes(b"original-sealed-placeholder")
    previous = db.read_bytes()

    catalog = report.network_report_body(tmp_path, "AUD-751")
    primary = {}
    _body, _events, _inventory = view.network_context(
        tmp_path, "AUD-751", "America/Sao_Paulo", primary=primary,
    )
    presentation = primary["rede:primary"]
    for page in (catalog, presentation):
        assert "Topologia lógica observada" in page
        assert "Inventário de endereços IP observados" in page
        assert "10.17.0.24" in page and "1.1.1.1" in page
        assert "IP público de saída: <strong>Não identificado</strong>" in page
    assert db.read_bytes() == previous

