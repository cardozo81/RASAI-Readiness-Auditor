"""Operator-controlled Ed25519 signatures for canonical M3 artifact bindings.

Private keys never enter audit data. Signature records remain untrusted until
validated against an independently configured public key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re

SIGNING_KEY = "RASAI_ARCHITECTURE_SIGNING_KEY_FILE"
VERIFY_KEY = "RASAI_ARCHITECTURE_VERIFY_KEY_FILE"
VERSION = "architecture-ed25519-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _payload(audit_id: str, page_id: str, snapshot_id: str,
             requested_url: str, final_url: str, device: str,
             binding: dict[str, object]) -> dict[str, object]:
    if binding.get("version") != "m3-artifact-binding-v1":
        raise ValueError("Invalid artifact binding contract")
    raw = binding.get("raw_sha256")
    rendered = binding.get("rendered_sha256")
    if not (isinstance(raw, str) and _SHA256.fullmatch(raw)
            and isinstance(rendered, str) and _SHA256.fullmatch(rendered)):
        raise ValueError("Both canonical artifacts are required for signed architecture")
    if not all(isinstance(value, str) and value.strip() for value in (
        audit_id, page_id, snapshot_id, requested_url, final_url, device,
    )):
        raise ValueError("Missing physical capture identity")
    return {
        "contract_version": VERSION, "audit_id": audit_id,
        "page_id": page_id, "snapshot_id": snapshot_id,
        "requested_url": requested_url, "final_url": final_url,
        "device": device, "raw_sha256": raw, "rendered_sha256": rendered,
    }


def sign_capture(audit_id: str, page_id: str, snapshot_id: str,
                 requested_url: str, final_url: str, device: str,
                 binding: dict[str, object]) -> dict[str, str] | None:
    """Produce a portable signature only when operator opted into a private key.

    The public verifier is always separately configured; never trust a public
    key embedded in the signature record.
    """
    key_file = os.environ.get(SIGNING_KEY)
    if not key_file:
        return None
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    key = serialization.load_pem_private_key(Path(key_file).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Only Ed25519 private keys are supported")
    payload = _payload(audit_id, page_id, snapshot_id, requested_url, final_url, device, binding)
    signature = key.sign(_canonical(payload))
    public = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    return {
        "version": VERSION,
        "signature": base64.b64encode(signature).decode("ascii"),
        "key_fingerprint": hashlib.sha256(public).hexdigest(),
    }


def verify_capture(audit_id: str, page_id: str, snapshot_id: str,
                   requested_url: str, final_url: str, device: str,
                   binding: dict[str, object], record: object) -> str:
    """Fail closed unless an external operator-configured public key verifies."""
    if record is None:
        return "UNSIGNED"
    if not isinstance(record, dict) or set(record) != {
        "version", "signature", "key_fingerprint",
    } or record.get("version") != VERSION:
        return "SIGNATURE_INVALID"
    if not os.environ.get(VERIFY_KEY):
        return "TRUST_ANCHOR_UNAVAILABLE"
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
        public = serialization.load_pem_public_key(Path(os.environ[VERIFY_KEY]).read_bytes())
        if not isinstance(public, Ed25519PublicKey):
            return "TRUST_ANCHOR_INVALID"
        fingerprint = hashlib.sha256(public.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw,
        )).hexdigest()
        if fingerprint != record["key_fingerprint"]:
            return "UNTRUSTED_SIGNER"
        signature = base64.b64decode(record["signature"], validate=True)
        if len(signature) != 64:
            return "SIGNATURE_INVALID"
        payload = _payload(audit_id, page_id, snapshot_id, requested_url,
                           final_url, device, binding)
        public.verify(signature, _canonical(payload))
    except (OSError, ValueError, TypeError, KeyError, InvalidSignature):
        return "SIGNATURE_INVALID"
    return "ATTESTED_ED25519"
