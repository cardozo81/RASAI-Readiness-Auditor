"""Read-only #601 binding of a signed FAQ receipt to persisted M3 DOM bytes.

This module verifies an already supplied, independently signed isolated-action
receipt against the *exact* rendered artifact of one physical AUD snapshot.
Matching identical bytes and URL does NOT prove the collector observed the
same browser session, the historical M3 capture time, a crawler, or indexing.
It does not collect, click, score, write to an AUD, or attest a manifest seal.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.audit_attempt_inspection import _source_fingerprint
from rasai.faq_interaction_receipt import verify_faq_interaction_receipt
from rasai.faq_observation import _MAX_HTML_BYTES, _safe_rendered_file
from rasai.faq_snapshot_scope import _url

_REQUIRED = frozenset({
    "snapshot_id", "page_id", "rendered_artifact_ref",
    "requested_url", "final_url", "device",
})


def inspect_faq_receipt_aud_binding(
    aud_dir: str | Path,
    *,
    audit_id: str,
    page_id: str,
    snapshot_id: str,
    requested_url: str,
    final_url: str,
    device: str,
    before_html: str,
    later_html: str,
    receipt: Mapping[str, Any] | None,
    receipt_mac: str,
    trusted_key: bytes,
    permitted_collector_ids: frozenset[str],
) -> dict[str, Any]:
    """Verify a signed DOM source and match its pre-action bytes to an AUD.

    A byte match means only that this *persisted rendered HTML* agrees with
    the receipt's independently signed pre-action payload. No collector's
    session ID, audit_id, device or snapshot_id is signed by the v1 receipt,
    so physical same-session attestation remains N/D even on success.
    """
    result: dict[str, Any] = {
        "status": "FAQ_AUD_RECEIPT_NOT_LINKED",
        "reason": "SOURCE_OR_RECEIPT_UNVERIFIABLE",
        "persisted_dom_bytes_match_signed_receipt": False,
        "persisted_aud_artifact_independently_attested": False,
        "same_browser_session_verified": False,
        "same_aud_sample_verified": False,
        "crawler_discovery_verified": False,
        "score_change_authorized": False,
        "audit_writes": 0,
        "provider_requests": 0,
    }
    if (
        not all(isinstance(v, str) and v and v == v.strip() for v in (
            audit_id, page_id, snapshot_id, requested_url, final_url, device,
        ))
        or not audit_id.startswith("AUD-")
        or _url(requested_url) != requested_url
        or _url(final_url) != final_url
        or device not in {"MOBILE", "DESKTOP"}
        or not isinstance(receipt, Mapping)
        or receipt.get("document_url") != final_url
        or not isinstance(before_html, str)
        or not isinstance(later_html, str)
    ):
        return result

    signed = verify_faq_interaction_receipt(
        before_html, later_html, receipt=receipt,
        receipt_mac=receipt_mac, trusted_key=trusted_key,
        permitted_collector_ids=permitted_collector_ids,
    )
    if signed["status"] != "ATTESTED_ISOLATED_FAQ_INTERACTION_OBSERVATION":
        return {**result, "reason": "SIGNED_INTERACTION_NOT_ATTESTED"}
    try:
        root = Path(aud_dir)
        db = root / "audit.db"
        if (
            root.name != audit_id or root.is_symlink()
            or not root.is_dir() or db.is_symlink() or not db.is_file()
        ):
            return result
        before_fingerprint = _source_fingerprint(db)
        with sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1.0,
        ) as con:
            con.execute("PRAGMA query_only=ON")
            columns = {row[1] for row in con.execute("PRAGMA table_info(page_snapshots)")}
            if not _REQUIRED.issubset(columns):
                return {**result, "reason": "MISSING_AUD_SNAPSHOT_SCOPE"}
            rows = con.execute(
                "SELECT s.rendered_artifact_ref,s.requested_url,s.final_url,s.device "
                "FROM page_snapshots s JOIN pages p ON p.page_id=s.page_id "
                "WHERE p.audit_id=? AND s.page_id=? AND s.snapshot_id=? LIMIT 2",
                (audit_id, page_id, snapshot_id),
            ).fetchall()
            multiplicity = con.execute(
                "SELECT COUNT(*) FROM page_snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()[0]
        if len(rows) != 1 or multiplicity != 1:
            return {**result, "reason": "MISSING_OR_AMBIGUOUS_SNAPSHOT"}
        ref, captured_requested, captured_final, captured_device = rows[0]
        if (
            captured_requested != requested_url
            or captured_final != final_url
            or not isinstance(captured_device, str)
            or captured_device.strip().upper() != device
        ):
            return {**result, "reason": "URL_OR_DEVICE_SCOPE_MISMATCH"}
        if not isinstance(ref, str) or not ref.startswith("artifacts/rendered/"):
            return {**result, "reason": "INVALID_RENDERED_ARTIFACT_REFERENCE"}
        # No symlink may appear in the stored physical artifact path, even
        # when the ultimate resolved target stays within the AUD directory.
        current = root
        for segment in ref.split("/"):
            if segment in {"", ".", ".."}:
                return {**result, "reason": "INVALID_RENDERED_ARTIFACT_REFERENCE"}
            current = current / segment
            if current.is_symlink():
                return {**result, "reason": "UNSAFE_RENDERED_ARTIFACT"}
        artifact = _safe_rendered_file(root, ref)
        if artifact is None:
            return {**result, "reason": "RENDERED_ARTIFACT_UNVERIFIABLE"}
        stored = artifact.read_bytes()
        if (
            not stored or len(stored) > _MAX_HTML_BYTES
            or stored != before_html.encode("utf-8")
        ):
            return {**result, "reason": "BEFORE_DOM_BYTES_NOT_IN_AUD"}
        if _source_fingerprint(db) != before_fingerprint:
            return {**result, "reason": "AUD_CHANGED_DURING_INSPECTION"}
    except (OSError, sqlite3.Error, ValueError, UnicodeError):
        return {**result, "reason": "UNVERIFIABLE_AUD_PHYSICAL_SOURCE"}
    return {
        **result,
        "status": "SIGNED_RECEIPT_MATCHES_PERSISTED_AUD_DOM_BYTES",
        "reason": "BYTE_IDENTITY_ONLY_NOT_SAME_BROWSER_SESSION",
        "persisted_dom_bytes_match_signed_receipt": True,
        "signed_action_attested_by_trusted_collector": True,
        "audit_id": audit_id,
        "page_id": page_id,
        "snapshot_id": snapshot_id,
        "requested_url": requested_url,
        "final_url": final_url,
        "device": device,
        "before_state": signed["before_state"],
        "later_state": signed["later_state"],
        "text_recoverable_after_action": signed["text_recoverable_after_action"],
    }


__all__ = ["inspect_faq_receipt_aud_binding"]
