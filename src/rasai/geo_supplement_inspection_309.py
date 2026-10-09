"""#309: read-only GEO supplement lifecycle inventory for sealed AUDs.

Treat externally captured Search API evidence as an independent supplement;
never reinterpret it as an in-AUD GEO v5/v6 snapshot or run a provider.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from rasai.geo_post_audit_complement import list_post_audit_geo_supplements
from rasai.persistence import AuditWorkspace


def inspect_geo_supplements(aud_dir: Path) -> dict:
    aud_dir = Path(aud_dir)
    if aud_dir.is_symlink() or (aud_dir / "audit.db").is_symlink():
        raise ValueError("audit workspace cannot be linked")
    ws = AuditWorkspace.open(aud_dir)
    records = list_post_audit_geo_supplements(ws, audit_id=ws.root.name)
    entries = [
        {
            "intent_id": item.intent_id,
            "status": item.state,
            "query_count": item.query_count,
            "search_type": item.search_type,
            "billability": item.billability,
            # VERIFIED refers to package provenance, not API success.
            "search_status": item.run_status,
            "verified_source_count": item.source_count,
            "search_started_at": item.started_at,
            "search_finished_at": item.finished_at,
            "posthoc_estimated_cost": item.posthoc_estimated_cost,
            "cost_currency": item.cost_currency,
            "pricing_version": item.pricing_version,
            "cost_is_provider_invoice": False,
            "cost_belongs_to_original_audit": False,
            "detail": item.detail,
            "evidence_html": str(item.directory / "supplement.html")
            if item.state == "VERIFIED" else None,
            "main_audit_geo_snapshot": False,
        }
        for item in records
    ]
    return {
        "contract_version": "RASAI-GEO-SUPPLEMENT-LIFECYCLE-INSPECTION-001",
        "audit_id": ws.root.name,
        "total_intents": len(entries),
        "verified": sum(x["status"] == "VERIFIED" for x in entries),
        "verified_successful_searches": sum(
            x["status"] == "VERIFIED" and x["search_status"] == "SUCCESS"
            for x in entries
        ),
        "verified_unsuccessful_searches": sum(
            x["status"] == "VERIFIED" and x["search_status"] != "SUCCESS"
            for x in entries
        ),
        "uncertain": sum(x["status"] == "PENDING_UNCERTAIN" for x in entries),
        "invalid": sum(x["status"] == "INVALID" for x in entries),
        "no_supplements": len(entries) == 0,
        "post_aud_isolated_from_original": True,
        "does_not_imply_generatively_cited": True,
        "verified_means_evidence_integrity_not_search_success": True,
        "excludes_supplement_cost_and_duration_from_original_audit": True,
        "provider_requests": 0,
        "audit_writes": 0,
        "entries": entries,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only, no-charge inspection of independent GEO supplements."
    )
    parser.add_argument("audit_dir", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(
        inspect_geo_supplements(args.audit_dir),
        sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
