"""Network Intelligence is observational, optional and isolated from audit engines."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rasai import network_intelligence as ni
from rasai import network_intelligence_ai as ai
from rasai import network_intelligence_reporting as report


def _data(*, two: bool = False):
    snapshot = {
        "capture_utc": "2026-10-25T10:00:00Z",
        "capture_time_state": "OBSERVED",
        "observation_id": "OBS-1",
        "device": "MOBILE",
        "target_host": "example.org",
        "sha256": "a" * 64,
        "metrics": {
            "connected_public_ip": {"state": "OBSERVED", "value": "1.1.1.1"},
            "tls_protocol": {"state": "OBSERVED", "value": "TLSv1.3"},
            "http_protocol": {"state": "OBSERVED", "value": "h2"},
            "tcp_handshake_ms": {"state": "NOT_OBSERVED", "value": None},
        },
    }
    def probe(when, tcp):
        return {
            "audit_id": "AUD-NET-1",
            "hostname": "example.org", "port": 443,
            "capture_utc": when, "sha256": "b" * 64,
            "metrics": {
                "dns_elapsed_ms": {"state": "OBSERVED", "value": 91.62},
                "tcp_handshake_ms": {"state": "OBSERVED", "value": tcp},
                "tls_handshake_ms": {"state": "OBSERVED", "value": 32.11},
                "connected_public_ip": {"state": "OBSERVED", "value": "1.0.0.1"},
            },
        }
    result = [probe("2026-10-26T10:00:00Z", 24.57)]
    if two:
        result.append(probe("2026-10-27T10:00:00Z", 39.57))
    return [snapshot], result


def _mock_sources(monkeypatch, *, two=False):
    obs, probes = _data(two=two)
    monkeypatch.setattr(ni, "read_network_observations", lambda *_: obs)
    monkeypatch.setattr(ni, "read_authorized_probes", lambda *_: probes)


def test_measured_fact_does_not_become_network_cause_or_percent(tmp_path, monkeypatch):
    _mock_sources(monkeypatch)
    observed = ni.build_network_assessment(tmp_path, "AUD-NET-1")
    assert observed["coverage"]["tcp_samples"] == 1
    assert observed["confidence_scope"] == "LIMITED"
    tcp = next(item for item in observed["findings"] if item["id"] == "NET-TCP_HANDSHAKE_MS")
    assert "24,57 ms" in tcp["conclusion"]
    assert tcp["evidence_refs"] == ["NET-PROBE-001"]
    assert "não" in tcp["limitation"].lower()
    assert "NET-PEERS" in {x["id"] for x in observed["findings"]}
    assert "NET-TEMPORAL" not in {x["id"] for x in observed["findings"]}
    assert all("%" not in item["conclusion"] for item in observed["findings"])


def test_temporal_support_only_for_comparable_dated_samples(tmp_path, monkeypatch):
    _mock_sources(monkeypatch, two=True)
    result = ni.build_network_assessment(tmp_path, "AUD-NET-1")
    assert result["confidence_scope"] == "MODERATE"
    temporal = next(f for f in result["findings"] if f["id"] == "NET-TEMPORAL")
    assert temporal["confidence"] == "MEDIUM"
    assert set(temporal["evidence_refs"]) == {"NET-PROBE-001", "NET-PROBE-002"}


def test_missing_or_bad_source_cannot_be_turned_into_success(tmp_path, monkeypatch):
    monkeypatch.setattr(ni, "read_network_observations", lambda *_: [])
    monkeypatch.setattr(ni, "read_authorized_probes", lambda *_: [])
    result = ni.build_network_assessment(tmp_path, "AUD-NET-1")
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["findings"][0]["confidence"] == "LOW"
    assert result["findings"][0]["evidence_refs"] == []


def test_ai_output_rejects_hallucinated_refs_and_confidence(tmp_path, monkeypatch):
    _mock_sources(monkeypatch, two=True)
    observed = ni.build_network_assessment(tmp_path, "AUD-NET-1")
    base = {
        "summary": "Os tempos disponíveis representam amostras pontuais.",
        "insights": [{
            "finding_id": "NET-TEMPORAL", "evidence_refs": ["NET-PROBE-001"],
            "interpretation": "As amostras podem diferir.",
            "confidence": "MEDIUM", "limitation": "Não comprova causa.",
            "recommendation": "Comparar sob condições equivalentes.",
            "validation": "Observar sessões documentadas.",
        }],
    }
    assert ai.validate_ai_interpretation(base, observed)["insights"][0]["confidence"] == "MEDIUM"
    invented = json.loads(json.dumps(base))
    invented["insights"][0]["evidence_refs"] = ["NET-PROBE-999"]
    with pytest.raises(ValueError):
        ai.validate_ai_interpretation(invented, observed)
    inflated = json.loads(json.dumps(base))
    inflated["insights"][0]["confidence"] = "HIGH"
    with pytest.raises(ValueError):
        ai.validate_ai_interpretation(inflated, observed)


def test_ai_requires_explicit_authorization_without_transport(tmp_path, monkeypatch):
    _mock_sources(monkeypatch)
    with pytest.raises(ValueError, match="autorização explícita"):
        ai.run_network_ai(tmp_path, "AUD-NET-1", authorized=False, provider="openai")


def test_html_displays_provenance_limits_and_ai_absence(tmp_path, monkeypatch):
    _mock_sources(monkeypatch)
    html = report.network_intelligence_section(tmp_path, "AUD-NET-1")
    assert "Diagnóstico de Rede e Conectividade" in html
    assert "24,57 ms" in html
    assert "Confiabilidade da conclusão geral" in html
    assert "NET-PROBE-001" in html
    assert "não executada" in html
    assert "SEO e GEO" in html
    assert "<script" not in html


def test_tampered_or_stale_ai_packet_is_never_displayed(tmp_path, monkeypatch):
    _mock_sources(monkeypatch)
    assessment = ni.build_network_assessment(tmp_path, "AUD-NET-1")
    valid_finding = next(f for f in assessment["findings"] if f["evidence_refs"])
    payload = {
        "contract": ai.AI_CONTRACT,
        "audit_id": "AUD-NET-1",
        "evidence_sha256": assessment["evidence_sha256"],
        "analysis": {
            "summary": "Leitura consultiva das evidências.",
            "insights": [{
                "finding_id": valid_finding["id"],
                "evidence_refs": [valid_finding["evidence_refs"][0]],
                "confidence": valid_finding["confidence"],
                "interpretation": "Medição pontual.",
                "limitation": "Não comprova causalidade.",
                "recommendation": "Conferir medições.",
                "validation": "Comparar resultados.",
            }],
        },
    }
    payload["sha256"] = __import__("hashlib").sha256(ni._canonical(payload)).hexdigest()
    payload["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
    file = ai._packet_path(tmp_path, assessment)
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps(payload), encoding="utf-8")
    assert ai.read_network_ai(tmp_path, assessment) is not None
    assert "Interpretação complementar por IA" in report.network_intelligence_section(tmp_path, "AUD-NET-1")
    payload["analysis"]["summary"] = "Resultado adulterado"
    file.write_text(json.dumps(payload), encoding="utf-8")
    assert ai.read_network_ai(tmp_path, assessment) is None
    assert "Resultado adulterado" not in report.network_intelligence_section(tmp_path, "AUD-NET-1")
    stale = dict(assessment, evidence_sha256="f" * 64)
    assert ai.read_network_ai(tmp_path, stale) is None


def test_report_never_calls_provider_even_if_sidecar_absent(tmp_path, monkeypatch):
    _mock_sources(monkeypatch)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Provider cannot be called when rendering")
    monkeypatch.setattr(ai, "run_network_ai", forbidden)
    assert "Diagnóstico de Rede" in report.network_intelligence_section(tmp_path, "AUD-NET-1")
