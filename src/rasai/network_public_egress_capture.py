"""Independent post-AUD public-IP evidence, separate from the target probe.

A read-only report can reuse this immutable, integrity-checked packet without
DNS, sockets, HTTP requests or alterations to the sealed audit database.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from rasai.network_public_egress import (
    collect_bounded, enabled_providers, verified_families,
)

CONTRACT = "rasai-network-public-egress-v1"
_AUDIT_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_MAX_BYTES = 65_536
_FILENAME = "public-egress.json"


def egress_path(workspace: Path) -> Path:
    return workspace / "artifacts" / "network" / _FILENAME


def _canonical(row: dict) -> bytes:
    return json.dumps(row, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _workspace_is_valid(root: Path, audit_id: str) -> bool:
    if not isinstance(audit_id, str) or not _AUDIT_ID.fullmatch(audit_id):
        return False
    db = root / "audit.db"
    target = egress_path(root)
    if (root.is_symlink() or db.is_symlink() or not db.is_file()
            or target.is_symlink() or target.parent.is_symlink()
            or target.parent.parent.is_symlink()):
        return False
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True,
                             timeout=1) as connection:
            connection.execute("PRAGMA query_only=ON")
            return connection.execute(
                "SELECT 1 FROM audits WHERE audit_id=? LIMIT 1",
                (audit_id,),
            ).fetchone() is not None
    except (sqlite3.Error, OSError, ValueError):
        return False


def capture_public_egress(workspace: str | Path, audit_id: str) -> Path | None:
    """Best-effort capture only, after the AUD was sealed; never called by render."""
    from rasai.network_enrichment import enrich_public_ip
    from rasai.network_geoip_operations import local_databases

    root = Path(workspace)
    if not enabled_providers(os.environ) or not _workspace_is_valid(root, audit_id):
        return None
    path = egress_path(root)
    if path.exists() or path.is_symlink():
        return None
    captured = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        packet = collect_bounded(os.environ)
    except Exception:
        packet = {
            "state": "UNAVAILABLE", "families": {},
            "method": "FIXED_HTTPS_IP_ECHO_NO_PROXY",
            "measurement_origin": "LOCAL_OPERATOR_PROCESS",
            "scope": "EXTERNAL_ECHO_REQUEST_ONLY_NOT_BROWSER_OR_TARGET_TCP",
        }
    if packet.get("state") == "NOT_REQUESTED":
        return None
    # Reuse local databases only; neither download nor request GeoIP here.
    if os.environ.get("RASAI_NETWORK_GEOIP_SOURCE", "LOCAL_FIRST") != "DISABLED":
        try:
            databases = local_databases()
            for family, observed in verified_families(packet).items():
                try:
                    packet["families"]["ipv" + str(family)]["enrichment"] = enrich_public_ip(
                        observed["ip"], asn_database=databases["asn_database"],
                        city_database=databases["city_database"],
                    )
                except (OSError, ValueError, TypeError, RuntimeError, KeyError):
                    pass
        except (OSError, ValueError, TypeError, RuntimeError, KeyError):
            pass
    row = {
        "contract": CONTRACT, "audit_id": audit_id,
        "capture_utc": captured,
        "measurement_origin": "LOCAL_OPERATOR_PROCESS",
        "method": "INDEPENDENT_EXTERNAL_HTTPS_IP_ECHO",
        "public_egress": packet,
    }
    digest = hashlib.sha256(_canonical(row)).hexdigest()
    row["sha256"] = digest
    row["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
    if len(_canonical(row)) > _MAX_BYTES:
        return None
    # Fail closed if a path was swapped since the initial preflight.
    if (root.is_symlink() or path.is_symlink() or
            path.parent.is_symlink() or path.parent.parent.is_symlink()):
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(row, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        return path
    except (OSError, ValueError, TypeError):
        return None


def read_public_egress_probe(workspace: str | Path, audit_id: str) -> dict | None:
    """Return a minimal, distinct presentation observation; ignore invalid packets."""
    root = Path(workspace)
    path = egress_path(root)
    if (not isinstance(audit_id, str) or not _AUDIT_ID.fullmatch(audit_id)
            or root.is_symlink() or path.is_symlink()
            or path.parent.is_symlink() or path.parent.parent.is_symlink()
            or not path.is_file()):
        return None
    try:
        if path.stat().st_size > _MAX_BYTES:
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(row, dict) or row.get("contract") != CONTRACT
                or row.get("audit_id") != audit_id
                or row.get("measurement_origin") != "LOCAL_OPERATOR_PROCESS"
                or row.get("method") != "INDEPENDENT_EXTERNAL_HTTPS_IP_ECHO"
                or row.get("digest_scope") != "INTEGRITY_ONLY_NOT_AUTHORSHIP"):
            return None
        sig = row.pop("sha256", None)
        row.pop("digest_scope", None)
        if (not isinstance(sig, str)
                or not hmac.compare_digest(hashlib.sha256(_canonical(row)).hexdigest(), sig)):
            return None
        packet = row.get("public_egress")
        if (not isinstance(packet, dict)
                or packet.get("state") not in ("OBSERVED", "PARTIAL", "UNAVAILABLE")):
            return None
        # Never synthesize a TCP observation or falsely bind this echo to a URL.
        return {
            "contract": CONTRACT,
            "capture_utc": row.get("capture_utc"),
            "measurement_origin": "LOCAL_OPERATOR_PROCESS",
            "method": "INDEPENDENT_EXTERNAL_HTTPS_IP_ECHO",
            "hostname": None, "metrics": {},
            "public_egress": packet,
        }
    except (OSError, UnicodeError, ValueError, TypeError, OverflowError):
        return None


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Verificação externa opcional de IP público")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--audit-id", required=True)
    args = parser.parse_args()
    capture_public_egress(args.workspace, args.audit_id)


if __name__ == "__main__":
    main()
