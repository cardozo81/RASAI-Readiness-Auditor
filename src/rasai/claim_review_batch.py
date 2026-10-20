"""#603: batched, authenticated OFFLINE claim-review projections.

An operator-provided manifest is only a grouping label, not evidence that
claims originated from an AUD, and no JSON, audited website or LLM may supply
the trusted verification key. No file/network writes or report promotion.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from rasai.claim_review_import_cli import (
    _MAX_TEXT, _MAX_DOCUMENT, _MAX_RECEIPT,
    _read_local, _unique_pairs, _nonstandard_number,
)
from rasai.claim_review_receipt import verify_claim_review_receipt
from rasai.claim_aud_binding import bind_claim_texts

_MAX_MANIFEST = 32_768
_MAX_CLAIMS = 50
_FIELDS = frozenset({
    "claim_id", "claim_file", "document_file", "receipt_file", "product_scope",
})
_FIELDS_WITH_SNAPSHOT = _FIELDS | {"snapshot_id"}


def _member_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value or len(value) > 240:
        raise ValueError("invalid local member name")
    relative = Path(value)
    if (relative.is_absolute() or ".." in relative.parts
            or "." in relative.parts or "\x00" in value):
        raise ValueError("unsafe manifest member path")
    path = root / relative
    # Refuse symlinks anywhere below the manifest's trusted root, not only
    # at the final filename; a symlink to another AUD would mix evidence.
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("manifest file path traverses symbolic link")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("manifest member escapes physical directory")
    return path


def _unverified(claim_id: str) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "state": "CLAIM_UNVERIFIED_EXTERNAL",
        "basis": "NO_AUTHENTICATED_REVIEW_RECEIPT",
        "source_version_verified": False,
        "regulatory_conformity_attested": False,
    }


def inspect_claim_review_batch(
    manifest_file: Path,
    *,
    trusted_key: bytes,
    trusted_reviewer_ids: frozenset[str],
    audit_directory: Path | None = None,
) -> dict[str, Any]:
    """Bounded batch of independently authenticated individual source reviews."""
    result: dict[str, Any] = {
        "contract": "RASAI-CLAIM-REVIEW-BATCH-603-001",
        "status": "NOT_VERIFIABLE",
        "reason": "MANIFEST_OR_TRUST_BOUNDARY_UNVERIFIABLE",
        "audit_id_operator_label_only": None,
        "audit_binding_mode": "NOT_REQUESTED",
        "audit_db_sha256": None,
        "claims_total": None,
        "claims": [],
        "provider_requests": 0,
        "audit_writes": 0,
        "legal_compliance_certified": False,
        "source_authenticity_independently_confirmed_by_this_tool": False,
        "caveat": (
            "A manifest AUD ID is a label, not verified AUD physical provenance. "
            "A trusted MAC only attests an external review decision for given "
            "bytes, version, dates and product scope; never SUSEP certification "
            "or an unqualified legal assertion."
        ),
    }
    if (not isinstance(trusted_key, bytes) or len(trusted_key) < 32
            or not isinstance(trusted_reviewer_ids, frozenset)
            or not trusted_reviewer_ids or not isinstance(manifest_file, Path)):
        return result
    try:
        raw = _read_local(manifest_file, limit=_MAX_MANIFEST)
        manifest = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_nonstandard_number,
        )
        if (not isinstance(manifest, dict)
                or set(manifest) != {"audit_id", "at_date", "claims"}
                or not isinstance(manifest["audit_id"], str)
                or not manifest["audit_id"].startswith("AUD-")
                or not isinstance(manifest["claims"], list)
                or not 0 < len(manifest["claims"]) <= _MAX_CLAIMS):
            return result
        reference_date = date.fromisoformat(manifest["at_date"])
        root = manifest_file.parent.resolve()
        seen: set[str] = set()
        for row in manifest["claims"]:
            if (not isinstance(row, dict) or set(row) not in {_FIELDS, _FIELDS_WITH_SNAPSHOT}
                    or not isinstance(row["claim_id"], str)
                    or not row["claim_id"].strip()
                    or len(row["claim_id"]) > 128
                    or row["claim_id"] in seen
                    or not isinstance(row["product_scope"], str)
                    or not row["product_scope"].strip()):
                return result
            seen.add(row["claim_id"])
        # Structurally verified batch; invalid/missing individual evidence
        # abstains locally, never promotes another claim through association.
        entries = []
        observed_claims = []
        for row in manifest["claims"]:
            identity = row["claim_id"]
            fallback = _unverified(identity)
            # Independent from receipt validity, capture literal claim bytes
            # for optional same-AUD read-only binding at the end of the batch.
            observed_claims.append({
                "claim_id": identity,
                "snapshot_id": row.get("snapshot_id"),
                "claim_text": None,
            })
            try:
                claim = _read_local(
                    _member_path(root, row["claim_file"]), limit=_MAX_TEXT,
                ).decode("utf-8")
                source = _read_local(
                    _member_path(root, row["document_file"]), limit=_MAX_DOCUMENT,
                )
                envelope = json.loads(
                    _read_local(
                        _member_path(root, row["receipt_file"]), limit=_MAX_RECEIPT,
                    ).decode("utf-8"),
                    object_pairs_hook=_unique_pairs,
                    parse_constant=_nonstandard_number,
                )
                observed_claims[-1]["claim_text"] = claim
                if (not claim or claim != claim.strip() or not isinstance(envelope, dict)
                        or set(envelope) != {"review", "mac"}
                        or not isinstance(envelope["review"], dict)
                        or not isinstance(envelope["mac"], str)):
                    entries.append(fallback)
                    continue
                reviewed = verify_claim_review_receipt(
                    claim, product_scope=row["product_scope"],
                    at_date=reference_date, primary_bytes=source,
                    receipt=envelope["review"], receipt_mac=envelope["mac"],
                    trusted_key=trusted_key,
                    trusted_reviewer_ids=trusted_reviewer_ids,
                )
                if reviewed["state"] not in {
                    "CLAIM_CORROBORATED",
                    "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE",
                }:
                    entries.append(fallback)
                    continue
                signed = envelope["review"]
                entries.append({
                    **fallback, **reviewed,
                    "source_version_verified": True,
                    "issuer_asserted_by_trusted_reviewer": signed["issuer"],
                    "source_url_attested": signed["source_url"],
                    "document_version": signed["document_version"],
                    "document_sha256": signed["document_sha256"],
                    "reviewer_receipt_id": signed["reviewer_receipt_id"],
                    "product_scope": signed["product_scope"],
                    "effective_from": signed["effective_from"],
                    "effective_until": signed["effective_until"],
                    "collected_on": signed.get("collected_on"),
                    "reviewed_on": signed["reviewed_on"],
                })
            except (OSError, ValueError, TypeError, UnicodeError, KeyError):
                entries.append(fallback)
        binding_mode = "NOT_REQUESTED"
        aud_digest = None
        if audit_directory is not None:
            linked = bind_claim_texts(
                audit_directory, manifest["audit_id"], observed_claims,
            )
            if linked["status"] != "OBSERVATIONAL_BINDING_CHECKED":
                # With opt-in linkage explicitly required, a valid signed
                # claim for some other site is not sufficient proof for
                # this AUD. No ambiguous rows or statuses are promoted.
                return {
                    **result, "reason": "AUD_BINDING_NOT_VERIFIABLE",
                    "audit_binding_mode": "NOT_VERIFIED",
                }
            binding_mode = "OBSERVATIONAL_BINDING_CHECKED"
            aud_digest = linked["source_audit_db_sha256"]
            for claim_entry in entries:
                binding = linked["claims"].get(claim_entry["claim_id"])
                claim_entry["audit_binding"] = binding
                if (not isinstance(binding, Mapping)
                        or binding.get("status")
                        != "TEXT_PRESENT_IN_SNAPSHOT_MAIN_CONTENT"):
                    # The receipt remains an independent documentary fact,
                    # but it cannot be promoted as a review of this AUD.
                    claim_id = claim_entry["claim_id"]
                    claim_entry.clear()
                    claim_entry.update(_unverified(claim_id))
                    claim_entry["basis"] = "AUD_CLAIM_TEXT_BINDING_NOT_PROVEN"
                    claim_entry["audit_binding"] = binding
        return {
            **result, "status": "DOCUMENTARY_REVIEW_BATCH_OBSERVED",
            "reason": None,
            "audit_id_operator_label_only": manifest["audit_id"],
            "audit_binding_mode": binding_mode,
            "audit_db_sha256": aud_digest,
            "claims_total": len(entries), "claims": entries,
        }
    except (OSError, ValueError, TypeError, UnicodeError):
        return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconciliacao offline de revisoes documentais autenticadas"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--format", choices=("json", "html"), default="json")
    parser.add_argument("--audit-directory", type=Path, default=None,
                        help="Opt-in literal claim binding to a physical AUD (offline)")
    args = parser.parse_args(argv)
    try:
        trusted_key = bytes.fromhex(
            os.environ.get("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", "")
        )
    except ValueError:
        trusted_key = b""
    reviewers = frozenset(
        item.strip() for item in
        os.environ.get("RASAI_CLAIM_REVIEWER_ALLOWLIST", "").split(",")
        if item.strip()
    )
    projected = inspect_claim_review_batch(
        args.manifest, trusted_key=trusted_key,
        trusted_reviewer_ids=reviewers,
        audit_directory=args.audit_directory,
    )
    if args.format == "html":
        from rasai.claim_review_batch_html import render_claim_review_batch_html
        print(render_claim_review_batch_html(projected))
    else:
        print(json.dumps(projected, sort_keys=True, ensure_ascii=False))
    return 0 if projected["status"] == "DOCUMENTARY_REVIEW_BATCH_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
