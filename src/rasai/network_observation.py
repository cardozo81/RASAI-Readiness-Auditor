"""#659 G1: passive, read-only network snapshot from persisted AUD observations.

This is not a probe. Unknown fields remain unknown, and the SHA-256 below
detects accidental changes but does not authenticate the audit's author.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
from typing import Any

from rasai.architecture_audit_facts import read_architecture_audit_facts

CONTRACT = "rasai-network-observation-v1"
_STATES = frozenset({
    "OBSERVED", "NOT_OBSERVED", "BLOCKED",
    "NOT_APPLICABLE", "INCONCLUSIVE", "COLLECTION_FAILED",
})


def _item(value: Any, *, source: str, state: str | None = None) -> dict[str, Any]:
    if state is None:
        state = "OBSERVED" if value is not None else "NOT_OBSERVED"
    if state not in _STATES:
        state = "INCONCLUSIVE"
    return {"state": state, "value": value if state == "OBSERVED" else None,
            "source": source, "measurement_origin": "AUD_PERSISTED_CAPTURE"}


def _public_ip(value: Any) -> str | None:
    try:
        ip = ipaddress.ip_address(value)
        return str(ip) if ip.is_global else None
    except (ValueError, TypeError):
        return None


def snapshots_from_audit(database: str | Path, audit_id: str) -> list[dict[str, Any]]:
    """Project only persisted facts. No network, writes, or refresh of sealed AUD."""
    records = read_architecture_audit_facts(database, audit_id)
    output = []
    for record in records:
        facts = record.get("network_facts") or {}
        sec = facts.get("main_response_security") or {}
        state = facts.get("main_response_state")
        absent = "NOT_OBSERVED" if state in (
            "NOT_COLLECTED", "NO_OBSERVATIONS", "UNAVAILABLE",
            "UNAVAILABLE_RENDER_FAILURE", None,
        ) else "INCONCLUSIVE"
        peer = _public_ip(sec.get("remote_public_peer_ip"))
        metrics = {
            "connected_public_ip": _item(peer, source="CDP_MAIN_DOCUMENT_RESPONSE",
                                         state="OBSERVED" if peer else absent),
            "tls_protocol": _item(sec.get("tls_protocol"), source="CDP_MAIN_DOCUMENT_RESPONSE",
                                  state="OBSERVED" if sec.get("tls_protocol") else absent),
            "http_protocol": _item(sec.get("http_protocol"), source="CDP_MAIN_DOCUMENT_RESPONSE",
                                   state="OBSERVED" if sec.get("http_protocol") else absent),
            "http_status": _item(record.get("http_status_observed"), source="RAW_HTTP_CAPTURE"),
            "redirect_count": _item(record.get("http_redirects_observed"), source="RAW_HTTP_CAPTURE"),
            "dns_resolution": _item(None, source="NO_DNS_CAPTURE"),
            "tcp_handshake_ms": _item(None, source="NO_TCP_TIMING_CAPTURE"),
            "tls_handshake_ms": _item(None, source="NO_TLS_TIMING_CAPTURE"),
            "traceroute": _item(None, source="NO_ACTIVE_PROBE"),
            "asn": _item(None, source="NO_ENRICHMENT"),
            "geoip": _item(None, source="NO_ENRICHMENT"),
        }
        payload = {
            "contract": CONTRACT,
            "audit_id": record["audit_id"],
            "observation_id": record["snapshot_id"],
            "page_id": record["page_id"],
            "device": record.get("device"),
            "method": "PASSIVE_READ_ONLY",
            "measurement_origin": "AUD_PERSISTED_CAPTURE",
            "capture_utc": None,
            "capture_time_state": "NOT_OBSERVED",
            "topology_state": "INCONCLUSIVE",
            "confidence": "OBSERVED_FIELDS_ONLY",
            "source_contract": record.get("contract"),
            "metrics": metrics,
            "limits": [
                "IP conectado não comprova origem física nem infraestrutura interna.",
                "Ausência de registro não demonstra falha na rede.",
                "Snapshot consultivo não altera a auditoria original.",
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False).encode("utf-8")
        payload["sha256"] = hashlib.sha256(canonical).hexdigest()
        payload["digest_scope"] = "INTEGRITY_ONLY_NOT_AUTHORSHIP"
        output.append(payload)
    return output


def projection_generated_at_utc() -> str:
    """Timestamp of display/projection, never passed off as capture time."""
    return datetime.now(timezone.utc).isoformat()
