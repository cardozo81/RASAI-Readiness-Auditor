"""#659 G3: read-only route detail and temporal comparison from immutable data."""
from collections import defaultdict
from html import escape
from ipaddress import ip_address
from math import isfinite


def route_panels(probes):
    output = []
    for row in probes[:32]:
        trace = (row.get("metrics") or {}).get("traceroute") or {}
        data = trace.get("value") if trace.get("state") == "OBSERVED" else None
        if not isinstance(data, dict) or not isinstance(data.get("hops"), list):
            continue
        lines = []
        for item in data["hops"][:8]:
            if not isinstance(item, dict):
                continue
            n, state = item.get("hop"), item.get("state")
            if type(n) is not int or not 1 <= n <= 8 or state not in (
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
            status = {"PUBLIC_HOP": "Resposta pública", "PRIVATE_HOP_REDACTED": "Endereço reservado",
                      "NO_REPLY": "Sem resposta"}[state]
            lines.append(f"<tr><th>{n}</th><td>{status}</td><td>{escape(address or 'Oculto')}</td>"
                         f"<td>{timing}</td></tr>")
        if not lines:
            continue
        output.append("<section class='panel'><h2>Etapas conhecidas do caminho</h2>"
                      "<p>Destino: " + escape(str(row.get("hostname") or "-")) +
                      ". Caminho lógico, possivelmente parcial. Endereços privados não "
                      "são divulgados. RTT por salto não mede a latência de cada enlace.</p>"
                      "<div class='table-wrap'><table><thead><tr><th>Salto</th>"
                      "<th>Situação</th><th>Endereço público</th><th>Tempo</th>"
                      "</tr></thead><tbody>" + "".join(lines) + "</tbody></table></div>"
                      "<p>" + ("Destino alcançado." if data.get("target_reached") else
                               "Caminho completo não confirmado.") + "</p></section>")
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
