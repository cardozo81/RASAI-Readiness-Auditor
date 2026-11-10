"""Consume the physical ledger; never upgrade query alignment to contextual proof."""
from contextlib import closing
import sqlite3

from rasai.geo_observation import _canonical_url
from rasai.geo_query_ledger import inspect_geo_per_query, _utc, _audit_digest
from rasai.geo_search_alignment import geo_query_alignment
from rasai.geo_temporal_provenance import _last_temporally_verified, _UNVERIFIABLE


def correlate_persisted(root, captures):
    ledger = inspect_geo_per_query(root)
    result = dict(contract="contextual-search-v1", audit_id=root.name, status="NOT_COMPARABLE",
        reason=ledger["reason"], source_audit_db_sha256=ledger["source_audit_db_sha256"],
        observations=[], limitations=["SEARCH_API_NOT_GENERATIVE_CITATION", "NO_CAUSALITY_OR_RANKING_PROVEN",
            "EXTERNAL_MARKET_LANGUAGE_DEVICE_EQUIVALENCE_NOT_PERSISTED"], provider_calls=0)
    if ledger["source_audit_db_integrity_guard"] != "DOUBLE_SHA256_MATCH":
        return result
    with closing(sqlite3.connect((root / "audit.db").as_uri() + "?mode=ro&immutable=1", uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        selected = _last_temporally_verified(con, table="perplexity_search_runs", audit_id=root.name,
                    columns=("run_id", "started_at"), time_column="started_at")
        if selected is None or selected is _UNVERIFIABLE:
            result["reason"] = "EXTERNAL_RUN_CHRONOLOGY_ND"
            return result
        run_id, _ = selected
        for row in ledger["queries"]:
            item = dict(query=row["query"], status="NOT_COMPARABLE", reason=row["reason"],
                alignment=None, source_run_ids=[run_id], evidence_ids=[], local_references=[],
                timestamps=dict(serp=row["serp_collected_at"], external=row["external_run_started_at"]),
                serp_scope=row["serp_scope"], exact_url_observations=[],
                limitations=list(result["limitations"]), sufficiency="INSUFICIENTE")
            if row["status"] != "DESCRIPTIVE_ONLY":
                result["observations"].append(item)
                continue
            sid = row["serp_observation_id"]
            item["evidence_ids"] = [sid]
            item["alignment"] = geo_query_alignment([row["query"]], [row["query"]])
            # Retain only exact URLs, never convert host overlap to a page match.
            urls = {_canonical_url(r[0]) for r in con.execute(
                "SELECT url FROM serp_results WHERE observation_id=? LIMIT 501", (sid,))}
            for capture in captures:
                if capture.get("audit_id") != root.name:
                    item["limitations"].append("FOREIGN_CAPTURE_NOT_CORRELATED")
                    continue
                reasons = []
                clock, observed = _utc(capture["captured_at"]), _utc(row["serp_collected_at"])
                if clock is None or observed is None or abs((clock - observed).total_seconds()) > 86400:
                    reasons.append("CAPTURE_SEARCH_WINDOW_MISMATCH_ND")
                if capture["device"].casefold() != row["serp_scope"]["device"].casefold():
                    reasons.append("CAPTURE_SERP_DEVICE_MISMATCH_ND")
                page_url = _canonical_url(capture["final_url_observed"] or capture["requested_url"])
                refs = [o["occurrence_id"] for o in capture["occurrences"]
                        if o["category"] not in {"NAVIGATION", "FOOTER", "SOCIAL", "UNKNOWN"}]
                if not refs:
                    reasons.append("NO_LOCAL_CONTEXT_EVIDENCE_ND")
                item["local_references"].append(dict(snapshot_id=capture["snapshot_id"],
                    evidence_ids=refs, source_ref=capture["source_ref"], source_sha256=capture["source_sha256"],
                    exact_page_url_in_serp=page_url in urls if page_url else None,
                    contextual_status="NOT_COMPARABLE", reasons=reasons + [
                        "EXTERNAL_CONTEXT_EQUIVALENCE_UNPROVEN", "LOCAL_QUERY_INTENT_LINK_UNPROVEN"]))
            # The ledger's URL populations are descriptive only. No comparable
            # contextual claim or opportunity can be derived from these counts.
            item.update(status="DESCRIPTIVE_ONLY", reason="EXTERNAL_CONTEXT_EQUIVALENCE_UNPROVEN",
                sufficiency="PARCIAL", exact_url_observations=[dict(
                    serp_distinct_urls=row["serp_distinct_urls"],
                    external_distinct_urls=row["perplexity_distinct_urls"], common_urls=row["common_urls"])])
            result["observations"].append(item)
    if _audit_digest(root / "audit.db")[0] != result["source_audit_db_sha256"]:
        result.update(reason="SOURCE_CHANGED_DURING_CONTEXTUAL_READ_ND", observations=[])
        return result
    if any(r["status"] == "DESCRIPTIVE_ONLY" for r in result["observations"]):
        result["reason"] = "EXTERNAL_CONTEXT_EQUIVALENCE_UNPROVEN"
    return result
