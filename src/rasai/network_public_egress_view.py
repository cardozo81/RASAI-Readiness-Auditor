"""Offline, humanized presentation of optional public-IP echo measurements."""
from __future__ import annotations

from html import escape
from typing import Any

from rasai.network_public_egress import error_summary, verified_families
from rasai.network_observation import _utc_capture_time
from rasai.time_contract import format_presentation_timestamp

_PROVIDER_LABELS = {"IPIFY": "ipify", "IDENTME": "ident.me"}


def _when(raw: Any, timezone_name: str) -> str:
    instant = _utc_capture_time(raw)
    if instant is None:
        return "Instante não comprovado"
    try:
        return format_presentation_timestamp(instant, timezone_name=timezone_name)
    except (TypeError, ValueError, OverflowError):
        return "Instante não comprovado"


def egress_label(packet: Any) -> str | None:
    observations = verified_families(packet)
    if not observations:
        return None
    return "; ".join("IPv" + str(family) + ": " + row["ip"]
                     for family, row in sorted(observations.items()))


def public_egress_panel(probes: list[dict], timezone_name: str) -> str:
    """Render persisted, verified packets only; no external I/O or DNS."""
    rows = []
    for index, probe in enumerate(probes[:32], 1):
        if not isinstance(probe, dict):
            continue
        packet = probe.get("public_egress")
        if not isinstance(packet, dict) or packet.get("state") == "NOT_REQUESTED":
            continue
        values = verified_families(packet)
        for family in (4, 6):
            observation = values.get(family)
            if observation is not None:
                provider = _PROVIDER_LABELS[observation["provider"]]
                detail = ("Endereço público observado pelo serviço externo "
                          "na conexão HTTPS do processo executor.")
                when = _when(observation.get("capture_utc"), timezone_name)
                address = observation["ip"]
            else:
                raw = packet.get("families")
                row = raw.get("ipv" + str(family)) if isinstance(raw, dict) else None
                if not isinstance(row, dict):
                    continue
                provider = "Nenhum serviço concluiu a consulta"
                detail = error_summary({
                    "state": "UNAVAILABLE",
                    "families": {"ipv" + str(family): row},
                }) or "Endereço não verificado."
                when = "N/D"
                address = "Não identificado"
            values_html = (str(index), "IPv" + str(family), address,
                           provider, when, detail)
            rows.append("<tr>" + "".join("<td>" + escape(str(v)) +
                        "</td>" for v in values_html) + "</tr>")
    if not rows:
        return ""
    warnings = []
    for index, probe in enumerate(probes[:32], 1):
        packet = probe.get("public_egress") if isinstance(probe, dict) else None
        message = error_summary(packet)
        if message:
            warnings.append("<p role='status'><strong>Descoberta de IPs parcial ou indisponível "
                            "(sonda " + str(index) + ").</strong> " +
                            escape(message) +
                            " As demais observações de rede foram preservadas.</p>")
    return (
        "<section class='panel' id='network-public-egress'>"
        "<h2>IP público de saída — verificação externa autorizada</h2>"
        "<p>A medição identifica somente o IP visto pelo serviço externo no "
        "processo executor, em conexão HTTPS direta. Não comprova o endereço "
        "do navegador, a conexão TCP com o destino auditado nem a rota física. "
        "Cada família IP é verificada de forma independente. Geolocalização "
        "por IP, quando disponível, é aproximada.</p>"
        "<div class='table-wrap'><table><thead><tr>"
        "<th>Sonda</th><th>Família</th><th>IP público</th>"
        "<th>Serviço</th><th>Instante</th><th>Interpretação</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        + "".join(warnings) + "</section>"
    )
