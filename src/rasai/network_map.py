"""#659 G3: offline consultative coordinate plot, not a physical network route."""
from __future__ import annotations

from html import escape
from ipaddress import ip_address
from math import isfinite
from typing import Any

from rasai.network_world_land import WORLD_LAND_SVG_PATH
from rasai.network_traceroute import MAX_HOPS_HARD_LIMIT


def _coordinate(value: Any, lower: float, upper: float) -> float | None:
    if type(value) not in (int, float):
        return None
    number = float(value)
    return number if isfinite(number) and lower <= number <= upper else None


def _public_source_label(value: Any) -> str:
    """Keep a meaningful source category without leaking internal machine IDs."""
    if value in ("LOCAL_MMDB_CITY", "LOCAL_MAXMIND_MMDB"):
        return "Base local de geolocalização IP (GeoIP)"
    if isinstance(value, str) and 1 <= len(value) <= 100:
        # A supplied human-readable source name is safe to display escaped.
        if not (value.isupper() and "_" in value):
            return value
    return "Base de referência geográfica informada na medição"


def network_geographic_panel(probes: list[dict]) -> str:
    """Render only approximate positions explicitly supplied by verified sidecars.

    No geographic paths/lines are inferred. A grid without coordinates is not
    a map of measured infrastructure, so absent enrichment has a logical fallback.
    """
    markers: dict[tuple[float, float], dict[str, Any]] = {}
    connections = []
    legend = []
    for probe in probes[:32]:
        measurements = probe.get("metrics")
        if not isinstance(measurements, dict):
            continue
        trace = measurements.get("traceroute") or {}
        trace_value = trace.get("value") if isinstance(trace, dict) else None
        hops = trace_value.get("hops") if isinstance(trace_value, dict) else None
        candidates = [("Destino: " + str(probe.get("hostname") or "público"),
                       measurements.get("geoip"), measurements.get("asn"), None, None)]
        if isinstance(hops, list):
            for hop in hops[:MAX_HOPS_HARD_LIMIT]:
                if not isinstance(hop, dict):
                    continue
                if hop.get("state") != "PUBLIC_HOP":
                    candidates.append(("", None, None, hop.get("hop"), None))
                    continue
                try:
                    address = ip_address(hop.get("public_ip"))
                    if not address.is_global:
                        continue
                except (TypeError, ValueError):
                    continue
                enrichment = hop.get("enrichment") or {}
                if not isinstance(enrichment, dict):
                    continue
                candidates.append(("Hop " + str(hop.get("hop")) + ": " +
                                   str(address), enrichment.get("geoip"),
                                   enrichment.get("asn"), hop.get("hop"), hop.get("rtt_ms")))
        prior_position = None
        for name, geo, asn, hop_number, rtt in candidates:
            if not isinstance(geo, dict) or geo.get("state") != "OBSERVED":
                prior_position = None
                continue
            value = geo.get("value")
            if not isinstance(value, dict):
                prior_position = None
                continue
            lat = _coordinate(value.get("latitude"), -90, 90)
            lon = _coordinate(value.get("longitude"), -180, 180)
            radius = _coordinate(value.get("accuracy_radius_km"), 0, 20000)
            if lat is None or lon is None or radius is None:
                prior_position = None
                continue
            origin = _public_source_label(value.get("source"))
            capture = str(probe.get("capture_utc") or "Data não comprovada")
            asn_value = asn.get("value") if isinstance(asn, dict) and asn.get("state") == "OBSERVED" else None
            organization = (("AS" + str(asn_value.get("number")) + " " +
                             str(asn_value.get("organization") or ""))
                            if isinstance(asn_value, dict) else "ASN indisponível")
            timing = str(rtt) + " ms" if type(rtt) in (int, float) and isfinite(rtt) and 0 <= rtt <= 60000 else "RTT indisponível"
            detail = organization + "; " + timing
            desc = (f"{name}. {detail}. Posição estimada {lat:.3f}°, {lon:.3f}°. "
                    f"Precisão: raio de {radius:g} km. Fonte: {origin}. "
                    f"Coleta: {capture}. Não é posição física comprovada.")
            x, y = 40 + (lon + 180) / 360 * 800, 20 + (90 - lat) / 180 * 360
            if type(hop_number) is int:
                if prior_position is not None and prior_position[0] + 1 == hop_number:
                    px, py = prior_position[1:]
                    if (px, py) != (x, y):
                        connections.append(
                            f"<line data-map-layer='logical-sequence' x1='{px:.2f}' y1='{py:.2f}' "
                            f"x2='{x:.2f}' y2='{y:.2f}' stroke='#667c96' "
                            "stroke-width='1.5' stroke-dasharray='5 5'/>"
                        )
                prior_position = (hop_number, x, y)
            else:
                prior_position = None
            # Keep the original coordinates and each individual observation.
            # Coincident IP geolocations are displayed as a single cluster.
            group = markers.setdefault((lat, lon), {"x": x, "y": y, "names": [], "descriptions": []})
            group["names"].append(name)
            group["descriptions"].append(desc)
            legend.append(
                "<li tabindex='0'><strong>" + escape(name) + "</strong>: " + escape(detail) + "; " +
                f"{lat:.3f}°, {lon:.3f}°; raio de precisão: {radius:g} km. "
                "Fonte: " + escape(origin) + ". Data: " + escape(capture) +
                ". Referência IP aproximada, não equipamento físico.</li>"
            )
    if not markers:
        return (
            "<section class='panel'><h2>Mapa e caminho de rede</h2>"
            "<p>Não há coordenadas geográficas sustentadas por uma fonte persistida. "
            "Por isso, nenhum ponto ou trajeto físico é desenhado. "
            "O destino observado, a resolução de nomes e as conexões "
            "estão detalhados nas tabelas de rede, quando disponíveis.</p>"
            "</section>"
        )
    svg_markers = []
    for group in markers.values():
        n = len(group["names"])
        x, y = group["x"], group["y"]
        label = (f"{n} registros na mesma posição geográfica: "
                 + ", ".join(group["names"])) if n > 1 else group["descriptions"][0]
        svg_markers.append(
            f"<g role='group' data-marker-count='{n}' aria-label='{escape(label, quote=True)}'>"
            f"<title>{escape(label)}</title>"
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='{11 if n > 1 else 7}' "
            "fill='#24578b' stroke='#ffffff' stroke-width='2'/>"
            + (f"<text x='{x:.2f}' y='{y+3.5:.2f}' text-anchor='middle' "
               "font-size='10' font-weight='700' fill='#ffffff' "
               f"aria-hidden='true'>{n}</text>" if n > 1 else "")
            + "</g>"
        )
    grid = []
    for lon in range(-180, 181, 60):
        x = 40 + (lon + 180) / 360 * 800
        grid.append(f"<line x1='{x:.2f}' y1='20' x2='{x:.2f}' y2='380' stroke='#d6e2ec'/>")
        grid.append(f"<text x='{x:.2f}' y='402' text-anchor='middle' font-size='12' fill='#3e5160'>{lon}°</text>")
    for lat in range(-90, 91, 30):
        y = 20 + (90 - lat) / 180 * 360
        grid.append(f"<line x1='40' y1='{y:.2f}' x2='840' y2='{y:.2f}' stroke='#d6e2ec'/>")
        grid.append(f"<text x='30' y='{y+4:.2f}' text-anchor='end' font-size='12' fill='#3e5160'>{lat}°</text>")
    return (
        "<section class='panel'><h2>Mapa geográfico consultivo</h2>"
        "<p>Pontos são estimativas geográficas da referência IP, "
        "com precisão limitada pela base local; não representam necessariamente "
        "a sede, o centro de dados, a rota percorrida ou a posição de um usuário. "
        "Linhas tracejadas, quando presentes, apenas ilustram saltos consecutivos com coordenadas; não são rotas físicas medidas.</p>"
        "<div class='table-wrap'><svg viewBox='0 0 880 430' role='img' "
        "aria-label='Representação aproximada de locais com coordenadas documentadas' "
        "style='display:block;min-width:550px;max-width:100%;background:#f2f7fb'>"
        + "<path data-map-layer='land' d='" + WORLD_LAND_SVG_PATH +
        "' fill='#e1eee7' stroke='#91a7a0' stroke-width='0.7'/>" +
        "".join(grid) + "".join(connections) + "".join(svg_markers) + "</svg></div>"
        "<p>Mapa base simplificado Natural Earth, escala 1:110 milhões "
        "(referência cartográfica de domínio público, não evidência de rede). "
        "A posição estimada é representada apenas pelos marcadores; nenhuma "
        "rota física é desenhada.</p>"
        "<h3>Origem e precisão de cada ponto</h3>"
        "<p>Os números nos marcadores indicam quantos registros compartilham "
        "a mesma coordenada estimada. O detalhamento individual continua "
        "na lista abaixo e é acessível pelo teclado.</p><ul>" +
        "".join(legend) + "</ul>"
        "</section>"
    )
