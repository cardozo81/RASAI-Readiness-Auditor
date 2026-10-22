"""#601: signed FAQ receipt bound to exact persisted AUD DOM bytes, offline."""
from __future__ import annotations

import hmac
from hashlib import sha256
import json
import sqlite3

import pytest

from rasai.faq_aud_receipt_binding import inspect_faq_receipt_aud_binding


_BEFORE = (
    '<button type="button" aria-controls="faq-answer" '
    'aria-expanded="false">Q</button>'
)
_AFTER = (
    '<button type="button" aria-controls="faq-answer" '
    'aria-expanded="true">Q</button>'
    '<div id="faq-answer">Answer after opt-in</div>'
)
_KEY = b"offline-faq-aud-binding-collector-trust-key-01"
_URL = "https://example.test/faq"


def _receipt():
    value = {
        "receipt_id": "TEST-601-BINDING",
        "collector_id": "TEST-ISOLATED-COLLECTOR",
        "target_id": "faq-answer",
        "document_url": _URL,
        "before_sha256": sha256(_BEFORE.encode()).hexdigest(),
        "after_sha256": sha256(_AFTER.encode()).hexdigest(),
        "before_utc": "2026-10-14T20:00:00Z",
        "after_utc": "2026-10-14T20:00:01Z",
        "action": "FAQ_DISCLOSURE_BUTTON_CLICK",
        "target_opt_in": True,
        "isolated_unauthenticated_context": True,
        "network_blocked_after_load": True,
    }
    signed = json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode()
    return value, hmac.new(_KEY, signed, sha256).hexdigest()


def _fixture(tmp_path):
    root = tmp_path / "AUD-FAQ-PHYSICAL"
    artifact = root / "artifacts/rendered/page.html"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(_BEFORE, encoding="utf-8")
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,rendered_artifact_ref TEXT,"
            "requested_url TEXT,final_url TEXT,device TEXT);"
        )
        con.execute("INSERT INTO pages VALUES (?,?)", ("PAGE-1", root.name))
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-1", "PAGE-1", "artifacts/rendered/page.html",
             _URL, _URL, "mobile"),
        )
    return root, artifact


def _check(root, **overrides):
    receipt, mac = _receipt()
    payload = {
        "audit_id": root.name,
        "page_id": "PAGE-1",
        "snapshot_id": "SNP-1",
        "requested_url": _URL,
        "final_url": _URL,
        "device": "MOBILE",
        "before_html": _BEFORE,
        "later_html": _AFTER,
        "receipt": receipt,
        "receipt_mac": mac,
        "trusted_key": _KEY,
        "permitted_collector_ids": frozenset({"TEST-ISOLATED-COLLECTOR"}),
    }
    payload.update(overrides)
    return inspect_faq_receipt_aud_binding(root, **payload)


def test_601_signed_receipt_matches_persisted_aud_dom_without_claiming_same_session(
    tmp_path,
):
    root, artifact = _fixture(tmp_path)
    original_db = (root / "audit.db").read_bytes()
    original_dom = artifact.read_bytes()
    result = _check(root)
    assert result["status"] == "SIGNED_RECEIPT_MATCHES_PERSISTED_AUD_DOM_BYTES"
    assert result["persisted_dom_bytes_match_signed_receipt"] is True
    assert result["signed_action_attested_by_trusted_collector"] is True
    assert result["same_browser_session_verified"] is False
    assert result["same_aud_sample_verified"] is False
    assert result["persisted_aud_artifact_independently_attested"] is False
    assert result["text_recoverable_after_action"] is True
    assert result["crawler_discovery_verified"] is False
    assert result["score_change_authorized"] is False
    assert result["audit_writes"] == result["provider_requests"] == 0
    assert (root / "audit.db").read_bytes() == original_db
    assert artifact.read_bytes() == original_dom


@pytest.mark.parametrize("override", [
    {"snapshot_id": "SNP-OTHER"},
    {"page_id": "PAGE-OTHER"},
    {"requested_url": "https://another.test/faq"},
    {"final_url": "https://another.test/faq"},
    {"device": "DESKTOP"},
    {"audit_id": "AUD-OTHER"},
    {"receipt_mac": "0" * 64},
    {"before_html": _BEFORE + " "},
])
def test_601_changed_identity_or_mac_or_dom_never_links(tmp_path, override):
    root, _ = _fixture(tmp_path)
    result = _check(root, **override)
    assert result["status"] == "FAQ_AUD_RECEIPT_NOT_LINKED"
    assert result["persisted_dom_bytes_match_signed_receipt"] is False
    assert result["same_browser_session_verified"] is False


def test_601_matching_receipt_does_not_hide_changed_persisted_html(tmp_path):
    root, artifact = _fixture(tmp_path)
    artifact.write_text(_BEFORE + "<footer>modified</footer>", encoding="utf-8")
    result = _check(root)
    assert result["status"] == "FAQ_AUD_RECEIPT_NOT_LINKED"
    assert result["reason"] == "BEFORE_DOM_BYTES_NOT_IN_AUD"


def test_601_duplicated_snapshot_id_in_another_aud_is_not_attributable(tmp_path):
    root, _ = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("INSERT INTO pages VALUES ('PAGE-OTHER','AUD-OTHER')")
        con.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?)",
            ("SNP-1", "PAGE-OTHER", "artifacts/rendered/other.html",
             _URL, _URL, "mobile"),
        )
    result = _check(root)
    assert result["reason"] == "MISSING_OR_AMBIGUOUS_SNAPSHOT"


def test_601_uncheckpointed_sqlite_is_not_valid_physical_evidence(tmp_path):
    root, _ = _fixture(tmp_path)
    (root / "audit.db-wal").write_bytes(b"pending")
    result = _check(root)
    assert result["status"] == "FAQ_AUD_RECEIPT_NOT_LINKED"
    assert result["reason"] == "UNVERIFIABLE_AUD_PHYSICAL_SOURCE"


def test_601_rendered_artifact_symlink_is_not_followed(tmp_path):
    root, artifact = _fixture(tmp_path)
    alternate = root / "other.html"
    alternate.write_text(_BEFORE, encoding="utf-8")
    artifact.unlink()
    try:
        artifact.symlink_to(alternate)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable without elevated permissions")
    result = _check(root)
    assert result["status"] == "FAQ_AUD_RECEIPT_NOT_LINKED"
    assert result["reason"] == "UNSAFE_RENDERED_ARTIFACT"


def test_601_legacy_db_without_url_device_scope_abstains(tmp_path):
    root = tmp_path / "AUD-FAQ-LEGACY"
    root.mkdir()
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,rendered_artifact_ref TEXT);"
        )
        con.execute("INSERT INTO pages VALUES ('PAGE-1','AUD-FAQ-LEGACY')")
        con.execute(
            "INSERT INTO page_snapshots VALUES "
            "('SNP-1','PAGE-1','artifacts/rendered/one.html')"
        )
    result = _check(root)
    assert result["status"] == "FAQ_AUD_RECEIPT_NOT_LINKED"
    assert result["reason"] == "MISSING_AUD_SNAPSHOT_SCOPE"


def test_601_signed_receipt_other_url_not_accepted_even_if_dom_same(tmp_path):
    root, _ = _fixture(tmp_path)
    receipt, mac = _receipt()
    receipt["document_url"] = "https://other.test/faq"
    result = _check(root, receipt=receipt, receipt_mac=mac)
    assert result["status"] == "FAQ_AUD_RECEIPT_NOT_LINKED"
    assert result["persisted_dom_bytes_match_signed_receipt"] is False
