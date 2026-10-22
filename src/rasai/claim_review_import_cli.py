"""#603: offline, non-mutating consumer for authenticated documentary receipts.

The trusted reviewer must create/sign the receipt independently. This command
does not access official sites, authenticate the issuer, ingest from AI/URLs,
perform an audit, or change report outcomes or regulatory standing.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
from typing import Any, Sequence

from rasai.claim_review_receipt import verify_claim_review_receipt

_MAX_DOCUMENT = 4_000_000
_MAX_TEXT = 8192
_MAX_RECEIPT = 16384


def _read_local(path: Path, *, limit: int) -> bytes:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise ValueError("source must be an existing regular local file")
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise ValueError("source bytes outside documented limit")
    source = path.read_bytes()
    if len(source) != size:
        raise ValueError("source bytes changed during reading")
    return source


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise ValueError("duplicate review receipt key")
        mapping[key] = value
    return mapping


def _nonstandard_number(value: str) -> None:
    raise ValueError("nonstandard receipt numeric literal")


def inspect_local_claim_receipt(
    *,
    claim_file: Path,
    document_file: Path,
    receipt_file: Path,
    product_scope: str,
    at_date: date,
    trusted_key: bytes,
    trusted_reviewer_ids: frozenset[str],
    require_collection_date: bool = False,
) -> dict[str, Any]:
    """Verify three bounded independent local files, no network or writes."""
    fallback = {
        "state": "CLAIM_UNVERIFIED_EXTERNAL",
        "basis": "NO_AUTHENTICATED_REVIEW_RECEIPT",
        "official_regulator_source_verified": False,
        "legal_compliance_certified": False,
        "file_writes": 0,
        "provider_requests": 0,
    }
    try:
        raw_claim = _read_local(claim_file, limit=_MAX_TEXT)
        claim = raw_claim.decode("utf-8")
        document = _read_local(document_file, limit=_MAX_DOCUMENT)
        raw_receipt = _read_local(receipt_file, limit=_MAX_RECEIPT)
        loaded = json.loads(
            raw_receipt.decode("utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_nonstandard_number,
        )
        if (
            not claim or claim != claim.strip() or not isinstance(loaded, dict)
            or set(loaded) != {"review", "mac"}
            or not isinstance(loaded["review"], dict)
            or not isinstance(loaded["mac"], str)
        ):
            return fallback
    except (OSError, ValueError, UnicodeError, TypeError):
        return fallback
    reviewed = verify_claim_review_receipt(
        claim, product_scope=product_scope, at_date=at_date,
        primary_bytes=document, receipt=loaded["review"],
        receipt_mac=loaded["mac"], trusted_key=trusted_key,
        trusted_reviewer_ids=trusted_reviewer_ids,
        require_collection_date=require_collection_date,
    )
    return {**fallback, **reviewed}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verifica recibo de revisão independente, offline e sem alterações de auditoria",
    )
    parser.add_argument("--claim-file", type=Path, required=True)
    parser.add_argument("--document-file", type=Path, required=True)
    parser.add_argument("--receipt-file", type=Path, required=True)
    parser.add_argument("--product-scope", required=True)
    parser.add_argument("--at-date", required=True)
    parser.add_argument("--require-collection-date", action="store_true",
                        help="Abster sem data de coleta autenticada no recibo")
    args = parser.parse_args(argv)
    # Secret material must originate from a separate trusted operator
    # environment. Never accept signing keys on the CLI or in review JSON.
    try:
        key = bytes.fromhex(
            os.environ.get("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", "")
        )
        verified_date = date.fromisoformat(args.at_date)
    except ValueError:
        key = b""
        verified_date = None
    reviewers = frozenset(
        item.strip() for item in
        os.environ.get("RASAI_CLAIM_REVIEWER_ALLOWLIST", "").split(",")
        if item.strip()
    )
    result = inspect_local_claim_receipt(
        claim_file=args.claim_file,
        document_file=args.document_file,
        receipt_file=args.receipt_file,
        product_scope=args.product_scope,
        at_date=verified_date,
        trusted_key=key,
        trusted_reviewer_ids=reviewers,
        require_collection_date=args.require_collection_date,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
