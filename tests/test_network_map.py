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
