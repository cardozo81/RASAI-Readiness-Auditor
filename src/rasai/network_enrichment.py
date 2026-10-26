"""#659 G2: optional strictly offline enrichment; no GeoIP provider requests."""
from __future__ import annotations

import hashlib
import importlib
import ipaddress
from math import isfinite
from pathlib import Path


def _unobserved():
    return {"state": "NOT_OBSERVED", "value": None, "error": None}


def _dataset(path: str):
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Arquivo geográfico inválido")
    size = source.stat().st_size
    if size <= 0 or size > 180_000_000:
        raise ValueError("Base geográfica fora do limite")
    digest = hashlib.sha256()
    with source.open("rb") as stream:
        for block in iter(lambda: stream.read(1_048_576), b""):
            digest.update(block)
    return source, digest.hexdigest()


def _field(v, low: float, high: float):
    if type(v) not in (int, float):
        return None
    number = float(v)
    return number if isfinite(number) and low <= number <= high else None


def enrich_public_ip(ip: str, *, asn_database: str | None = None,
                     city_database: str | None = None) -> dict:
    """Use operator-supplied MMDB only. Dataset hash is integrity, not authenticity."""
    try:
        address = ipaddress.ip_address(ip)
        if not address.is_global:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError("Enriquecimento restrito a endereço IP público")
    metrics = {"asn": _unobserved(), "geoip": _unobserved()}
    if not asn_database and not city_database:
        return metrics
    try:
        mmdb = importlib.import_module("maxminddb")
    except ImportError:
        for key, source in (("asn", asn_database), ("geoip", city_database)):
            if source:
                metrics[key] = {"state": "COLLECTION_FAILED", "value": None,
                                "error": "OPTIONAL_MMDB_READER_UNAVAILABLE"}
        return metrics
    for name, path in (("asn", asn_database), ("geoip", city_database)):
        if not path:
            continue
        try:
            dbfile, sha = _dataset(path)
            reader = mmdb.open_database(str(dbfile))
            try:
                data = reader.get(str(address))
            finally:
                reader.close()
            if not isinstance(data, dict):
                continue
            if name == "asn":
                number = data.get("autonomous_system_number")
                organization = data.get("autonomous_system_organization")
                if type(number) is int and number > 0 and number < 4_294_967_296:
                    metrics[name] = {"state": "OBSERVED", "error": None, "value": {
                        "number": number,
                        "organization": (organization[:128] if isinstance(organization, str)
                                         else None),
                        "source": "LOCAL_MMDB_ASN",
                        "dataset_sha256": sha,
                        "confidence": "DATABASE_ATTRIBUTION_NOT_ORIGIN_PROOF",
                    }}
            else:
                loc = data.get("location")
                if not isinstance(loc, dict):
                    continue
                latitude = _field(loc.get("latitude"), -90, 90)
                longitude = _field(loc.get("longitude"), -180, 180)
                radius = _field(loc.get("accuracy_radius"), 0, 20000)
                if None in (latitude, longitude, radius):
                    continue
                metrics[name] = {"state": "OBSERVED", "error": None, "value": {
                    "latitude": latitude, "longitude": longitude,
                    "accuracy_radius_km": radius,
                    "source": "LOCAL_MMDB_CITY", "dataset_sha256": sha,
                    "confidence": "APPROXIMATE_DATABASE_GEOLOCATION",
                }}
        except (OSError, ValueError, TypeError, KeyError):
            metrics[name] = {"state": "COLLECTION_FAILED", "value": None,
                             "error": "LOCAL_DATASET_UNAVAILABLE_OR_INVALID"}
    return metrics
