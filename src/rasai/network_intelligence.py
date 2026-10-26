"""Consultative Network Intelligence from verified, already collected G1/G2/G3 evidence.

No provider calls, probes, scoring, persistent audit writes or invented measurements.
"""
from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any

from rasai.network_observation import snapshots_from_audit
from rasai.network_observation_store import read_network_observations, sidecar_path
from rasai.network_active_probe import read_authorized_probes

CONTRACT = "RASAI-NETWORK-INTELLIGENCE-001"
_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_METRICS = ("dns_elapsed_ms", "tcp_handshake_ms", "tls_handshake_ms")
_LABELS = {
    "dns_elapsed_ms": "Consulta DNS",
    "tcp_handshake_ms": "Conexão TCP",
    "tls_handshake_ms": "Negociação TLS",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _measurement(value: Any) -> float | None:
    if type(value) not in (int, float) or not isfinite(value) or not 0 <= value < 60000:
        return None
    return float(value)


def _observed(row: dict[str, Any], key: str) -> Any:
    metrics = row.get("metrics")
    if not isinstance(metrics, dict):
        return None
    metric = metrics.get(key)
    return metric.get("value") if isinstance(metric, dict) and metric.get("state") == "OBSERVED" else None


def _fact(*, key: str, title: str, conclusion: str, refs: list[str],
          limit: str, recommendation: str, confidence: str = "HIGH") -> dict[str, Any]:
    return {
        "id": key,
        "title": title,
        "conclusion": conclusion,
        "confidence": confidence,
        "evidence_refs": list(dict.fromkeys(refs)),
        "limitation": limit,
        "recommendation": recommendation,
        "validation": "Comparar com observações autorizadas adicionais, no mesmo escopo e com data conhecida.",
    }


def build_network_assessment(workspace: str | Path, audit_id: str) -> dict[str, Any]:
    """Project observations without writing, probing, interpreting absent metrics as failure."""
    if not _ID.fullmatch(audit_id):
        raise ValueError("Identificador de auditoria inválido")
    root = Path(workspace)
    if root.is_symlink() or (root / "audit.db").is_symlink():
        raise ValueError("Workspace de auditoria inválido")
    observations = read_network_observations(root, audit_id)
    packet = sidecar_path(root)
    # A present but invalid sidecar is NOT permission to trust an unverified fallback.
    if not observations and not (packet.exists() or packet.is_symlink()):
        db = root / "audit.db"
        if db.is_file():
            observations = snapshots_from_audit(db, audit_id)
    probes = read_authorized_probes(root, audit_id)
    evidence: list[dict[str, Any]] = []
    observations_by_id: list[tuple[str, dict[str, Any]]] = []
    probes_by_id: list[tuple[str, dict[str, Any]]] = []
    for i, row in enumerate(observations[:100], 1):
        if not isinstance(row, dict):
            continue
        ref = f"NET-AUD-{i:03d}"
        evidence.append({
            "id": ref, "origin": "AUD_PERSISTED_CAPTURE",
            "time": row.get("capture_utc") if row.get("capture_time_state") == "OBSERVED" else None,
            "host": row.get("target_host"), "device": row.get("device"),
            "digest": row.get("sha256"), "observation_id": row.get("observation_id"),
        })
        observations_by_id.append((ref, row))
    for i, row in enumerate(probes[:32], 1):
        if not isinstance(row, dict):
            continue
        ref = f"NET-PROBE-{i:03d}"
        evidence.append({
            "id": ref, "origin": "AUTHORIZED_COMPLEMENTARY_PROBE",
            "time": row.get("capture_utc"), "host": row.get("hostname"),
            "port": row.get("port"), "digest": row.get("sha256"),
        })
        probes_by_id.append((ref, row))

    findings: list[dict[str, Any]] = []
    measured: dict[str, list[tuple[str, float]]] = {key: [] for key in _METRICS}
    for ref, row in probes_by_id:
        for key in _METRICS:
            value = _measurement(_observed(row, key))
            if value is not None:
                measured[key].append((ref, value))
    for key, title in _LABELS.items():
        rows = measured[key]
        if not rows:
            continue
        ref, value = rows[-1]
        decimal = f"{value:g}".replace(".", ",")
        findings.append(_fact(
            key="NET-" + key.upper(), title=title + " observada",
            conclusion=f"Uma medição autorizada registrou {decimal} ms na etapa {title.lower()} do executor.",
            refs=[ref],
            limit="Tempo da sessão do executor; não equivale ao desempenho experimentado por visitantes e não identifica causa.",
            recommendation="Se houver suspeita de lentidão, repetir medições autorizadas de forma controlada antes de priorizar correções.",
        ))

    transport = [
        (ref, row) for ref, row in observations_by_id
        if _observed(row, "connected_public_ip") or _observed(row, "tls_protocol")
        or _observed(row, "http_protocol")
    ]
    if transport:
        ref, row = transport[-1]
        parts = []
        for name, label in (("http_protocol", "HTTP"), ("tls_protocol", "TLS"),
                            ("connected_public_ip", "par público da conexão")):
            value = _observed(row, name)
            if isinstance(value, (str, int)) and value:
                parts.append(f"{label}: {value}")
        findings.append(_fact(
            key="NET-TRANSPORT", title="Protocolo e conexão da captura original",
            conclusion="A auditoria registrou " + "; ".join(parts) + ".",
            refs=[ref], limit="A captura não demonstra topologia de origem, trajetória física ou conformidade total da configuração TLS.",
            recommendation="Correlacionar com o contexto de captura caso haja uma investigação de transporte.",
        ))

    peers: dict[str, list[str]] = {}
    for ref, row in observations_by_id + probes_by_id:
        ip = _observed(row, "connected_public_ip")
        if isinstance(ip, str) and ip:
            peers.setdefault(ip, []).append(ref)
    if len(peers) > 1:
        findings.append(_fact(
            key="NET-PEERS", title="Endereços públicos diferentes",
            conclusion="Foram observados endereços de conexão públicos diferentes em registros distintos.",
            refs=[refs[0] for refs in peers.values()],
            confidence="HIGH",
            limit="A diferença não comprova CDN, balanceamento, migração, origem física nem regressão de desempenho.",
            recommendation="Investigar distribuição de tráfego somente se existir objetivo técnico e evidência adicional.",
        ))

    comparisons: list[tuple[str, list[str]]] = []
    groups: dict[tuple[str, int], list[tuple[str, dict[str, Any]]]] = {}
    for ref, row in probes_by_id:
        host, port, stamp = row.get("hostname"), row.get("port"), row.get("capture_utc")
        if isinstance(host, str) and type(port) is int and isinstance(stamp, str) and stamp.endswith("Z"):
            groups.setdefault((host, port), []).append((ref, row))
    for group in groups.values():
        group.sort(key=lambda pair: str(pair[1]["capture_utc"]))
        first, last = group[0], group[-1]
        if first[1]["capture_utc"] == last[1]["capture_utc"]:
            continue
        for key in _METRICS:
            first_ms = _measurement(_observed(first[1], key))
            last_ms = _measurement(_observed(last[1], key))
            if first_ms is not None and last_ms is not None:
                comparisons.append((key, [first[0], last[0]]))
    if comparisons:
        refs = list(dict.fromkeys(ref for _, pair in comparisons for ref in pair))
        findings.append(_fact(
            key="NET-TEMPORAL", title="Amostras temporalmente comparáveis",
            conclusion="Há ao menos duas medições datadas do mesmo destino e porta, com tempos comparáveis.",
            refs=refs, confidence="MEDIUM",
            limit="As diferenças entre sessões não provam tendência, gargalo nem causa; condições de saída podem variar.",
            recommendation="Verificar amostras adicionais com condições de medição documentadas antes de atribuir tendência.",
        ))

    geo_refs = [ref for ref, row in probes_by_id
                if isinstance(_observed(row, "geoip"), dict)]
    if geo_refs:
        findings.append(_fact(
            key="NET-GEOIP", title="Referência geográfica aproximada",
            conclusion="Há uma atribuição geográfica aproximada registrada em base local de IP.",
            refs=geo_refs, confidence="MEDIUM",
            limit="A atribuição não comprova a localização física do servidor nem o caminho de rede.",
            recommendation="Considerar o raio de precisão e a origem da base antes de utilizar a estimativa.",
        ))

    if not findings:
        findings.append(_fact(
            key="NET-LIMITATION", title="Evidência insuficiente para conclusão técnica",
            conclusion="Não há medições verificadas suficientes para interpretar o comportamento da conexão.",
            refs=[], confidence="LOW",
            limit="Ausência de medição não é evidência de falha de rede.",
            recommendation="Avaliar necessidade de coleta complementar somente com autorização explícita.",
        ))

    independent_sessions = len({
        (row.get("hostname"), row.get("port"), row.get("capture_utc"))
        for _, row in probes_by_id if row.get("capture_utc")
    })
    reliability = "MODERATE" if comparisons and independent_sessions >= 2 else "LIMITED"
    assessment: dict[str, Any] = {
        "contract": CONTRACT, "audit_id": audit_id,
        "analysis_method": "DETERMINISTIC_PERSISTED_EVIDENCE",
        "status": "OBSERVED_LIMITED" if (transport or any(measured.values())) else "INSUFFICIENT_EVIDENCE",
        "confidence_scope": reliability,
        "confidence_explanation": (
            "Há sessões independentes datadas para comparação pontual; ainda não há base para inferir causalidade ou desempenho global."
            if reliability == "MODERATE"
            else "Amostragem insuficiente para avaliar confiabilidade global, tendências ou causas."
        ),
        "evidence": evidence, "findings": findings,
        "coverage": {
            "audit_captures": len(observations_by_id),
            "authorized_probes": len(probes_by_id),
            "dns_samples": len(measured["dns_elapsed_ms"]),
            "tcp_samples": len(measured["tcp_handshake_ms"]),
            "tls_samples": len(measured["tls_handshake_ms"]),
        },
        "scope_limitations": [
            "Não representa velocidade percebida por usuários nem qualidade global do site.",
            "Não comprova causalidade, CDN, topologia interna, posição física ou efeito em SEO/GEO.",
            "Hipóteses e recomendações exigem validação humana e evidência adicional.",
        ],
    }
    assessment["evidence_sha256"] = sha256(_canonical(assessment)).hexdigest()
    return assessment
