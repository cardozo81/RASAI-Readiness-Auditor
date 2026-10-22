"""Offline reviewer-owned finalization of an independently reviewed #603 packet.

This utility NEVER decides authenticity or correctness. The independently
authorized reviewer supplies the source, factual assessment and private key.
It cannot download documents, issue a signature without that key, touch an AUD
or replace material already finalized.
"""
from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from rasai.claim_review_receipt import verify_claim_review_receipt
from rasai.claim_review_import_cli import _unique_pairs, _nonstandard_number

_REQUIRED_INPUT = frozenset({
    "source_url", "effective_from", "effective_until", "reviewed_on",
    "collected_on", "product_scope", "document_version", "issuer",
    "reviewer_receipt_id", "reviewer_id", "matched_excerpt",
    "review_decision", "independent_source_authenticity_verified",
})
_MAX_INPUT = 16384
_MAX_DOCUMENT = 4_000_000
_MAX_TEMPLATE = 32768
_AUD_ID = "AUD-EAFBFF6E3F6E415CB0DD41F561B5B2DF"


def _read_stable(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("private reviewer input missing or linked")
    before = path.stat()
    if not 0 < before.st_size <= limit:
        raise ValueError("private reviewer input exceeds size limit")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(limit + 1)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    if (path.is_symlink() or len(raw) != before.st_size
            or any(getattr(value, name) != getattr(before, name)
                   for value in (opened, after) for name in fields)):
        raise ValueError("private reviewer input changed during read")
    return raw


def _json_file(path: Path, limit: int) -> dict[str, Any]:
    try:
        data = json.loads(_read_stable(path, limit).decode("utf-8"),
                          object_pairs_hook=_unique_pairs,
                          parse_constant=_nonstandard_number)
    except (UnicodeError, ValueError, TypeError):
        raise ValueError("private reviewer JSON invalid") from None
    if not isinstance(data, dict):
        raise ValueError("private reviewer JSON object required")
    return data


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def _create_private(path: Path, data: bytes) -> bool:
    """No replacement or modification even for a partially finalized packet."""
    if path.exists() or path.is_symlink():
        if _read_stable(path, len(data)) != data:
            raise ValueError("existing reviewer output differs; no overwrite")
        return False
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return True


def finalize_reviewer_packet(
    private_directory: Path, *, trusted_key: bytes,
    trusted_reviewer_ids: frozenset[str],
    reviewer_confirmed: bool = False,
) -> dict[str, Any]:
    """Prepare signed files only after independent human review of real bytes.

    A MAC proves key possession and integrity of the reviewer declaration,
    not official source authenticity, SUSEP approval or legal compliance.
    """
    base = {
        "status": "PRIVATE_REVIEW_INPUT_REQUIRED",
        "audit_writes": 0, "provider_requests": 0,
        "official_source_authenticated_by_tool": False,
        "legal_compliance_certified": False,
        "reviewer_decision_made_by_tool": False,
        "signed_receipt_created": False,
        "manifest_created": False,
    }
    if not reviewer_confirmed:
        raise ValueError("reviewer confirmation required")
    if (not isinstance(trusted_key, bytes) or len(trusted_key) < 32
            or not trusted_reviewer_ids
            or not isinstance(trusted_reviewer_ids, frozenset)):
        raise ValueError("trusted independent reviewer credentials required")
    root = Path(private_directory)
    if not root.is_dir() or any(part.is_symlink() for part in (root, *root.parents)):
        raise ValueError("private reviewer directory unsafe")
    resolved = root.resolve()
    repo = Path(__file__).resolve().parents[1]
    if (resolved == repo or repo in resolved.parents
            or any(part.name.startswith(("AUD-", "CONS-", "RPR-"))
                   for part in (resolved, *resolved.parents))):
        raise ValueError("reviewer output must be outside Git and sealed packages")
    template = _json_file(root / "manifest.template.json", _MAX_TEMPLATE)
    if (set(template) != {"audit_id", "at_date", "claims"}
            or template["audit_id"] != _AUD_ID
            or template["at_date"] != "2026-10-14"
            or not isinstance(template["claims"], list)
            or len(template["claims"]) != 1):
        raise ValueError("historical review template identity not verified")
    entry = template["claims"][0]
    if (not isinstance(entry, dict)
            or set(entry) != {
                "claim_id", "snapshot_id", "claim_file",
                "document_file", "receipt_file", "product_scope",
            }
            or not isinstance(entry["snapshot_id"], str)
            or not entry["snapshot_id"].startswith("SNP-")
            or entry["claim_file"] != "claim.txt"
            or entry["document_file"] != "conditions.txt"
            or entry["receipt_file"] != "receipt.json"):
        raise ValueError("historical review template members not verified")
    claim = _read_stable(root / "claim.txt", _MAX_INPUT).decode("utf-8")
    primary = _read_stable(root / "conditions.txt", _MAX_DOCUMENT)
    proposed = _json_file(root / "review.authorized.json", _MAX_INPUT)
    if set(proposed) != _REQUIRED_INPUT:
        raise ValueError("authorized review decision fields incomplete")
    reviewer_id = proposed.get("reviewer_id")
    if (not isinstance(reviewer_id, str)
            or reviewer_id not in trusted_reviewer_ids
            or proposed.get("independent_source_authenticity_verified") is not True):
        raise ValueError("reviewer identity/authenticity declaration missing")
    review = {
        **proposed,
        "claim_text": claim,
        "document_sha256": sha256(primary).hexdigest(),
    }
    try:
        at_date = date.fromisoformat(template["at_date"])
        payload = json.dumps(review, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("authorized review serialization invalid") from None
    if len(payload) > _MAX_INPUT:
        raise ValueError("authorized review decision exceeds size limit")
    mac = hmac.new(trusted_key, payload, sha256).hexdigest()
    checked = verify_claim_review_receipt(
        claim, product_scope=review["product_scope"],
        at_date=at_date, primary_bytes=primary,
        receipt=review, receipt_mac=mac,
        trusted_key=trusted_key, trusted_reviewer_ids=trusted_reviewer_ids,
        require_collection_date=True,
    )
    if checked["state"] not in {
        "CLAIM_CORROBORATED", "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE",
    }:
        raise ValueError("authorized source/version/scope/claim review not verifiable")
    # The AUD binding and actual external competence still require the final
    # independent gate; this utility does not turn a declaration into proof.
    manifest = {**template, "claims": [
        {**entry, "product_scope": review["product_scope"]}
    ]}
    signed_bytes = _json_bytes({"review": review, "mac": mac})
    manifest_bytes = _json_bytes(manifest)
    # If output exists and differs, reject BEFORE writing any other output.
    for name, expected in (("receipt.json", signed_bytes),
                           ("manifest.json", manifest_bytes)):
        file = root / name
        if file.exists() or file.is_symlink():
            if _read_stable(file, len(expected)) != expected:
                raise ValueError("existing reviewer packet differs; no overwrite")
    receipt_created = _create_private(root / "receipt.json", signed_bytes)
    try:
        manifest_created = _create_private(root / "manifest.json", manifest_bytes)
    except BaseException:
        if receipt_created:
            (root / "receipt.json").unlink(missing_ok=True)
        raise
    return {
        **base,
        "status": ("PRIVATE_REVIEW_PACKET_FINALIZED"
                   if receipt_created or manifest_created
                   else "PRIVATE_REVIEW_PACKET_REUSED"),
        "signed_receipt_created": receipt_created,
        "manifest_created": manifest_created,
        "review_document_hash_bound": True,
        "review_claim_literal_bound": True,
        "reviewer_receipt_mac_locally_verified": True,
        "final_physical_aud_gate_required": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reviewer-owned OFFLINE signed #603 packet finalizer"
    )
    parser.add_argument("--private-directory", required=True, type=Path)
    parser.add_argument("--reviewer-confirmed", action="store_true",
                        help="Authorized reviewer has authenticated the actual "
                             "official version, dates, scope and literal excerpt")
    args = parser.parse_args(argv)
    try:
        raw = os.environ.get("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", "")
        key = bytes.fromhex(raw) if 64 <= len(raw) <= 256 else b""
        reviewers = frozenset(
            v.strip() for v in
            os.environ.get("RASAI_CLAIM_REVIEWER_ALLOWLIST", "").split(",")
            if v.strip()
        )
        output = finalize_reviewer_packet(
            args.private_directory, trusted_key=key,
            trusted_reviewer_ids=reviewers,
            reviewer_confirmed=args.reviewer_confirmed,
        )
    except (ValueError, TypeError, OSError, UnicodeError):
        print(json.dumps({
            "status": "PRIVATE_REVIEW_PACKET_NOT_FINALIZED",
            "audit_writes": 0, "provider_requests": 0,
            "signed_receipt_created": False, "manifest_created": False,
        }))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
