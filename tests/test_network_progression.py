"""G3 historical projection never initiates collection."""
from rasai.network_progression import route_panels, temporal_panel


def test_route_does_not_expose_private_ips():
    probe = {"hostname": "public.example.com", "metrics": {
        "traceroute": {"state": "OBSERVED", "value": {
            "target_reached": False, "hops": [
                {"hop": 1, "state": "PRIVATE_HOP_REDACTED",
                 "public_ip": "192.168.0.1", "rtt_ms": 2},
                {"hop": 2, "state": "PUBLIC_HOP",
                 "public_ip": "8.8.8.8", "rtt_ms": 10},
            ]}}}}
    report = route_panels([probe])
    assert "192.168.0.1" not in report
    assert "8.8.8.8" in report and "Caminho completo não confirmado" in report


def test_history_only_comparable_observed_values():
    def row(utc, measured):
        return {"hostname": "site.example.com", "port": 443,
                "capture_utc": utc, "metrics": {
                    "tcp_handshake_ms": {"state": "OBSERVED", "value": measured}}}
    assert temporal_panel([row("2026-10-25T10:00:00Z", 20)]) == ""
    html = temporal_panel([row("2026-10-25T10:00:00Z", 20),
                           row("2026-10-26T10:00:00Z", 30)])
    assert "+10.00 ms" in html and "não comprovam causa" in html
