"""Runtime contract for grouped request-remediation evidence.

The feature module owns normalization, grouping semantics and AI/report behavior. This
module composes the runtime boundary that persists the additive projection and ensures
recurrence denominators are limited to the source populations that actually contributed
to each group.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3
from typing import Any, Iterable, Mapping, Sequence

_INSTALLED = False
_ORIGINAL_GROUPER: Any = None


def group_request_error_evidence(
    events: Sequence[Mapping[str, Any]],
    sample_universe: Iterable[str],
    *,
    audit_id: str = "",
) -> list[dict[str, Any]]:
    """Return deterministic groups with a source-compatible recurrence denominator.

    CAT-06 and CAT-07 are different synthetic populations. A group observed only in
    CAT-07 must therefore use CAT-07 samples as its denominator instead of being diluted
    by unrelated CAT-06 samples. Cross-source groups use the union of the contributing
    source populations.
    """
    from rasai import request_remediation_intelligence as feature

    original = _ORIGINAL_GROUPER or feature.group_request_error_evidence
    groups = original(events, sample_universe, audit_id=audit_id)
    universe = {str(value) for value in sample_universe if str(value)}
    for group in groups:
        members = list(group.get("events", []))
        sources = {
            str(item.get("source_catalog") or "")
            for item in members
            if item.get("source_catalog")
        }
        eligible_universe = {
            sample
            for sample in universe
            if sample.split(":", 1)[0] in sources
        }
        affected = {
            str(item.get("sample_key") or "")
            for item in members
            if item.get("sample_key")
        }
        total = len(eligible_universe)
        ratio = (len(affected) / total) if total else 0.0
        group["total_sample_count"] = total
        group["affected_sample_count"] = len(affected)
        group["recurrence_ratio"] = ratio
        group["recurrence_class"] = feature._recurrence_class(ratio)
    return sorted(
        groups,
        key=lambda item: (
            -float(item.get("recurrence_ratio") or 0.0),
            -int(item.get("affected_sample_count") or 0),
            -int(item.get("occurrence_count") or 0),
            str(item.get("title") or ""),
        ),
    )


def persist_request_remediation_groups(
    database: Any,
    audit_id: str,
    groups: Sequence[Mapping[str, Any]],
) -> None:
    """Persist the deterministic projection using explicit column contracts."""
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
    global _INSTALLED, _ORIGINAL_GROUPER
    if _INSTALLED:
        return
    from rasai import request_remediation_intelligence as feature

    if not getattr(feature.group_request_error_evidence, "_rasai_source_population_denominator", False):
        _ORIGINAL_GROUPER = feature.group_request_error_evidence
        group_request_error_evidence._rasai_source_population_denominator = True
        group_request_error_evidence._rasai_original = _ORIGINAL_GROUPER
        feature.group_request_error_evidence = group_request_error_evidence
    feature.persist_request_remediation_groups = persist_request_remediation_groups
    _INSTALLED = True


__all__ = [
    "group_request_error_evidence",
    "persist_request_remediation_groups",
    "install",
]
