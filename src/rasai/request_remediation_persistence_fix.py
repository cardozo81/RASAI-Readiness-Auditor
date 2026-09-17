"""Narrow persistence correction for request-remediation grouping.

Kept separate so the additive feature can be corrected without touching canonical audit
schemas. It replaces only the group/evidence writer; all grouping semantics stay in
request_remediation_intelligence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3
from typing import Any, Mapping, Sequence

_INSTALLED = False


def persist_request_remediation_groups(
    database: Any,
    audit_id: str,
    groups: Sequence[Mapping[str, Any]],
) -> None:
    from rasai import request_remediation_intelligence as feature

    connection = sqlite3.connect(database)
    try:
        feature._ensure_schema(connection)
        now = datetime.now(timezone.utc).isoformat()
        current_ids = {str(group["group_id"]) for group in groups}
        with connection:
            connection.execute("DELETE FROM request_remediation_evidence WHERE audit_id=?", (audit_id,))
            connection.execute("DELETE FROM request_remediation_groups WHERE audit_id=?", (audit_id,))
            for group in groups:
                connection.execute(
                    """
                    INSERT INTO request_remediation_groups (
                        group_id,audit_id,family,party_scope,title,occurrence_count,problem_count,
                        affected_sample_count,total_sample_count,recurrence_ratio,recurrence_class,
                        source_catalogs_json,resource_urls_json,http_statuses_json,error_types_json,
                        observed_impacts_json,potential_impacts_json,public_reference_label,
                        public_reference_url,evidence_fingerprint,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        group["group_id"], audit_id, group["family"], group["party_scope"], group["title"],
                        group["occurrence_count"], group["problem_count"], group["affected_sample_count"],
                        group["total_sample_count"], group["recurrence_ratio"], group["recurrence_class"],
                        json.dumps(group["source_catalogs"], ensure_ascii=False),
                        json.dumps(group["resource_urls"], ensure_ascii=False),
                        json.dumps(group["http_statuses"], ensure_ascii=False),
                        json.dumps(group["error_types"], ensure_ascii=False),
                        json.dumps(group["observed_impacts"], ensure_ascii=False),
                        json.dumps(group["potential_impacts"], ensure_ascii=False),
                        group["public_reference_label"], group["public_reference_url"],
                        group["evidence_fingerprint"], now,
                    ),
                )
                for sequence, event in enumerate(group.get("events", []), 1):
                    basis = "|".join(
                        (
                            str(group["group_id"]),
                            str(event.get("sample_key") or ""),
                            str(sequence),
                            feature._problem_signature(event),
                        )
                    )
                    evidence_id = "REQE-" + sha256(basis.encode("utf-8")).hexdigest()[:18].upper()
                    first_party = event.get("first_party")
                    connection.execute(
                        """
                        INSERT INTO request_remediation_evidence (
                            evidence_id,group_id,audit_id,source_catalog,source_kind,sample_key,
                            sample_id,run_index,device,error_type,source_url,normalized_url,first_party,
                            http_status,resource_type,message,error_forced_frustrated,captured_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            evidence_id, group["group_id"], audit_id, event.get("source_catalog") or "—",
                            event.get("source_kind") or "—", event.get("sample_key") or "—", event.get("sample_id"),
                            event.get("run_index"), event.get("device"), event.get("error_type") or "UNKNOWN",
                            event.get("source_url"), event.get("normalized_url"),
                            None if first_party is None else int(bool(first_party)), event.get("http_status"),
                            event.get("resource_type"), str(event.get("message") or "")[:2000] or None,
                            int(bool(event.get("error_forced_frustrated"))), event.get("captured_at"),
                        ),
                    )
            if current_ids:
                placeholders = ",".join("?" for _ in current_ids)
                connection.execute(
                    f"DELETE FROM request_remediation_ai WHERE audit_id=? AND group_id NOT IN ({placeholders})",
                    (audit_id, *sorted(current_ids)),
                )
            else:
                connection.execute("DELETE FROM request_remediation_ai WHERE audit_id=?", (audit_id,))
    finally:
        connection.close()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import request_remediation_intelligence as feature

    feature.persist_request_remediation_groups = persist_request_remediation_groups
    _INSTALLED = True


__all__ = ["persist_request_remediation_groups", "install"]
