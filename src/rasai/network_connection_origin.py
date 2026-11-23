"""Read-only origin evidence for #751. No route, GeoIP or egress inference.

A passive browser response can establish a remote peer, never the browser's
local endpoint. An explicitly authorized process probe may record the local
socket endpoint. Neither measurement establishes the public egress IP.
"""
from __future__ import annotations

import ipaddress
from typing import Any, Mapping

from rasai.network_observation import _utc_capture_time
from rasai.network_public_egress_view import egress_label

_SOCKET_SOURCE = "SOCKET_GETSOCKNAME_AFTER_CONNECT"
_PROBE_METHOD = "EXPLICIT_DNS_TCP_TLS_PROBE"


def _validated_ip(value: Any, *, public_only: bool = False) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 64:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if address.is_unspecified or (public_only and not address.is_global):
        return None
    # A scope identifier is an interface detail, not part of an IP address.
    return str(address).split("%", 1)[0]


def _peer(item: Mapping[str, Any]) -> str | None:
    metrics = item.get("metrics")
    if not isinstance(metrics, dict):
        return None
    metric = metrics.get("connected_public_ip")
    if not isinstance(metric, dict) or metric.get("state") != "OBSERVED":
        return None
    return _validated_ip(metric.get("value"), public_only=True)


def _local_endpoint(item: Mapping[str, Any]) -> tuple[str | None, str]:
    """Only exact socket provenance can establish a local endpoint."""
    metrics = item.get("metrics")
    metric = metrics.get("local_socket_ip") if isinstance(metrics, dict) else None
    if not isinstance(metric, dict) or metric.get("state") == "NOT_OBSERVED":
        return None, "NOT_OBSERVED"
    if metric.get("state") != "OBSERVED":
        return None, "INCONCLUSIVE"
    if not (
        item.get("measurement_origin") == "LOCAL_OPERATOR_PROCESS"
        and item.get("method") == _PROBE_METHOD
        and item.get("source") == "LOCAL_SOCKET_STACK"
        and metric.get("source") == _SOCKET_SOURCE
    ):
        return None, "INCONCLUSIVE"
    ip = _validated_ip(metric.get("value"))
    return (ip, "OBSERVED") if ip else (None, "INCONCLUSIVE")


def origin_evidence(
    observations: list[dict[str, Any]], probes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Describe independent connections without treating a destination as origin.

    Input lists must come from existing validated sidecar readers (or the
    canonical read-only legacy projection), not arbitrary public JSON.
    """
    output: list[dict[str, Any]] = []
    for index, item in enumerate(observations[:100], 1):
        if not isinstance(item, dict):
            continue
        capture = (
            _utc_capture_time(item.get("capture_utc"))
            if item.get("capture_time_state") == "OBSERVED" else None
        )
        output.append({
            "kind": "Navegador da auditoria",
            "context": str(item.get("device") or "Dispositivo não informado")[:40],
            "destination": item.get("target_host"),
            "remote_ip": _peer(item),
            "local_ip": None,
            "local_state": "NOT_OBSERVED",
            "egress_ip": None,
            "egress_state": "NOT_OBSERVED",
            "captured_at": capture,
            "method": "Captura passiva da navegação principal",
            "provenance": "Registro da captura do navegador",
            "ref": "#network-passive-" + str(index),
        })
    for index, item in enumerate(probes[:32], 1):
        if not isinstance(item, dict):
            continue
        local_ip, state = _local_endpoint(item)
        public_ips = egress_label(item.get("public_egress"))
        independent = item.get("method") == "INDEPENDENT_EXTERNAL_HTTPS_IP_ECHO"
        output.append({
            "kind": "Processo executor",
            "context": ("Verificação externa do IP público" if independent
                        else "Sondagem independente autorizada"),
            "destination": item.get("hostname"),
            "remote_ip": _peer(item),
            "local_ip": local_ip,
            "local_state": state,
            "egress_ip": public_ips,
            "egress_state": "OBSERVED" if public_ips else "NOT_OBSERVED",
            "captured_at": _utc_capture_time(item.get("capture_utc")),
            "method": ("Consulta HTTPS a serviço de identificação do IP público"
                       if independent else "Conexão TCP/TLS de sondagem autorizada"),
            "provenance": (
                "Resposta de serviço externo à solicitação do processo executor"
                if independent else "Endereço local da conexão TCP, registrado pelo processo"
                if local_ip else "Nenhum endereço local verificável na sonda"
            ),
            "ref": "#network-probe-" + str(index),
        })
    return output
