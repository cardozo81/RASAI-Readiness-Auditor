"""Single offline #603 acceptance gate; no external source authentication by software.

Consumes only a previously produced private document packet and one existing
AUD. The independent reviewer is responsible for authenticating the actual
primary source and for producing the signed receipt, outside this process.
Results contain counters only, never claims, texts, URLs or credentials.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Sequence

from rasai.claim_review_batch import inspect_claim_review_batch
from rasai.report_claim_review_advisory import inspect_documentary_claim_advisory
from rasai.geo_query_ledger import _audit_digest

_STATUS = "AUTHENTICATED_REVIEW_AND_AUD_LINK_VERIFIED"


def inspect_physical_claim_review_gate(
    audit_directory: Path, manifest_file: Path, *,
    trusted_key: bytes, trusted_reviewer_ids: frozenset[str],
) -> dict[str, Any]:
    """One bounded acceptance check, fail-closed, with redacted output only.

    This attests the stored AUD text and an allowlisted independent reviewer's
    *signed documentary decision*. It cannot certify the actual issuer/portal.
    """
    fallback: dict[str, Any] = {
        "contract": "RASAI-CLAIM-REVIEW-PHYSICAL-GATE-603-001",
        "status": "NOT_VERIFIABLE",
        "reason": "AUD_OR_SIGNED_DOCUMENTARY_PACKET_NOT_ATTESTED",
        "official_source_authenticated_by_this_tool": False,
        "legal_compliance_certified": False,
        "provider_requests": 0,
        "audit_writes": 0,
    }
    if (not isinstance(audit_directory, Path)
            or not isinstance(manifest_file, Path)
            or not isinstance(trusted_key, bytes) or len(trusted_key) < 32
            or not isinstance(trusted_reviewer_ids, frozenset)
            or not trusted_reviewer_ids):
        return fallback
    try:
        source = audit_directory / "audit.db"
        if (audit_directory.is_symlink() or source.is_symlink()
                or not source.is_file()):
            return fallback
        before_sha, before_size = _audit_digest(source)
        reviewed = inspect_claim_review_batch(
            manifest_file, trusted_key=trusted_key,
            trusted_reviewer_ids=trusted_reviewer_ids,
            audit_directory=audit_directory, require_collection_date=True,
        )
        advisory = inspect_documentary_claim_advisory(
            audit_directory, manifest_file, trusted_key=trusted_key,
            trusted_reviewer_ids=trusted_reviewer_ids,
        )
        after_sha, after_size = _audit_digest(source)
        if (before_sha != after_sha or before_size != after_size
                or reviewed.get("status") != "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
                or reviewed.get("audit_binding_mode") != "OBSERVATIONAL_BINDING_CHECKED"
                or reviewed.get("document_collection_date_policy") != "REQUIRED"
                or reviewed.get("audit_db_sha256") != before_sha
                or reviewed.get("provider_requests") != 0
                or reviewed.get("audit_writes") != 0
                or advisory.get("status") != "AUD_BOUND_DOCUMENTARY_REVIEW_OBSERVED"
                or advisory.get("audit_db_sha256") != before_sha
                or advisory.get("provider_requests") != 0
                or advisory.get("audit_writes") != 0):
            return fallback
        n_corroborated = advisory["claims_reviewed_as_corroborated"]
        n_contradicted = advisory["claims_reviewed_as_contradicted"]
        n_observed = advisory["claims_observed_in_aud"]
        n_total = advisory["claims_submitted"]
        if (not all(type(n) is int and 0 <= n <= 50
                    for n in (n_corroborated, n_contradicted, n_observed, n_total))
                or n_corroborated + n_contradicted > n_observed
                or n_total < n_observed):
            return fallback
        promoted = n_corroborated + n_contradicted
        return {
            **fallback,
            "status": (
                _STATUS if promoted else
                "REVIEW_PACKET_OBSERVATIONS_ONLY_NOT_HOMOLOGATED"
            ),
            "reason": (
                None if promoted else "NO_AUTHENTICATED_DOCUMENTARY_DECISION"
            ),
            "submitted_claims": n_total,
            "observed_claims": n_observed,
            "promoted_documentary_decisions": promoted,
            "reviewed_as_corroborated": n_corroborated,
            "reviewed_as_contradicted": n_contradicted,
            "unverified_claims": advisory["claims_without_documentary_verification"],
            "source_aud_integrity_unchanged": True,
            "review_authority_independently_checked_by_software": False,
            "caveat": (
                "Software verifies authenticated review statement and AUD "
                "binding, not whether the reviewer truly authenticated the "
                "issuer/official registry. Separate external acceptance required."
            ),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return fallback


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate focal e offline de comprovantes #603, sem exportar dados privados"
    )
    parser.add_argument("--audit-directory", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    key_str = os.environ.get("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", "")
    try:
        key = bytes.fromhex(key_str) if 64 <= len(key_str) <= 256 else b""
    except ValueError:
        key = b""
    reviewers = frozenset(
        item.strip() for item in
        os.environ.get("RASAI_CLAIM_REVIEWER_ALLOWLIST", "").split(",")
        if item.strip()
    )
    result = inspect_physical_claim_review_gate(
        args.audit_directory, args.manifest,
        trusted_key=key, trusted_reviewer_ids=reviewers,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == _STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
