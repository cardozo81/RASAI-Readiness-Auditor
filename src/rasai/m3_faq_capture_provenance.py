"""Worker-origin #652 M3 capture provenance, independent of FAQ collector HMAC.

The trusted M3 renderer signs a fresh cross-check *after* the observer returned,
using a short-lived Ed25519 key that is never exposed to the page or collector
callback. The public verification record is persisted in canonical M3 metadata,
not in a post-seal sidecar. The sealed AUD and a separate FAQ collector MAC are
both required by the caller. This is software-process provenance, not hardware,
OS egress, Googlebot or third-party identity attestation.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from rasai.audit_attempt_inspection import _source_fingerprint

_VERSION = "RASAI-M3-FAQ-CHROMIUM-CAPTURE-001"
_KEYS = ("audit_id", "page_id", "snapshot_id", "requested_url", "final_url", "device")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sign_worker_capture(
    *, scope: Mapping[str, str], nonce: str,
    before_sha256: str, after_sha256: str,
    navigation_started_ns: int, observed_ns: int,
    same_page_context: bool,
) -> dict[str, Any]:
    """Only call in M3 renderer after independently re-reading the live page.

    The context and page identity predicate is calculated by M3, never copied
    from the observer's claimed status. The key does not leave this call.
    """
    if (
        set(scope) != set(_KEYS)
        or not all(isinstance(scope[k], str) and scope[k] for k in _KEYS)
        or not isinstance(nonce, str) or not _NONCE.fullmatch(nonce)
        or not all(isinstance(x, str) and _HEX64.fullmatch(x)
                   for x in (before_sha256, after_sha256))
        or type(navigation_started_ns) is not int or navigation_started_ns <= 0
        or type(observed_ns) is not int
        or not navigation_started_ns <= observed_ns <= navigation_started_ns + 60_000_000_000
        or same_page_context is not True
    ):
        raise ValueError("unverifiable worker-origin M3 same-page capture")
    payload = {
        "version": _VERSION, "scope": dict(scope), "capture_nonce": nonce,
        "canonical_before_sha256": before_sha256,
        "worker_after_sha256": after_sha256,
        "navigation_started_monotonic_ns": navigation_started_ns,
        "worker_observed_monotonic_ns": observed_ns,
        "same_page_context_verified_by_m3": True,
        "advisory_only": True,
        "crawler_discovery_verified": False,
        "score_change_authorized": False,
    }
    # The attestation extra is opt-in. Legacy read-only FAQ consumers must
    # import this module successfully even without cryptography installed.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization

    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "payload": payload,
        "public_key_b64": base64.b64encode(public).decode("ascii"),
        "signature_b64": base64.b64encode(key.sign(_canonical(payload))).decode("ascii"),
    }


def verify_worker_capture(
    record: Any, *, scope: Mapping[str, str],
    before_sha256: str, after_sha256: str,
) -> bool:
    """Independently verify the signed worker claim and exact AUD/FAQ scope.

    Its public key is session-local. Authenticity ultimately depends on the
    already verified AUD seal and trusted worker, not on a global PKI anchor.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        # An unsigned default install must safely abstain; it must not make
        # the canonical M3 snapshot, existing FAQ readers or reports crash.
        return False
    try:
        if not isinstance(record, dict) or set(record) != {
            "payload", "public_key_b64", "signature_b64",
        }:
            return False
        payload = record["payload"]
        if not isinstance(payload, dict) or set(payload) != {
            "version", "scope", "capture_nonce", "canonical_before_sha256",
            "worker_after_sha256", "navigation_started_monotonic_ns",
            "worker_observed_monotonic_ns", "same_page_context_verified_by_m3",
            "advisory_only", "crawler_discovery_verified", "score_change_authorized",
        }:
            return False
        if (
            payload["version"] != _VERSION
            or set(payload["scope"]) != set(_KEYS)
            or payload["scope"] != {k: scope[k] for k in _KEYS}
            or not _NONCE.fullmatch(payload["capture_nonce"])
            or payload["canonical_before_sha256"] != before_sha256
            or payload["worker_after_sha256"] != after_sha256
            or not _HEX64.fullmatch(before_sha256)
            or not _HEX64.fullmatch(after_sha256)
            or payload["same_page_context_verified_by_m3"] is not True
            or payload["advisory_only"] is not True
            or payload["crawler_discovery_verified"] is not False
            or payload["score_change_authorized"] is not False
            or type(payload["navigation_started_monotonic_ns"]) is not int
            or type(payload["worker_observed_monotonic_ns"]) is not int
            or not 0 < payload["navigation_started_monotonic_ns"]
                <= payload["worker_observed_monotonic_ns"]
                <= payload["navigation_started_monotonic_ns"] + 60_000_000_000
        ):
            return False
        public = base64.b64decode(record["public_key_b64"], validate=True)
        signature = base64.b64decode(record["signature_b64"], validate=True)
        if len(public) != 32 or len(signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(public).verify(signature, _canonical(payload))
        return True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError, InvalidSignature):
        return False


def inspect_persisted_worker_capture(
    aud_dir: str | Path, *, scope: Mapping[str, str],
    before_sha256: str, after_sha256: str,
) -> bool:
    """Independent read-only inspection of a M3-produced canonical snapshot.

    Caller must first verify the AUD manifest and link the FAQ receipt to the
    exact canonical rendered artifact. No writes, no page navigation.
    """
    try:
        root = Path(aud_dir)
        if root.is_symlink() or root.name != scope["audit_id"]:
            return False
        db = root / "audit.db"
        if db.is_symlink() or not db.is_file():
            return False
        start = _source_fingerprint(db)
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1",
                             uri=True, timeout=1) as con:
            con.execute("PRAGMA query_only=ON")
            rows = con.execute(
                "SELECT s.browser_metadata FROM page_snapshots s "
                "JOIN pages p ON p.page_id=s.page_id "
                "WHERE p.audit_id=? AND s.page_id=? AND s.snapshot_id=? LIMIT 2",
                (scope["audit_id"], scope["page_id"], scope["snapshot_id"]),
            ).fetchall()
            count = con.execute(
                "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?",
                (scope["snapshot_id"],),
            ).fetchone()[0]
        if len(rows) != 1 or count != 1 or not isinstance(rows[0][0], str):
            return False
        metadata = json.loads(rows[0][0])
        if not isinstance(metadata, dict):
            return False
        record = metadata.get("experimental_faq_m3_worker_provenance")
        return _source_fingerprint(db) == start and verify_worker_capture(
            record, scope=scope, before_sha256=before_sha256,
            after_sha256=after_sha256,
        )
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error,
            UnicodeError, json.JSONDecodeError):
        return False


__all__ = ["sign_worker_capture", "verify_worker_capture",
           "inspect_persisted_worker_capture"]
