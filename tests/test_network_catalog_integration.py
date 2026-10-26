"""Issue #659: prove the sealed offline catalog consumes verified G2/G3 evidence.

No external DNS, sockets, traceroute process, GeoIP service or provider calls.
"""
from __future__ import annotations

import hashlib
import json

from rasai.catalog_report_site import (
    catalog_report_is_fresh, materialize_catalog_report_site,
    verify_catalog_report_package,
)
from rasai.network_active_probe import (
    CONTRACT, _canonical, probe_path,
)
from tests.test_catalog_report_site import AUDIT_ID, _workspace


def _write_verified_packet(workspace, series_id: str) -> None:
    root = workspace.root
    row = {
        "contract": CONTRACT,
        "audit_id": AUDIT_ID,
        "hostname": "example.org",
        "port": 443,
        "series_id": series_id,
        "measurement_origin": "TEST_ONLY_LOCAL_SYNTHETIC",
        "capture_utc": "2026-10-26T10:00:00Z",
        "state": "OBSERVED",
        "metrics": {
            "dns_resolution": {"state": "OBSERVED", "value": ["8.8.8.8"]},
            "tcp_handshake_ms": {"state": "OBSERVED", "value": 12.0},
            "geoip": {"state": "OBSERVED", "value": {
                "latitude": -30.0, "longitude": -51.2,
                "accuracy_radius_km": 100,
                "source": "Base de referência local controlada",
            }},
            "traceroute": {"state": "OBSERVED", "value": {
                "target_reached": False,
                "hops": [
                    {"hop": 1, "state": "PRIVATE_HOP_REDACTED",
                     "public_ip": None, "rtt_ms": 1.2},
                    {"hop": 2, "state": "PUBLIC_HOP",
                     "public_ip": "8.8.8.8", "rtt_ms": 12.0},
                ],
            }},
        },
    }
    row["sha256"] = hashlib.sha256(_canonical(row)).hexdigest()
    row["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
    path = probe_path(root, AUDIT_ID, "example.org", 443, series_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")


def test_network_probes_enter_sealed_offline_catalog_without_changing_aud(tmp_path):
    workspace, _non_catalog = _workspace(tmp_path)
    before = (workspace.root / "audit.db").read_bytes()
    _write_verified_packet(workspace, "sample-one")

    report = materialize_catalog_report_site(
        audit_id=AUDIT_ID, workspace=workspace,
    ).parent
    page = (report / "network.html").read_text(encoding="utf-8")
    assert "Medição complementar autorizada" in page
    assert "Mapa geográfico consultivo" in page
    assert "<svg" in page and "<circle" in page
    assert "Base de referência local controlada" in page
    assert "Etapas conhecidas do caminho" in page
    assert "192.168." not in page
    assert "Caminho completo não confirmado" in page

    valid, reasons = verify_catalog_report_package(report)
    assert valid, reasons
    assert catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace)
    assert (workspace.root / "audit.db").read_bytes() == before

    _write_verified_packet(workspace, "sample-two")
    assert not catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace)
    report = materialize_catalog_report_site(
        audit_id=AUDIT_ID, workspace=workspace,
    ).parent
    valid, reasons = verify_catalog_report_package(report)
    assert valid, reasons
    assert catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace)
    assert (workspace.root / "audit.db").read_bytes() == before
