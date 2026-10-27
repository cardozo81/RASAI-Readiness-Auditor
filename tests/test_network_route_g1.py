"""G1 report must preserve all measured hop slots without private IP disclosure."""
from rasai.network_progression import route_panels


def test_all_sixteen_hops_and_last_responder_are_visible():
    hops = [{"hop": i, "state": "NO_REPLY", "public_ip": None,
             "rtt_ms": None} for i in range(1, 17)]
    hops[0] = {"hop": 1, "state": "PRIVATE_HOP_REDACTED",
               "public_ip": None, "rtt_ms": 1.0}
    hops[-1] = {"hop": 16, "state": "PUBLIC_HOP", "public_ip": "8.8.8.8",
                "rtt_samples_ms": [9.0, 10.0], "rtt_ms": 9.0}
    row = {"hostname": "example.org", "metrics": {"traceroute": {
        "state": "OBSERVED", "value": {"hops": hops, "target_reached": False,
                                      "last_responding_hop": 16}}}}
    html = route_panels([row])
    assert html.count("<tr><th scope='row'>") == 16
    assert "último respondente" in html
    assert "Caminho completo não confirmado" in html
    assert "9.00 ms, 10.00 ms" in html
    assert "Sem IP" in html and "Oculto" in html
    assert "192.168." not in html
