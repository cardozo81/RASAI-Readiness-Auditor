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
    assert "LOCAL_MAXMIND_MMDB" in html
    assert "https:" not in html
