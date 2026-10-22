"""Offline, non-billable diagnostic of executive evidence scopes for one AUD.

This CLI prints JSON only and does not invoke any catalog collector, browser,
provider, report writer or scoring engine. Designed for a human smoke using an
already exported sealed AUD, not a new audit.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from rasai.report_decision_matrix import decision_evidence_matrix

_MAX_DB_BYTES = 512 * 1024 * 1024

def inspect_audit_decision_evidence(audit_directory: Path) -> dict[str, Any]:
    fallback: dict[str, Any] = {
        "contract": "RASAI-DECISION-EVIDENCE-604-001",
        "status": "NOT_VERIFIABLE", "audit_id": None,
        "reason": "Fonte SQLite da AUD indisponível ou não selada", "rows": [],
        "provider_requests": 0, "audit_writes": 0,
    }
    try:
        root = Path(audit_directory)
        db = root / "audit.db"
        if (root.is_symlink() or not root.is_dir() or not root.name.startswith("AUD-")
                or db.is_symlink() or not db.is_file()
                or not 0 < db.stat().st_size <= _MAX_DB_BYTES
                or any(Path(str(db) + sidecar).exists()
                       for sidecar in ("-wal", "-shm", "-journal"))):
            return fallback
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2,
        )) as connection:
            connection.execute("PRAGMA query_only=ON")
            connection.row_factory = sqlite3.Row
            from rasai.catalog_report_model import _load_data
            from rasai.catalog_report_metrics import _web_observation
            audit_id = root.name
            data = _load_data(audit_id, db, connection=connection)
            if not data.audit or data.audit.get("audit_id") != audit_id:
                return fallback
            web = _web_observation(db, audit_id, connection=connection)
            # Use the SAME read-only catalog status resolver as index.html.
            # A successful run is not a representative Apdex sample.
            from rasai.catalog_report_catalog_state import _catalog_status
            catalog_statuses = {
                catalog_id: _catalog_status(
                    db, data, catalog_id, connection=connection,
                )[0]
                for catalog_id in ("CAT-06", "CAT-07")
            }
            scores = data.scores
        # Second projection checks its own SQLite sidecar evidence and
        # identities and returns N/D on ambiguous SERP observations.
        from rasai.catalog_report_governance import _overview_serp_depth
        from rasai.optional_seo_interpretation import optional_seo_penalties
        projected = decision_evidence_matrix(
            audit_id=audit_id, scores=scores, web=web,
            catalog_statuses=catalog_statuses,
            serp_depth=_overview_serp_depth(db, audit_id),
            optional_seo_discounts=optional_seo_penalties(db, audit_id),
        )
        return projected
    except (sqlite3.Error, OSError, ValueError, TypeError, OverflowError, KeyError):
        return fallback


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lê limites decisórios persistidos sem novas requisições ou escrita"
    )
    parser.add_argument("audit_directory", type=Path)
    parser.add_argument(
        "--verify-html", action="store_true",
        help="conferir matriz decisória renderizada em HTML e manifesto do relatório",
    )
    parser.add_argument(
        "--claim-review-manifest", type=Path, default=None,
        help="Opt-in: resumo independente de recibos oficiais revisados, "
             "vinculados literalmente a esta AUD e com data de coleta assinada",
    )
    args = parser.parse_args(argv)
    projected = inspect_audit_decision_evidence(args.audit_directory)
    if args.verify_html:
        from rasai.report_decision_html_acceptance import inspect_decision_html_parity
        projected = {
            **projected,
            "html_semantic_gate": inspect_decision_html_parity(
                args.audit_directory, projected,
            ),
        }
    if args.claim_review_manifest is not None:
        from rasai.report_claim_review_advisory import inspect_documentary_claim_advisory
        # Credentials remain exclusively in the trusted process environment,
        # never in the AUD, packet, CLI arguments, JSON output or HTML.
        raw_key = os.environ.get("RASAI_CLAIM_REVIEW_HMAC_KEY_HEX", "")
        try:
            trusted_key = bytes.fromhex(raw_key) if 0 < len(raw_key) <= 128 else b""
        except ValueError:
            trusted_key = b""
        reviewers = frozenset(
            name.strip() for name in
            os.environ.get("RASAI_CLAIM_REVIEWER_ALLOWLIST", "").split(",")
            if name.strip()
        )
        projected = {
            **projected,
            "documentary_claim_advisory": inspect_documentary_claim_advisory(
                args.audit_directory, args.claim_review_manifest,
                trusted_key=trusted_key, trusted_reviewer_ids=reviewers,
            ),
        }
    print(json.dumps(projected, ensure_ascii=False, sort_keys=True))
    return 0 if (
        projected.get("status") == "DESCRIPTIVE_ONLY"
        and (
            not args.verify_html
            or projected["html_semantic_gate"]["status"] == "HTML_MATRIX_PARITY_VERIFIED"
        )
        and (
            args.claim_review_manifest is None
            or projected["documentary_claim_advisory"]["status"]
            == "AUD_BOUND_DOCUMENTARY_REVIEW_OBSERVED"
        )
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["inspect_audit_decision_evidence", "main"]
