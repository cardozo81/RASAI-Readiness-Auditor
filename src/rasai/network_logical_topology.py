"""Offline projection of verified network endpoints and logical trace positions.

Never infers public egress, physical adjacency, hop addresses, DNS connections,
or geographic coordinates. The input must come from the validated AUD readers.
"""
from __future__ import annotations

from html import escape
from typing import Any

from rasai.network_connection_origin import _validated_ip, origin_evidence
from rasai.network_public_egress import verified_families
from rasai.network_observation import _utc_capture_time
from rasai.time_contract import format_presentation_timestamp


def _display_time(value: Any, timezone_name: str) -> str:
    instant = _utc_capture_time(value)
    if instant is None:
        return "N/D (instante não comprovado)"
    try:
        return format_presentation_timestamp(instant, timezone_name=timezone_name)
    except (ValueError, TypeError, OverflowError):
        return "N/D (instante não comprovado)"


def _metric(item: dict, name: str) -> Any:
    metrics = item.get("metrics")
    metric = metrics.get(name) if isinstance(metrics, dict) else None
    return metric.get("value") if isinstance(metric, dict) and metric.get("state") == "OBSERVED" else None


def _li(label: str) -> str:
    return "<li>" + escape(label) + "</li>"


def logical_network_sections(
    observations: list[dict], probes: list[dict], timezone_name: str,
) -> str:
    """Render logical origin/trace/destination and a role-aware IP inventory.

    A traceroute is independent of the established TCP socket; no drawn edge
    claims continuity between its hops or successful arrival at the destination.
    All strings are HTML-escaped; only valid observed IPs become inventory rows.
    """
    diagrams: list[str] = []
    inventory: list[tuple[str, str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_ip(environment: str, ip: str | None, role: str, source: str, instant: str) -> None:
        if ip is None:
            return
        key = (environment, ip, role)
        if key not in seen:
            seen.add(key)
            inventory.append((ip, role, environment, source, instant))

    for index, row in enumerate(origin_evidence(observations, []), 1):
        environment = "Navegador · captura " + str(index)
        stamp = _display_time(row["captured_at"], timezone_name)
        destination = row["remote_ip"]
        add_ip(environment, destination, "IP remoto da captura principal",
               "Resposta do navegador", stamp)
        steps = [
            _li("Ponto inicial: endereço local do navegador não identificado."),
            _li("Destino observado na navegação: " + (destination or "Não identificado") + "."),
        ]
        diagrams.append(
            "<h3>" + escape(environment) + "</h3><ol>" + "".join(steps) + "</ol>"
            "<p>Esta captura não comprova a interface local nem a rota do executor.</p>"
        )

    for index, probe in enumerate(probes[:32], 1):
        if not isinstance(probe, dict):
            continue
        origin = origin_evidence([], [probe])[0]
        environment = "Executor · sonda " + str(index)
        stamp = _display_time(origin["captured_at"], timezone_name)
        local_ip = origin["local_ip"] if origin["local_state"] == "OBSERVED" else None
        peer_ip = origin["remote_ip"]
        add_ip(environment, local_ip, "Endereço local do socket TCP",
               "Interface escolhida pelo sistema na conexão autorizada", stamp)
        add_ip(environment, peer_ip, "IP remoto conectado por TCP",
               "Socket TCP da sonda autorizada", stamp)

        dns = _metric(probe, "dns_resolution")
        if isinstance(dns, list):
            for candidate in dns[:32]:
                ip = _validated_ip(candidate, public_only=True)
                add_ip(environment, ip, "Candidato DNS (conexão não comprovada)",
                       "Resolução de nomes da sonda", stamp)

        steps = [_li(
            "Ponto inicial do processo: " + (local_ip or "Não identificado")
            + " (interface local; não é o IP público de saída)."
        )]
        externally_observed = verified_families(probe.get("public_egress"))
        for family, observation in sorted(externally_observed.items()):
            add_ip(environment, observation["ip"],
                   "IP público de saída IPv" + str(family) + " (consulta HTTPS externa)",
                   "Serviço externo de identificação; não é a conexão ao destino",
                   _display_time(observation.get("capture_utc"), timezone_name))
            steps.append(_li(
                "Saída pública IPv" + str(family) + " observada pelo serviço externo: "
                + observation["ip"] + " (não comprova a rota desta conexão TCP)."
            ))
        if isinstance(probe.get("public_egress"), dict) and not externally_observed:
            steps.append(_li("Saída pública externa: não identificada nesta medição."))
        trace = _metric(probe, "traceroute")
        hops = trace.get("hops") if isinstance(trace, dict) else None
        if isinstance(hops, list):
            for hop in hops[:16]:
                if not isinstance(hop, dict) or type(hop.get("hop")) is not int:
                    continue
                number = hop["hop"]
                if not 1 <= number <= 32:
                    continue
                state = hop.get("state")
                if state == "PUBLIC_HOP":
                    ip = _validated_ip(hop.get("public_ip"), public_only=True)
                    add_ip(environment, ip, "Salto público " + str(number),
                           "Traceroute autorizado (sondagem independente)", stamp)
                    detail = ip or "endereço não verificável"
                elif state == "PRIVATE_HOP_REDACTED":
                    detail = "resposta de endereço privado ou reservado (ocultado)"
                elif state == "NO_REPLY":
                    detail = "sem resposta"
                else:
                    detail = "estado não comprovado"
                steps.append(_li("Salto " + str(number) + ": " + detail + "."))
        else:
            steps.append(_li("Saltos intermediários: não observados."))

        if peer_ip:
            detail = "Destino da conexão TCP: " + peer_ip + "."
        else:
            detail = "Destino da conexão TCP: não identificado."
        if isinstance(trace, dict) and trace.get("target_reached") is not True:
            detail += " Chegada pelo traceroute não confirmada."
        steps.append(_li(detail))
        diagrams.append(
            "<h3>" + escape(environment) + "</h3><ol>" + "".join(steps) + "</ol>"
            "<p>Os saltos são respostas numeradas de uma medição independente. "
            "Não representam enlaces físicos verificados nem sequência TCP comprovada.</p>"
        )

    start = (
        "<section class='panel' id='network-logical-topology'>"
        "<h2>Topologia lógica observada</h2>"
        "<p>A origem local do executor só é indicada quando o socket da sonda autorizada "
        "a registrou. O navegador é outra sessão. A ordem dos saltos é apenas a ordem "
        "observada pelo traceroute, não um caminho físico confirmado. "
        "IP público de saída só é apresentado quando observado em consulta HTTPS "
        "externa e autorizada, independente da conexão ao destino.</p>"
    )
    if not diagrams:
        start += "<p>Não há medições de rede verificáveis. Isso não comprova falha de conexão.</p>"
    topology = start + "".join(diagrams) + "</section>"

    inventory_html = (
        "<section class='panel' id='network-ip-inventory'>"
        "<h2>Inventário de endereços IP observados</h2>"
        "<p>Um IP pode aparecer mais de uma vez quando tem papéis distintos. "
        "Resolução DNS indica candidatos, não conexões realizadas. "
        "Endereços ocultados ou sem resposta não são inventados. "
        "Ausência de coordenadas não elimina um IP do inventário.</p>"
    )
    if inventory:
        inventory_html += (
            "<div class='table-wrap'><table><thead><tr><th>Endereço IP</th>"
            "<th>Papel comprovado</th><th>Ambiente</th><th>Proveniência</th>"
            "<th>Instante</th></tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join("<td>" + escape(str(value)) + "</td>" for value in row) + "</tr>"
                for row in inventory
            ) + "</tbody></table></div>"
        )
    else:
        inventory_html += "<p>Nenhum endereço IP verificável identificado nestes registros.</p>"
    return topology + inventory_html + "</section>"
