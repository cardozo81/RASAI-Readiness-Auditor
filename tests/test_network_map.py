"""Offline geo visualization is grounded only in persisted approximate GeoIP."""
from rasai.network_map import network_geographic_panel


def test_geo_panel_refuses_unproven_coordinates_and_unsafe_types():
    assert "nenhum ponto ou trajeto" in network_geographic_panel([])
    invalid = {"hostname": "site.example", "metrics": {
        "geoip": {"state": "OBSERVED",
                  "value": {"latitude": True, "longitude": 9,
                            "accuracy_radius_km": 10}}
    }}
    assert "<svg" not in network_geographic_panel([invalid])


def test_geo_panel_uses_approximation_without_physical_routes():
    row = {"hostname": "<site>", "capture_utc": "2026-10-26T10:00:00Z",
           "metrics": {"geoip": {"state": "OBSERVED", "value": {
               "latitude": -30.0, "longitude": -51.1,
               "accuracy_radius_km": 120,
               "source": "LOCAL_MAXMIND_MMDB"}}}}
    html = network_geographic_panel([row])
    assert "<svg" in html and "<circle" in html
    assert "Posição estimada" in html and "120 km" in html
    assert "&lt;site&gt;" in html and "<site>" not in html
    assert "data-map-layer='land'" in html
    assert "data-map-layer='network-route'" not in html
    assert "Origem e precisão de cada ponto" in html
    assert "Base local de geolocalização IP (GeoIP)" in html
    assert "LOCAL_MAXMIND_MMDB" not in html
    assert "https:" not in html


def test_map_renders_observed_hops_with_independent_geoip_asn():
    row = {"hostname": "example.org", "capture_utc": "2026-10-26T10:00:00Z",
           "metrics": {"traceroute": {"state": "OBSERVED", "value": {
               "hops": [
                   {"hop": 1, "state": "PUBLIC_HOP", "public_ip": "8.8.8.8",
                    "rtt_ms": 12.5, "enrichment": {
                        "geoip": {"state": "OBSERVED", "value": {
                            "latitude": 37.4, "longitude": -122.1,
                            "accuracy_radius_km": 50, "source": "LOCAL_MMDB_CITY"}},
                        "asn": {"state": "OBSERVED", "value": {
                            "number": 15169, "organization": "Example Operator"}}}},
                   {"hop": 2, "state": "NO_REPLY", "public_ip": None},
                   {"hop": 3, "state": "PUBLIC_HOP", "public_ip": "1.1.1.1",
                    "enrichment": {"asn": {"state": "OBSERVED", "value": {
                        "number": 13335, "organization": "Other Operator"}}}}
               ]}}}}
    html = network_geographic_panel([row])
    assert html.count("<circle") == 1
    assert "Hop 1: 8.8.8.8" in html
    assert "AS15169" in html and "12.5 ms" in html
    assert "Hop 2:" not in html and "Hop 3:" not in html
    assert "data-map-layer='network-route'" not in html


def test_map_does_not_render_private_or_invalid_hop_ips():
    row = {"hostname": "example.org", "metrics": {"traceroute": {
        "state": "OBSERVED", "value": {"hops": [
            {"hop": 1, "state": "PUBLIC_HOP", "public_ip": "192.168.1.1",
             "enrichment": {"geoip": {"state": "OBSERVED", "value": {
                 "latitude": 10.0, "longitude": 20.0, "accuracy_radius_km": 10}}}},
            {"hop": 2, "state": "PUBLIC_HOP", "public_ip": "<invalido>",
             "enrichment": {"geoip": {"state": "OBSERVED", "value": {
                 "latitude": 10.0, "longitude": 20.0, "accuracy_radius_km": 10}}}}
        ]}}}}
    html = network_geographic_panel([row])
    assert "<svg" not in html
    assert "192.168.1.1" not in html
    assert "&lt;invalido&gt;" not in html


def test_sixteen_hop_ceiling_is_consistent_with_map():
    hops = [{"hop": i, "state": "NO_REPLY"} for i in range(1, 17)]
    hops[-1] = {"hop": 16, "state": "PUBLIC_HOP", "public_ip": "8.8.8.8",
                "enrichment": {"geoip": {"state": "OBSERVED", "value": {
                    "latitude": -30.0, "longitude": -51.0,
                    "accuracy_radius_km": 100, "source": "LOCAL_MMDB_CITY"}}}}
    row = {"hostname": "example.org", "metrics": {"traceroute": {
        "state": "OBSERVED", "value": {"hops": hops}}}}
    assert "Hop 16: 8.8.8.8" in network_geographic_panel([row])


def test_geo_links_only_adjacent_observed_coordinates():
    def hop(index, geo=True):
        return {"hop": index, "state": "PUBLIC_HOP", "public_ip": "8.8.8.8",
                "enrichment": {"geoip": {"state": "OBSERVED" if geo else "NOT_OBSERVED",
                    "value": {"latitude": index * 1.0, "longitude": index * 2.0,
                              "accuracy_radius_km": 50} if geo else None}}}
    row = {"metrics": {"traceroute": {"state": "OBSERVED", "value": {
        "hops": [hop(1), hop(2), hop(3, False), hop(4), hop(5)]}}}}
    html = network_geographic_panel([row])
    assert html.count("data-map-layer='logical-sequence'") == 2
    assert "não são rotas físicas medidas" in html


def test_same_coordinates_are_aggregated_without_losing_records():
    """Regression: 13 geolocated hops + destination in only four locations."""
    coords = [(20.0, 30.0)] * 2 + [(30.0, 40.0)] * 3 + [(40.0, 50.0)] * 8
    def geo(lat, lon):
        return {"state": "OBSERVED", "value": {
            "latitude": lat, "longitude": lon, "accuracy_radius_km": 150,
            "source": "LOCAL_MMDB_CITY"}}
    hops = [{"hop": index, "state": "PUBLIC_HOP",
             "public_ip": "2001:4860:4860::" + str(index),
             "rtt_ms": float(index),
             "enrichment": {"geoip": geo(*position), "asn": {
                 "state": "OBSERVED", "value": {"number": 15169,
                                                  "organization": "Operador"}}}}
            for index, position in enumerate(coords, 1)]
    row = {"hostname": "example.org", "capture_utc": "2026-10-27T13:26:45Z",
           "metrics": {"geoip": geo(10.0, 20.0), "traceroute": {
               "state": "OBSERVED", "value": {
                   "hops": hops, "target_reached": False}}}}
    html = network_geographic_panel([row])
    assert html.count("<circle") == 4
    assert html.count("<li tabindex='0'>") == 14
    for n in (1, 2, 3, 8):
        assert f"data-marker-count='{n}'" in html
    assert html.count("data-map-layer='logical-sequence'") == 2
    assert "Hop 13" in html and "Destino: example.org" in html
    assert "não são rotas físicas medidas" in html


def test_presentation_point_colors_are_unique_stable_and_shared_without_changing_catalog():
    from rasai.network_map import network_map_locations
    def geo(lat, lon):
        return {"state": "OBSERVED", "value": {
            "latitude": lat, "longitude": lon, "accuracy_radius_km": 75,
            "source": "LOCAL_MAXMIND_MMDB"}}
    row = {"hostname": "example.test", "metrics": {
        "geoip": geo(-30.0, -51.0),
        "traceroute": {"state": "OBSERVED", "value": {"hops": [
            {"hop": 1, "state": "PUBLIC_HOP", "public_ip": "8.8.8.8",
             "enrichment": {"geoip": geo(-30.0, -51.0)}},
            {"hop": 2, "state": "PUBLIC_HOP", "public_ip": "1.1.1.1",
             "enrichment": {"geoip": geo(40.0, -74.0)}},
            {"hop": 3, "state": "PUBLIC_HOP", "public_ip": "9.9.9.9",
             "enrichment": {"geoip": geo(48.0, 2.0)}},
            {"hop": 4, "state": "NO_REPLY"},
        ]}}}}
    points = network_map_locations([row])
    assert len(points) == 3
    assert len({p["color"] for p in points.values()}) == 3
    assert points == network_map_locations([row])
    assert list(p["number"] for p in points.values()) == [1, 2, 3]
    presentation = network_geographic_panel([row], presentation_mode=True)
    technical = network_geographic_panel([row])
    assert technical.count("fill='#24578b'") == 3
    assert "data-point-number=" not in technical and "Ponto 1" not in technical
    assert presentation.count("data-point-number=") == 3
    assert presentation.count("data-marker-count='2'") == 1
    assert presentation.count("<li tabindex='0'>") == 4
    for point in points.values():
        assert f"id='{point['id']}'" in presentation
        assert f"fill='{point['color']}'" in presentation
        assert f"href='#{point['id']}'" in presentation
    # Missing GeoIP is never assigned a pin or a color.
    assert "Hop 4:" not in presentation
    assert "Não é posição física comprovada" in presentation


def test_presentation_hop_table_links_only_truly_plotted_locations():
    from rasai.network_map import network_map_locations
    from rasai.parallel_report.scope_context import _network_hop_rows
    from rasai.parallel_report.components import table

    geo = {"state": "OBSERVED", "value": {
        "latitude": 10.0, "longitude": 20.0, "accuracy_radius_km": 100}}
    probes = [{"hostname": "example.test", "metrics": {
        "traceroute": {"state": "OBSERVED", "value": {"hops": [
            {"hop": 1, "state": "PUBLIC_HOP", "public_ip": "8.8.8.8",
             "enrichment": {"geoip": geo}},
            {"hop": 2, "state": "PUBLIC_HOP", "public_ip": "1.1.1.1",
             "enrichment": {}},
            {"hop": 3, "state": "NO_REPLY"},
        ]}}}}]
    positions = network_map_locations(probes)
    mapped = _network_hop_rows(probes, "UTC", map_locations=positions)
    assert len(mapped) == 3
    assert mapped[0]["_map_point"] == positions[(10.0, 20.0)]
    assert mapped[1]["_map_point"] is None
    assert mapped[2]["_map_point"] is None
    html = table("Saltos verificados", mapped,
                 [("hop", "Salto"), ("_map_point", "Ponto no mapa")])
    assert html.count("Ponto 1</a>") == 1
    assert html.count("Não localizado no mapa") >= 2
    assert f"fill=\"{positions[(10.0, 20.0)]['color']}\"" in html
    assert "href=\"#network-map-point-1\"" in html

def test_presentation_nearby_geoip_points_are_individually_visible_without_changing_evidence():
    """Real-world IPv4/IPv6 overlap must not hide the red point behind the blue one."""
    import re
    from math import hypot
    from rasai.network_map import network_map_locations

    def geo(lat, lon):
        return {"state": "OBSERVED", "value": {
            "latitude": lat, "longitude": lon,
            "accuracy_radius_km": 20, "source": "LOCAL_MMDB_CITY",
        }}

    probes = [{"hostname": "example.test", "capture_utc": "2026-11-23T12:36:31Z",
        "metrics": {"geoip": geo(-23.547, -46.636)},
        "public_egress": {"state": "OBSERVED", "families": {
            "ipv4": {"state": "OBSERVED", "ip": "8.8.8.8", "provider": "IPIFY",
                     "capture_utc": "2026-11-23T12:36:31Z",
                     "enrichment": {"geoip": geo(-30.027, -51.235)}},
            "ipv6": {"state": "OBSERVED", "ip": "2606:4700:4700::1111",
                     "provider": "IPIFY", "capture_utc": "2026-11-23T12:36:32Z",
                     "enrichment": {"geoip": geo(-29.909, -50.957)}},
        }},
    }]
    refs = network_map_locations(probes)
    html = network_geographic_panel(probes, presentation_mode=True)
    assert len(refs) == 3 and html.count("data-point-number=") == 3
    assert html.count("data-map-layer='marker-offset-guide'") == 2
    assert "não representam rotas de rede" in html
    assert "Saída pública IPv4: 8.8.8.8" in html
    assert "Saída pública IPv6: 2606:4700:4700::1111" in html
    assert "Coleta: 2026-11-23T12:36:32Z" in html

    rendered = {}
    for coordinate, point in refs.items():
        match = re.search(
            rf"id='{point['id']}'[^>]*>.*?<circle cx='([0-9.]+)' "
            rf"cy='([0-9.]+)' r='7' fill='{re.escape(point['color'])}'",
            html,
            re.DOTALL,
        )
        assert match is not None
        rendered[coordinate] = (float(match.group(1)), float(match.group(2)))
        assert f"href='#{point['id']}'" in html

    ipv4 = rendered[(-30.027, -51.235)]
    ipv6 = rendered[(-29.909, -50.957)]
    assert hypot(ipv4[0] - ipv6[0], ipv4[1] - ipv6[1]) >= 18
    assert "-30.027°, -51.235°" in html
    assert "-29.909°, -50.957°" in html
    assert "Ponto 1" in html and "Ponto 2" in html and "Ponto 3" in html

    # Technical catalog renderer retains its previous, unshifted coordinates.
    plain = network_geographic_panel(probes)
    assert "marker-offset-guide" not in plain
    assert "Pontos próximos foram separados" not in plain


def test_presentation_nonoverlapping_map_does_not_add_offset_guides():
    row = {"hostname": "example.test", "metrics": {"geoip": {
        "state": "OBSERVED", "value": {
            "latitude": -30.0, "longitude": -51.0,
            "accuracy_radius_km": 20, "source": "LOCAL_MMDB_CITY",
        },
    }}}
    html = network_geographic_panel([row], presentation_mode=True)
    assert "data-marker-count='1'" in html
    assert "marker-offset-guide" not in html
    assert "Pontos próximos foram separados" not in html
