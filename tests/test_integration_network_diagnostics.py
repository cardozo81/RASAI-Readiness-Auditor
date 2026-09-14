from __future__ import annotations

from datetime import datetime, timezone

from rasai import integration_network_diagnostics as network
from rasai.integration_diagnostics import (
    STATUS_OPERATIONAL_LIMITED,
    STATUS_TRANSIENT_FAILURE,
    IntegrationDiagnostic,
    get_integration_spec,
)


def _diagnostic(spec, *, status=STATUS_TRANSIENT_FAILURE, category="NETWORK", http_status=None):
    return IntegrationDiagnostic(
        integration_id=spec.id,
        label=spec.label,
        checked_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        category=category,
        detail="test",
        action="test",
        configuration_fingerprint="fingerprint",
        latency_ms=125,
        http_status=http_status,
        probe_cost=spec.probe_cost,
        validated_facets=("configuration",),
    )


def _layer(*, endpoint="https://service.example", dns="OK", tcp="OK", tls="OK", attempts=1, code="", detail=""):
    return network._LayerProbe(
        endpoint=endpoint,
        host="service.example",
        port=443,
        dns_status=dns,
        tcp_status=tcp,
        tls_status=tls,
        attempt_count=attempts,
        latencies_ms=(10,) * attempts,
        error_code=code,
        error_detail=detail,
    )


def test_copilot_network_target_is_runtime_host_not_generic_github_api() -> None:
    spec = get_integration_spec("ai:copilot")
    assert spec is not None
    assert network.endpoint_for_spec(spec) == "https://api.githubcopilot.com/_ping"


def test_real_http_503_proves_transport_path_and_does_not_trigger_socket_retries() -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    result = _diagnostic(spec, status=STATUS_TRANSIENT_FAILURE, category="PROVIDER_UNAVAILABLE", http_status=503)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("HTTP response already proves the network path; no low-level retry is needed")

    assessment = network.assess_network(spec, result, layer_probe=forbidden)
    assert assessment.classification == network.NETWORK_PATH_OK
    assert assessment.http_status == 503
    assert assessment.inferred_from_http is True
    assert assessment.dns_status == "OK"
    assert assessment.tcp_status == "OK"
    assert assessment.tls_status == "OK"


def test_persistent_tcp_failure_with_control_ok_is_destination_specific(monkeypatch) -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    result = _diagnostic(spec, status=STATUS_TRANSIENT_FAILURE, category="NETWORK", http_status=None)
    monkeypatch.setattr(network, "_proxy_configured", lambda: False)

    def fake_probe(endpoint, attempts=3):
        if endpoint == network.CONTROL_ENDPOINT:
            return _layer(endpoint=endpoint)
        return _layer(endpoint=endpoint, tcp="FALHA", tls="NÃO ALCANÇADO", attempts=3, code="TimeoutError", detail="timed out")

    assessment = network.assess_network(spec, result, layer_probe=fake_probe)
    assert assessment.classification == network.NETWORK_DESTINATION_UNREACHABLE
    assert assessment.control_status == "OK"
    assert assessment.attempt_count == 3


def test_tls_certificate_failure_is_classified_as_probable_interception_when_control_works(monkeypatch) -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    result = _diagnostic(spec, status=STATUS_TRANSIENT_FAILURE, category="NETWORK", http_status=None)
    monkeypatch.setattr(network, "_proxy_configured", lambda: False)

    def fake_probe(endpoint, attempts=3):
        if endpoint == network.CONTROL_ENDPOINT:
            return _layer(endpoint=endpoint)
        return _layer(
            endpoint=endpoint,
            tls="FALHA",
            attempts=3,
            code="SSLCertVerificationError",
            detail="certificate verify failed: unable to get local issuer certificate",
        )

    assessment = network.assess_network(spec, result, layer_probe=fake_probe)
    assert assessment.classification == network.TLS_INTERCEPTION_OR_POLICY
    assert assessment.control_status == "OK"


def test_proxy_environment_keeps_failed_direct_path_inconclusive(monkeypatch) -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    result = _diagnostic(spec, status=STATUS_TRANSIENT_FAILURE, category="NETWORK", http_status=None)
    monkeypatch.setattr(network, "_proxy_configured", lambda: True)

    def fake_probe(endpoint, attempts=3):
        if endpoint == network.CONTROL_ENDPOINT:
            return _layer(endpoint=endpoint)
        return _layer(endpoint=endpoint, tcp="FALHA", tls="NÃO ALCANÇADO", attempts=3)

    assessment = network.assess_network(spec, result, layer_probe=fake_probe)
    assert assessment.classification == network.NETWORK_INCONCLUSIVE_PROXY_OR_VPN
    assert assessment.proxy_configured is True


def test_copilot_checks_runtime_network_even_when_github_token_probe_is_http_200(monkeypatch) -> None:
    spec = get_integration_spec("ai:copilot")
    assert spec is not None
    result = _diagnostic(spec, status=STATUS_OPERATIONAL_LIMITED, category="AUTHENTICATED_GITHUB", http_status=200)
    monkeypatch.setattr(network, "_proxy_configured", lambda: False)
    seen: list[str] = []

    def fake_probe(endpoint, attempts=3):
        seen.append(endpoint)
        return _layer(endpoint=endpoint)

    assessment = network.assess_network(spec, result, layer_probe=fake_probe)
    assert seen == ["https://api.githubcopilot.com/_ping"]
    assert assessment.classification == network.NETWORK_PATH_OK
    assert assessment.inferred_from_http is False


def test_network_assessment_persistence_contains_only_sanitized_endpoint(tmp_path) -> None:
    assessment = network.NetworkAssessment(
        integration_id="ai:openai",
        checked_at=datetime.now(timezone.utc).isoformat(),
        endpoint="https://api.openai.com/v1/models",
        host="api.openai.com",
        port=443,
        dns_status="OK",
        tcp_status="OK",
        tls_status="OK",
        http_status=200,
        attempt_count=1,
        latencies_ms=(25,),
        classification=network.NETWORK_PATH_OK,
        error_code="",
        error_detail="",
    )
    network.save_network_assessment(tmp_path, assessment)
    loaded = network.load_network_assessments(tmp_path)["ai:openai"]
    assert loaded.endpoint == "https://api.openai.com/v1/models"
    assert loaded.host == "api.openai.com"
    assert loaded.classification == network.NETWORK_PATH_OK
