"""#659 G2: offline ASN/GeoIP requires provenance and never invokes providers."""
import sys
from types import SimpleNamespace

from rasai import network_enrichment as e


def test_without_dataset_fails_conservatively():
    out = e.enrich_public_ip("8.8.8.8")
    assert out["geoip"]["state"] == "NOT_OBSERVED"
    assert out["asn"]["state"] == "NOT_OBSERVED"


def test_local_dataset_asn_and_geoip_with_validity(tmp_path, monkeypatch):
    asn = tmp_path / "asn.mmdb"
    city = tmp_path / "city.mmdb"
    asn.write_bytes(b"authenticity-not-implied")
    city.write_bytes(b"coordinate-data")
    class Reader:
        def __init__(self, path):
            self.path = path
        def get(self, ip):
            if self.path == str(asn):
                return {"autonomous_system_number": 15169,
                        "autonomous_system_organization": "Example ASN"}
            return {"location": {"latitude": -30.0, "longitude": -51.0,
                                 "accuracy_radius": 200}}
        def close(self):
            pass
    monkeypatch.setitem(sys.modules, "maxminddb",
                        SimpleNamespace(open_database=lambda path: Reader(path)))
    out = e.enrich_public_ip("8.8.8.8", asn_database=str(asn),
                             city_database=str(city))
    assert out["asn"]["value"]["number"] == 15169
    assert out["geoip"]["value"]["accuracy_radius_km"] == 200
    assert len(out["geoip"]["value"]["dataset_sha256"]) == 64
    assert out["geoip"]["value"]["source"] == "LOCAL_MMDB_CITY"


def test_private_ip_never_enriched(tmp_path):
    try:
        e.enrich_public_ip("127.0.0.1", city_database="anything")
    except ValueError:
        pass
    else:
        assert False, "Private address was accepted"
