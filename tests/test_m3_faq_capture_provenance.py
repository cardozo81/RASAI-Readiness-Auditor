"""#652: focused M3 capture cross-attestation and negative tamper/replay cases."""
from copy import deepcopy
from hashlib import sha256
import json
import sqlite3

from rasai.m3_faq_capture_provenance import (
    inspect_persisted_worker_capture, sign_worker_capture, verify_worker_capture,
)

SCOPE = {
    "audit_id": "AUD-TEST-PHYSICAL", "page_id": "PG-1", "snapshot_id": "SNP-1",
    "requested_url": "https://test.invalid/faq",
    "final_url": "https://test.invalid/faq", "device": "MOBILE",
}
BEFORE = sha256(b"canonical").hexdigest()
AFTER = sha256(b"after-click").hexdigest()


def _signed():
    return sign_worker_capture(
        scope=SCOPE, nonce="ab" * 16, before_sha256=BEFORE,
        after_sha256=AFTER, navigation_started_ns=10,
        observed_ns=20, same_page_context=True,
    )


def test_worker_origin_signature_binds_capture_scope_and_both_dom_states():
    signed = _signed()
    assert verify_worker_capture(signed, scope=SCOPE,
                                 before_sha256=BEFORE, after_sha256=AFTER)
    assert not verify_worker_capture(signed, scope={**SCOPE, "page_id": "PG-2"},
                                     before_sha256=BEFORE, after_sha256=AFTER)
    assert not verify_worker_capture(signed, scope=SCOPE,
                                     before_sha256=BEFORE, after_sha256=BEFORE)
    altered = deepcopy(signed)
    altered["payload"]["same_page_context_verified_by_m3"] = False
    assert not verify_worker_capture(altered, scope=SCOPE,
                                     before_sha256=BEFORE, after_sha256=AFTER)
    replay = deepcopy(signed)
    replay["payload"]["capture_nonce"] = "cd" * 16
    assert not verify_worker_capture(replay, scope=SCOPE,
                                     before_sha256=BEFORE, after_sha256=AFTER)


def test_fail_closed_on_timeout_and_uncorroborated_browser_context():
    for changes in ({"same_page_context": False},
                    {"observed_ns": 60_000_000_011}):
        kwargs = dict(scope=SCOPE, nonce="ab" * 16, before_sha256=BEFORE,
                      after_sha256=AFTER, navigation_started_ns=10,
                      observed_ns=20, same_page_context=True)
        kwargs.update(changes)
        import pytest
        with pytest.raises(ValueError):
            sign_worker_capture(**kwargs)


def test_readonly_source_requires_canonical_m3_metadata(tmp_path):
    aud = tmp_path / SCOPE["audit_id"]
    aud.mkdir()
    db = aud / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript(
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots(snapshot_id TEXT,page_id TEXT,browser_metadata TEXT);"
        )
        con.execute("INSERT INTO pages VALUES (?,?)", (SCOPE["page_id"], SCOPE["audit_id"]))
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?)", (
            SCOPE["snapshot_id"], SCOPE["page_id"],
            json.dumps({"experimental_faq_m3_worker_provenance": _signed()}),
        ))
    original = db.read_bytes()
    assert inspect_persisted_worker_capture(
        aud, scope=SCOPE, before_sha256=BEFORE, after_sha256=AFTER,
    )
    assert db.read_bytes() == original
    with sqlite3.connect(db) as con:
        con.execute("UPDATE page_snapshots SET browser_metadata=?", ('{}',))
    assert not inspect_persisted_worker_capture(
        aud, scope=SCOPE, before_sha256=BEFORE, after_sha256=AFTER,
    )
