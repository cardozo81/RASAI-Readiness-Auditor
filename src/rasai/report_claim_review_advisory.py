"""Opt-in, source-bound documentary claim summary for the executive AUD CLI.

This module does not perform authentication of a regulator or source website:
a reviewer MAC means an approved reviewer attested a *documentary review*,
not that this software certified the insurer, claim or legal compliance.
The authenticated packet is neither a canonical score nor a mutation of AUD.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from typing import Any

from rasai.claim_aud_binding import _ref_file
from rasai.claim_review_batch import inspect_claim_review_batch
from rasai.geo_query_ledger import _audit_digest

CONTRACT = "RASAI-DOCUMENTARY-CLAIMS-ADVISORY-001"
_PROMOTED = frozenset({
    "CLAIM_CORROBORATED", "CLAIM_CONTRADICTED_WITH_VERSIONED_SOURCE",
})
_UNVERIFIED = "CLAIM_UNVERIFIED_EXTERNAL"


def _material_sources_still_sealed(
    audit_directory: Path, claims: list[dict[str, Any]], audit_db_sha: str,
) -> bool:
    """Revalidate physical source bytes *after* the documentary review.

    The batch reader verified the main-content artifacts at one instant.
    A concurrent replacement after that verification must not preserve an
    executive claim of current AUD binding. This does not prove a remote
    document's origin or an adversarially controlled host filesystem.
    """
    db = audit_directory / "audit.db"
    journals = tuple(
        Path(str(db) + suffix) for suffix in ("-wal", "-shm", "-journal")
    )
    if any(p.exists() for p in journals):
        return False
    checked: set[tuple[str, str]] = set()
    for row in claims:
        binding = row.get("audit_binding")
        if (not isinstance(binding, dict)
                or binding.get("status") != "TEXT_PRESENT_IN_SNAPSHOT_MAIN_CONTENT"):
            continue
        reference = binding.get("source_artifact_ref")
        digest = binding.get("main_content_sha256")
        if (not isinstance(reference, str) or not isinstance(digest, str)
                or len(digest) != 64):
            return False
        item = (reference, digest)
        if item in checked:
            continue
        path = _ref_file(audit_directory, reference)
        if path is None:
            return False
        try:
            before = path.stat()
            if not 0 < before.st_size <= 2_000_000:
                return False
            checksum = sha256()
            size = 0
            with path.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(chunk)
                    if size > 2_000_000:
                        return False
                    checksum.update(chunk)
            after = path.stat()
            # The identity comparison includes the opened descriptor, not
            # only two inspections of a potentially replaced pathname.
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            if os.name != "nt":
                fields += ("st_ctime_ns",)
            if (size != before.st_size
                    or any(
                        getattr(candidate, field) != getattr(before, field)
                        for candidate in (opened, after)
                        for field in fields
                    )
                    or _ref_file(audit_directory, reference) != path
                    or checksum.hexdigest() != digest):
                return False
        except (OSError, ValueError):
            return False
        checked.add(item)
    if any(p.exists() for p in journals):
        return False
    latest_sha, _size = _audit_digest(db)
    if any(p.exists() for p in journals):
        return False
    return latest_sha == audit_db_sha


def inspect_documentary_claim_advisory(
    audit_directory: Path, manifest_file: Path, *,
    trusted_key: bytes, trusted_reviewer_ids: frozenset[str],
) -> dict[str, Any]:
    """Review one externally supplied packet against this *same* sealed AUD.

    No fetch, report modification, source text, URL, secret or claim ID output.
    A failed trust boundary is N/D, not zero claims or proven false claims.
    """
    denied: dict[str, Any] = {
        "contract": CONTRACT,
        "status": "NOT_VERIFIABLE",
        "reason": "DOCUMENTARY_PACKET_OR_AUD_BINDING_NOT_ATTESTED",
        "population": "SUBMITTED_CLAIMS_ONLY",
        "official_source_authenticated_by_this_tool": False,
        "legal_or_regulatory_conformity_certified": False,
        "provider_requests": 0,
        "audit_writes": 0,
    }
    if (not isinstance(audit_directory, Path)
            or not isinstance(manifest_file, Path)
            or not isinstance(trusted_key, bytes)
            or len(trusted_key) < 32
            or not isinstance(trusted_reviewer_ids, frozenset)
            or not trusted_reviewer_ids):
        return denied
    try:
        packet = inspect_claim_review_batch(
            manifest_file, trusted_key=trusted_key,
            trusted_reviewer_ids=trusted_reviewer_ids,
            audit_directory=audit_directory,
            require_collection_date=True,
        )
        rows = packet.get("claims")
        if (packet.get("status") != "DOCUMENTARY_REVIEW_BATCH_OBSERVED"
                or packet.get("contract") != "RASAI-CLAIM-REVIEW-BATCH-603-001"
                or packet.get("audit_binding_mode") != "OBSERVATIONAL_BINDING_CHECKED"
                or packet.get("document_collection_date_policy") != "REQUIRED"
                or packet.get("audit_id_operator_label_only") != audit_directory.name
                or packet.get("audit_writes") != 0
                or packet.get("provider_requests") != 0
                or not isinstance(rows, list)
                or not 0 < len(rows) <= 50
                or type(packet.get("claims_total")) is not int
                or packet["claims_total"] != len(rows)):
            return denied
        source_sha, _ = _audit_digest(audit_directory / "audit.db")
        if packet.get("audit_db_sha256") != source_sha:
            return denied
        counts = {"observed": 0, "corroborated": 0,
                  "contradicted": 0, "unverified": 0,
                  "observation_unverified": 0}
        for row in rows:
            if (not isinstance(row, dict)
                    or row.get("regulatory_conformity_attested") is not False
                    or row.get("state") not in _PROMOTED | {_UNVERIFIED}):
                return denied
            binding = row.get("audit_binding")
            is_bound = (isinstance(binding, dict)
                        and binding.get("status")
                        == "TEXT_PRESENT_IN_SNAPSHOT_MAIN_CONTENT")
            observed = row.get("audit_observation_state")
            if (observed not in {"CLAIM_OBSERVED", "NOT_VERIFIED"}
                    or (observed == "CLAIM_OBSERVED") != is_bound):
                return denied
            if is_bound:
                counts["observed"] += 1
            else:
                counts["observation_unverified"] += 1
            state = row["state"]
            if state in _PROMOTED:
                if (not is_bound or row.get("source_version_verified") is not True
                        or binding.get("capture_date_matches_manifest") is not True
                        or not isinstance(row.get("collected_on"), str)
                        or not row["collected_on"]):
                    return denied
                counts["corroborated" if state == "CLAIM_CORROBORATED"
                       else "contradicted"] += 1
            else:
                if row.get("source_version_verified") is not False:
                    return denied
                counts["unverified"] += 1
        if not _material_sources_still_sealed(
            audit_directory, rows, source_sha,
        ):
            return denied
        return {
            "contract": CONTRACT,
            "status": "AUD_BOUND_DOCUMENTARY_REVIEW_OBSERVED",
            "reason": None,
            "population": "SUBMITTED_CLAIMS_ONLY",
            "claims_submitted": len(rows),
            "claims_observed_in_aud": counts["observed"],
            "claims_observation_not_verified": counts["observation_unverified"],
            "claims_reviewed_as_corroborated": counts["corroborated"],
            "claims_reviewed_as_contradicted": counts["contradicted"],
            "claims_without_documentary_verification": counts["unverified"],
            "collection_date_policy": "REQUIRED",
            "audit_db_sha256": source_sha,
            "official_source_authenticated_by_this_tool": False,
            "legal_or_regulatory_conformity_certified": False,
            "provider_requests": 0,
            "audit_writes": 0,
            "caveat": (
                "Apenas alegações submetidas e vinculadas literalmente a snapshots "
                "desta AUD. Recibo HMAC atesta decisão do revisor autorizado, "
                "não autenticidade oficial independente, verdade comercial "
                "nem conformidade SUSEP. Ausência de prova não significa falsidade."
            ),
        }
    except (OSError, ValueError, TypeError, KeyError):
        return denied


__all__ = ["inspect_documentary_claim_advisory", "CONTRACT"]
