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


def test_signature_stripping_is_not_accepted_with_trust_anchor(tmp_path, monkeypatch):
    """A valid digest alone cannot replace an intentionally required signature."""
    import sqlite3
    from rasai.architecture_m6_evidence import read_audit_architecture_observations
    directory = tmp_path / "AUD-SIGNED"
    (directory / "artifacts").mkdir(parents=True)
    raw = directory / "artifacts" / "raw.html"
    rendered = directory / "artifacts" / "rendered.html"
    raw.write_bytes(b"raw")
    rendered.write_bytes(b"rendered")
    from rasai.architecture_m6_evidence import capture_artifact_binding
    binding = capture_artifact_binding(directory, "artifacts/raw.html",
                                       "artifacts/rendered.html")
    with sqlite3.connect(directory / "audit.db") as conn:
        conn.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        conn.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,"
            "final_url TEXT, architecture_classification TEXT,"
            "raw_artifact_ref TEXT, rendered_artifact_ref TEXT, browser_metadata TEXT)"
        )
        conn.execute("INSERT INTO pages VALUES ('P-1','AUD-SIGNED')")
        conn.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                     ("S-1", "P-1", "MOBILE", "https://example.org/",
                      "https://example.org/", "HYDRATED",
                      "artifacts/raw.html", "artifacts/rendered.html",
                      json.dumps({"architecture_artifact_binding": binding})))
    assert len(read_audit_architecture_observations(tmp_path, "AUD-SIGNED")) == 1
    monkeypatch.setenv(VERIFY_KEY, str(tmp_path / "operator-public.pem"))
    assert read_audit_architecture_observations(tmp_path, "AUD-SIGNED") == ()


def test_signed_m6_evidence_is_verifiable_end_to_end(tmp_path, monkeypatch):
    """Signed canonical snapshot works; physical tampering causes advisory abstention."""
    pytest.importorskip("cryptography")
    import sqlite3
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from rasai.architecture_m6_evidence import (
        capture_artifact_binding, read_audit_architecture_observations,
    )

    workspace = tmp_path / "AUD-ATTEST"
    (workspace / "artifacts").mkdir(parents=True)
    raw = workspace / "artifacts" / "raw.html"
    rendered = workspace / "artifacts" / "rendered.html"
    raw.write_bytes(b"<main>server</main>")
    rendered.write_bytes(b"<main>browser</main>")

    key = Ed25519PrivateKey.generate()
    private_path, public_path = tmp_path / "private.pem", tmp_path / "public.pem"
    private_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    public_path.write_bytes(key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    monkeypatch.setenv(SIGNING_KEY, str(private_path))
    monkeypatch.setenv(VERIFY_KEY, str(public_path))

    binding = capture_artifact_binding(
        workspace, "artifacts/raw.html", "artifacts/rendered.html",
    )
    identity = ("AUD-ATTEST", "P-1", "S-1", "https://example.org/",
                "https://example.org/", "MOBILE", binding)
    attestation = sign_capture(*identity)
    assert verify_capture(*identity, attestation) == "ATTESTED_ED25519"

    with sqlite3.connect(workspace / "audit.db") as conn:
        conn.execute("CREATE TABLE pages(page_id TEXT, audit_id TEXT)")
        conn.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT, page_id TEXT, device TEXT, requested_url TEXT,"
            "final_url TEXT, architecture_classification TEXT,"
            "raw_artifact_ref TEXT, rendered_artifact_ref TEXT, browser_metadata TEXT)"
        )
        conn.execute("INSERT INTO pages VALUES ('P-1','AUD-ATTEST')")
        conn.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
                     ("S-1", "P-1", "MOBILE", "https://example.org/",
                      "https://example.org/", "HYDRATED",
                      "artifacts/raw.html", "artifacts/rendered.html",
                      json.dumps({"architecture_artifact_binding": binding,
                                  "architecture_attestation": attestation})))
    assert len(read_audit_architecture_observations(tmp_path, "AUD-ATTEST")) == 1
    rendered.write_bytes(b"<main>tampered</main>")
    assert read_audit_architecture_observations(tmp_path, "AUD-ATTEST") == ()
