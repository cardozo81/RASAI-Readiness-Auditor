"""Ed25519 signature anchor regression: no network and no paid provider."""
from __future__ import annotations

import json

import pytest

from rasai.architecture_attestation import (
    SIGNING_KEY, VERIFY_KEY, sign_capture, verify_capture,
)


def _binding():
    return {"version": "m3-artifact-binding-v1", "raw_sha256": "a" * 64,
            "rendered_sha256": "b" * 64, "manifest_attested": False}


def _identity(binding=None):
    return ("AUD-1", "PAGE-1", "SNAP-1", "https://example.org/",
            "https://example.org/", "MOBILE", binding or _binding())


def test_optional_key_does_not_block_independent_audits(monkeypatch):
    monkeypatch.delenv(SIGNING_KEY, raising=False)
    assert sign_capture(*_identity()) is None
    assert verify_capture(*_identity(), None) == "UNSIGNED"


def test_ed25519_signature_uses_external_public_trust_anchor(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    private_path = tmp_path / "private.pem"
    public_path = tmp_path / "trusted-public.pem"
    private_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    public_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    monkeypatch.setenv(SIGNING_KEY, str(private_path))
    monkeypatch.setenv(VERIFY_KEY, str(public_path))

    record = sign_capture(*_identity())
    assert set(record) == {"version", "signature", "key_fingerprint"}
    assert verify_capture(*_identity(), record) == "ATTESTED_ED25519"

    changed = _binding()
    changed["rendered_sha256"] = "c" * 64
    assert verify_capture(*_identity(changed), record) == "SIGNATURE_INVALID"
    assert verify_capture("AUD-OTHER", *_identity()[1:], record) == "SIGNATURE_INVALID"
    monkeypatch.delenv(VERIFY_KEY)
    assert verify_capture(*_identity(), record) == "TRUST_ANCHOR_UNAVAILABLE"
    monkeypatch.setenv(VERIFY_KEY, str(public_path))
    forged = dict(record, key_fingerprint="0" * 64)
    assert verify_capture(*_identity(), forged) == "UNTRUSTED_SIGNER"
    other = Ed25519PrivateKey.generate()
    public_path.write_bytes(other.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    assert verify_capture(*_identity(), record) == "UNTRUSTED_SIGNER"
    assert not any("PRIVATE KEY" in json.dumps(record) for _ in (0,))
