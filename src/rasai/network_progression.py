"""#659 G3: read-only route detail and temporal comparison from immutable data."""
from collections import defaultdict
from html import escape
from ipaddress import ip_address
from math import isfinite


_TRACE_METHODS = {
    "WINDOWS_TRACERT": "tracert (Windows)",
    "LINUX_TRACEROUTE_TCP": "traceroute TCP (Linux)",
}
_TRACE_PROTOCOLS = {"ICMP": "ICMP", "TCP": "TCP"}
_TRACE_COLLECTION = {
    "COMPLETED_PROCESS": "processo concluído",
    "TIME_BUDGET_EXCEEDED": "limite de tempo excedido",
    "COMMAND_FAILED": "processo encerrado com erro",
}
_TRACE_ORIGINS = {"LOCAL_OPERATOR_PROCESS": "processo local autorizado"}


def _trace_provenance(value):
    """Project only allowlisted method/protocol/collector metadata."""
    def known(mapping, key):
        item = value.get(key)
        return mapping.get(item, "não informado") if isinstance(item, str) else "não informado"

    limit = value.get("max_hops")
    limit_text = str(limit) if type(limit) is int and 1 <= limit <= 16 else "não informado"
    return (
        "<p>Proveniência do rastreamento: método "
        + escape(known(_TRACE_METHODS, "method"))
        + "; protocolo " + escape(known(_TRACE_PROTOCOLS, "probe_protocol"))
        + "; executor " + escape(known(_TRACE_ORIGINS, "measurement_origin"))
        + "; coleta " + escape(known(_TRACE_COLLECTION, "collection_status"))
        + "; limite de saltos " + limit_text + ". "
        "A conclusão do processo não comprova que o destino respondeu.</p>"
    )


def route_panels(probes):
    output = []
    for row in probes[:32]:
        trace = (row.get("metrics") or {}).get("traceroute") or {}
        data = trace.get("value") if trace.get("state") == "OBSERVED" else None
        if not isinstance(data, dict) or not isinstance(data.get("hops"), list):
            continue
        lines = []
        last_responding = data.get("last_responding_hop")
        if type(last_responding) is not int:
            last_responding = max((h.get("hop") for h in data["hops"] if isinstance(h, dict)
                                   and h.get("state") in ("PUBLIC_HOP", "PRIVATE_HOP_REDACTED")
                                   and type(h.get("hop")) is int), default=None)
        for item in data["hops"][:16]:
            if not isinstance(item, dict):
                continue
            n, state = item.get("hop"), item.get("state")
            if type(n) is not int or not 1 <= n <= 16 or state not in (
                    "PUBLIC_HOP", "PRIVATE_HOP_REDACTED", "NO_REPLY"):
                continue
            address = item.get("public_ip")
            try:
                parsed = ip_address(address)
                address = str(parsed) if state == "PUBLIC_HOP" and parsed.is_global else None
            except (TypeError, ValueError):
                address = None
            rtt = item.get("rtt_ms")
            timing = (f"{rtt:.2f} ms" if type(rtt) in (float, int) and
                      isfinite(rtt) and 0 <= rtt <= 60000 else "Não observado")
            samples = item.get("rtt_samples_ms")
            if isinstance(samples, list):
                valid_samples = [v for v in samples[:3] if type(v) in (float, int)
                                 and isfinite(v) and 0 <= v <= 60000]
                if valid_samples:
                    timing = ", ".join(f"{v:.2f} ms" for v in valid_samples)
            status = {"PUBLIC_HOP": "Resposta pública", "PRIVATE_HOP_REDACTED": "Endereço reservado",
                      "NO_REPLY": "Sem resposta"}[state]
            marker = " (último respondente)" if n == last_responding else ""
            shown_address = address or ("Oculto" if state == "PRIVATE_HOP_REDACTED" else "Sem IP")
            lines.append(f"<tr><th scope='row'>{n}</th><td>{status}{marker}</td><td>{escape(shown_address)}</td>"
                         f"<td>{timing}</td></tr>")
        if not lines:
            continue
        output.append("<section class='panel'><h2>Etapas conhecidas do caminho</h2>"
                      "<p>Destino: " + escape(str(row.get("hostname") or "-")) +
                      ". Caminho lógico, possivelmente parcial. Endereços privados não "
                      "são divulgados. RTT por salto não mede a latência de cada enlace.</p>"
                      + _trace_provenance(data)
                      + "<div class='table-wrap'><table><thead><tr><th>Salto</th>"
                      "<th>Situação</th><th>Endereço público</th><th>Tempo</th>"
                      "</tr></thead><tbody>" + "".join(lines) + "</tbody></table></div>"
                      "<p>" + ("Destino alcançado." if data.get("target_reached") else
                               "Caminho completo não confirmado.") +
                      (" A coleta excedeu o limite de tempo; os saltos anteriores foram preservados."
                       if trace.get("error") == "TRACE_TIME_BUDGET_EXCEEDED" else
                       " O processo de sondagem terminou com erro; os saltos observados foram preservados."
                       if trace.get("error") == "TRACE_COMMAND_FAILED" else "") +
                      "</p></section>")
    return "".join(output)


def temporal_panel(probes):
    groups = defaultdict(list)
    for row in probes[:32]:
        host, port, stamp = row.get("hostname"), row.get("port"), row.get("capture_utc")
        if isinstance(host, str) and type(port) is int and isinstance(stamp, str) and stamp.endswith("Z"):
            groups[(host, port)].append(row)
    rows = []
    for (host, port), items in sorted(groups.items()):
        items.sort(key=lambda x: x["capture_utc"])
        if len(items) < 2 or items[0]["capture_utc"] == items[-1]["capture_utc"]:
            continue
        first, last = items[0], items[-1]
        for metric, label in (("tcp_handshake_ms", "Conexão TCP"),
                              ("tls_handshake_ms", "Negociação TLS")):
            prior = (first.get("metrics") or {}).get(metric) or {}
            recent = (last.get("metrics") or {}).get(metric) or {}
            before = prior.get("value") if prior.get("state") == "OBSERVED" else None
            after = recent.get("value") if recent.get("state") == "OBSERVED" else None
            if not all(type(v) in (int, float) and isfinite(v) and 0 <= v < 60000
                       for v in (before, after)):
                continue
            rows.append("<tr><td>" + escape(host) + ":" + str(port) + "</td>"
                        "<td>" + label + "</td><td>" + escape(first["capture_utc"]) +
                        "</td><td>" + f"{before:.2f} ms" + "</td><td>" +
                        escape(last["capture_utc"]) + "</td><td>" + f"{after:.2f} ms" +
                        "</td><td>" + f"{after-before:+.2f} ms" + "</td></tr>")
    if not rows:
        return ""
    return ("<section class='panel'><h2>Comparação temporal das medições</h2>"
            "<p>Comparação descritiva entre sessões autorizadas do mesmo destino e porta. "
            "Variações não comprovam causa ou tendência. O acesso do executor, VPN e "
            "proxy podem diferir entre coletas.</p><div class='table-wrap'><table>"
            "<thead><tr><th>Destino</th><th>Indicador</th><th>Primeira data</th>"
            "<th>Primeiro valor</th><th>Última data</th><th>Último valor</th>"
            "<th>Diferença</th></tr></thead><tbody>" + "".join(rows) +
            "</tbody></table></div></section>")
