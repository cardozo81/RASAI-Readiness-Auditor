"""#659 G3: offline consultative coordinate plot, not a physical network route."""
from __future__ import annotations

from html import escape
from colorsys import hsv_to_rgb
from ipaddress import ip_address
from math import isfinite
from typing import Any

from rasai.network_world_land import WORLD_LAND_SVG_PATH
from rasai.network_traceroute import MAX_HOPS_HARD_LIMIT
from rasai.network_public_egress import verified_families


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


def _geo_position(geo: Any) -> tuple[float, float] | None:
    """Precisely the verified coordinate rule used by the map renderer."""
    if not isinstance(geo, dict) or geo.get("state") != "OBSERVED":
        return None
    value = geo.get("value")
    if not isinstance(value, dict):
        return None
    lat = _coordinate(value.get("latitude"), -90, 90)
    lon = _coordinate(value.get("longitude"), -180, 180)
    radius = _coordinate(value.get("accuracy_radius_km"), 0, 20000)
    return (lat, lon) if lat is not None and lon is not None and radius is not None else None


def _public_hop(hop: Any) -> bool:
    if not isinstance(hop, dict) or hop.get("state") != "PUBLIC_HOP":
        return False
    try:
        return ip_address(hop.get("public_ip")).is_global
    except (TypeError, ValueError):
        return False


def map_reference_for_hop(hop: Any, points: dict) -> dict | None:
    """No synthetic map pin for unverified/remote-private hops."""
    if not _public_hop(hop):
        return None
    enrichment = hop.get("enrichment")
    geo = enrichment.get("geoip") if isinstance(enrichment, dict) else None
    position = _geo_position(geo)
    return points.get(position) if position is not None else None


def network_map_locations(probes: list[dict]) -> dict[tuple[float, float], dict]:
    """Stable identity and distinct colors from the exact map-eligible evidence.

    Colors are presentation metadata only; numbers are the accessible fallback.
    The default technical catalog renderer does not use these values.
    """
    coords: set[tuple[float, float]] = set()
    for probe in probes[:32]:
        metrics = probe.get("metrics") if isinstance(probe, dict) else None
        if not isinstance(metrics, dict):
            continue
        destination = _geo_position(metrics.get("geoip"))
        if destination is not None:
            coords.add(destination)
        for observation in verified_families(probe.get("public_egress")).values():
            enrichment = observation.get("enrichment")
            geo = enrichment.get("geoip") if isinstance(enrichment, dict) else None
            position = _geo_position(geo)
            if position is not None:
                coords.add(position)
        trace = metrics.get("traceroute")
        detail = trace.get("value") if isinstance(trace, dict) else None
        hops = detail.get("hops") if isinstance(detail, dict) else None
        if not isinstance(hops, list):
            continue
        for hop in hops[:MAX_HOPS_HARD_LIMIT]:
            if not _public_hop(hop):
                continue
            enrichment = hop.get("enrichment")
            geo = enrichment.get("geoip") if isinstance(enrichment, dict) else None
            position = _geo_position(geo)
            if position is not None:
                coords.add(position)
    result = {}
    used = set()
    for index, position in enumerate(sorted(coords), 1):
        # Irrational hue spacing distributes colors across the palette.
        # Ensure bytewise uniqueness, even after 8-bit RGB rounding.
        hue = ((index - 1) * 0.618033988749895) % 1
        while True:
            rgb = hsv_to_rgb(hue, 0.72, 0.68)
            color = "#" + "".join(f"{round(channel * 255):02x}" for channel in rgb)
            if color not in used:
                used.add(color)
                break
            hue = (hue + 0.0027) % 1
        result[position] = {
            "id": f"network-map-point-{index}",
            "number": index,
            "label": f"Ponto {index}",
            "color": color,
        }
    return result


def network_geographic_panel(probes: list[dict], *, presentation_mode: bool = False) -> str:
    """Render only approximate positions explicitly supplied by verified sidecars.

    No geographic paths/lines are inferred. A grid without coordinates is not
    a map of measured infrastructure, so absent enrichment has a logical fallback.
    """
    markers: dict[tuple[float, float], dict[str, Any]] = {}
    connections = []
    legend = []
    legend_entries = []
    point_refs = network_map_locations(probes) if presentation_mode else {}
    for probe in probes[:32]:
        measurements = probe.get("metrics")
        if not isinstance(measurements, dict):
            continue
        trace = measurements.get("traceroute") or {}
        trace_value = trace.get("value") if isinstance(trace, dict) else None
        hops = trace_value.get("hops") if isinstance(trace_value, dict) else None
        candidates = [("Destino: " + str(probe.get("hostname") or "público"),
                       measurements.get("geoip"), measurements.get("asn"), None, None)]
        egress_families = verified_families(probe.get("public_egress"))
        egress_captures = {}
        for family, observation in sorted(egress_families.items()):
            enrichment = observation.get("enrichment")
            if isinstance(enrichment, dict):
                name = "Saída pública IPv" + str(family) + ": " + observation["ip"]
                egress_captures[name] = observation.get("capture_utc")
                candidates.append((
                    name, enrichment.get("geoip"), enrichment.get("asn"), None, None
                ))
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
            # Public IPv4/IPv6 use their independent HTTPS observation timestamps.
            capture = str(egress_captures.get(name) or probe.get("capture_utc")
                          or "Data não comprovada")
            asn_value = asn.get("value") if isinstance(asn, dict) and asn.get("state") == "OBSERVED" else None
            organization = (("AS" + str(asn_value.get("number")) + " " +
                             str(asn_value.get("organization") or ""))
                            if isinstance(asn_value, dict) else "ASN indisponível")
            timing = str(rtt) + " ms" if type(rtt) in (int, float) and isfinite(rtt) and 0 <= rtt <= 60000 else "RTT indisponível"
            detail = organization + "; " + timing
            if presentation_mode and name in egress_captures and len(egress_families) == 2:
                detail += ("; mesma origem lógica: processo executor; "
                           "medições HTTPS IPv4 e IPv6 independentes")
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
            legend_entries.append((name, detail, lat, lon, radius, origin, capture))
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
    # Presentation-only deconfliction: preserve the measured geographic anchors.
    # Two distinct nearby coordinates can project to virtually the same SVG pixel.
    # Move the drawn symbols, not the recorded coordinates or their map identity.
    display_positions = {}
    offset_guides = []
    if presentation_mode:
        from math import hypot

        plotted = list(markers.items())
        def radius(group):
            return 11 if len(group["names"]) > 1 else 7

        crowded = {
            key for key, group in plotted
            if any(
                key != other_key
                and hypot(group["x"] - other["x"], group["y"] - other["y"])
                < radius(group) + radius(other) + 4
                for other_key, other in plotted
            )
        }
        occupied = [
            (group["x"], group["y"], radius(group))
            for key, group in plotted if key not in crowded
        ]
        for key, group in plotted:
            if key not in crowded:
                continue
            base_x, base_y, r = group["x"], group["y"], radius(group)
            placed = False
            for ring in range(1, max(12, len(crowded) * 2) + 1):
                step = 16 * ring
                offsets = (
                    (-step, 0), (step, 0), (0, -step), (0, step),
                    (-step, -step), (step, -step), (-step, step), (step, step),
                )
                for dx, dy in offsets:
                    x, y = base_x + dx, base_y + dy
                    if not (40 + r <= x <= 840 - r and 20 + r <= y <= 380 - r):
                        continue
                    if any(hypot(x - px, y - py) < r + pr + 4
                           for px, py, pr in occupied):
                        continue
                    display_positions[key] = (x, y)
                    occupied.append((x, y, r))
                    offset_guides.append(
                        f"<line data-map-layer='marker-offset-guide' "
                        f"x1='{base_x:.2f}' y1='{base_y:.2f}' "
                        f"x2='{x:.2f}' y2='{y:.2f}' stroke='#52677e' "
                        "stroke-width='1.2' stroke-dasharray='2 3' "
                        "pointer-events='none'/>"
                    )
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                occupied.append((base_x, base_y, r))

    svg_markers = []
    for position, group in markers.items():
        n = len(group["names"])
        x, y = display_positions.get(position, (group["x"], group["y"]))
        point = point_refs.get(position) if presentation_mode else None
        label = (f"{n} registros na mesma posição geográfica: "
                 + ", ".join(group["names"])) if n > 1 else group["descriptions"][0]
        identity = (
            f" id='{point['id']}' data-point-number='{point['number']}'"
            if point else ""
        )
        color = point["color"] if point else "#24578b"
        accessible = (point["label"] + ". " + label) if point else label
        if position in display_positions:
            accessible += (" Marcador deslocado no desenho; a linha auxiliar "
                           "indica a coordenada geográfica estimada original.")
        svg_markers.append(
            f"<g role='group'{identity} data-marker-count='{n}' "
            f"aria-label='{escape(accessible, quote=True)}'>"
            f"<title>{escape(accessible)}</title>"
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='{11 if n > 1 else 7}' "
            f"fill='{color}' stroke='#ffffff' stroke-width='2'/>"
            + (f"<text x='{x:.2f}' y='{y+3.5:.2f}' text-anchor='middle' "
               "font-size='10' font-weight='700' fill='#ffffff' "
               f"aria-hidden='true'>{n}</text>" if n > 1 else "")
            + "</g>"
        )
    if presentation_mode:
        legend = []
        for name, detail, lat, lon, radius, origin, capture in legend_entries:
            point = point_refs[(lat, lon)]
            legend.append(
                "<li tabindex='0'>"
                "<svg width='14' height='14' viewBox='0 0 14 14' aria-hidden='true'>"
                f"<rect x='1' y='1' width='12' height='12' rx='2' fill='{point['color']}'/></svg> "
                f"<a href='#{point['id']}'>{point['label']}</a> — "
                "<strong>" + escape(name) + "</strong>: " + escape(detail) + "; "
                f"{lat:.3f}°, {lon:.3f}°; raio de precisão: {radius:g} km. "
                "Fonte: " + escape(origin) + ". Data: " + escape(capture)
                + ". Referência IP aproximada, não equipamento físico.</li>"
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
        + ("<p class='rf'>Pontos próximos foram separados visualmente para evitar sobreposição. "
           "Guias curtos conectam cada símbolo deslocado à sua coordenada geográfica estimada original; "
           "não representam rotas de rede.</p>" if offset_guides else "")
        + "<div class='table-wrap'><svg viewBox='0 0 880 430' role='img' "
        "aria-label='Representação aproximada de locais com coordenadas documentadas' "
        "style='display:block;min-width:550px;max-width:100%;background:#f2f7fb'>"
        + "<path data-map-layer='land' d='" + WORLD_LAND_SVG_PATH +
        "' fill='#e1eee7' stroke='#91a7a0' stroke-width='0.7'/>" +
        "".join(grid) + "".join(connections) + "".join(offset_guides) + "".join(svg_markers) + "</svg></div>"
        "<p>Mapa base simplificado Natural Earth, escala 1:110 milhões "
        "(referência cartográfica de domínio público, não evidência de rede). "
        "A posição estimada é representada apenas pelos marcadores; nenhuma "
        "rota física é desenhada.</p>"
        "<h3>Origem e precisão de cada ponto</h3>"
        + ("<p>Os marcadores possuem cores individuais e identificadores Ponto N; "
           "um marcador compartilhado mantém a mesma cor em todas as observações. "
           if presentation_mode else
           "<p>Os números nos marcadores indicam quantos registros compartilham "
           "a mesma coordenada estimada. ")
        + "O detalhamento individual continua na lista abaixo e é acessível pelo teclado.</p><ul>" +
        "".join(legend) + "</ul>"
        "</section>"
    )
