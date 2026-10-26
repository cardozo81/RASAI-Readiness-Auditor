"""Focused no-network contract checks for #659 G1."""
from rasai.network_observation import CONTRACT, _public_ip, _item, _utc_capture_time, snapshots_from_audit


def test_public_ip_rejects_private_and_loopback():
    assert _public_ip("192.168.1.1") is None
    assert _public_ip("127.0.0.1") is None
    assert _public_ip("8.8.8.8") == "8.8.8.8"


def test_unknown_not_automatically_observed():
    assert _item(None, source="NO_DNS_CAPTURE")["state"] == "NOT_OBSERVED"
    assert _item("bad", source="sample", state="COLLECTION_FAILED")["value"] is None


def test_missing_legacy_audit_is_safe(tmp_path):
    assert snapshots_from_audit(tmp_path / "missing.db", "AUD-LEGACY") == []
    assert CONTRACT.endswith("-v1")



def test_capture_timestamp_preserves_provenance_and_requires_timezone():
    assert _utc_capture_time("2026-10-26T06:00:00-03:00") == "2026-10-26T09:00:00Z"
    assert _utc_capture_time("2026-10-26T09:00:00Z") == "2026-10-26T09:00:00Z"
    assert _utc_capture_time("2026-10-26 09:00:00") is None
    assert _utc_capture_time(None) is None


def test_passive_snapshot_host_and_utc_are_scoped_to_original_capture(tmp_path):
    import sqlite3
    from rasai.network_reporting import network_report_body
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as cx:
        cx.executescript("""
            CREATE TABLE pages(page_id TEXT, audit_id TEXT);
            CREATE TABLE page_snapshots(
                snapshot_id TEXT, page_id TEXT, device TEXT,
                raw_artifact_ref TEXT, rendered_artifact_ref TEXT,
                browser_metadata TEXT, architecture_classification TEXT,
                final_url TEXT, requested_url TEXT, captured_at TEXT
            );
        """)
        cx.execute("INSERT INTO pages VALUES (?, ?)", ("PAGE-1", "AUD-X"))
        cx.execute("""INSERT INTO page_snapshots VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("SN-1", "PAGE-1", "mobile", None, None, "{}",
             "UNKNOWN", "https://user:password@public.example/path?token=SECRET",
             "https://public.example/", "2026-10-26T06:00:00-03:00"))
    original = db.read_bytes()
    rows = snapshots_from_audit(db, "AUD-X")
    assert len(rows) == 1
    assert rows[0]["target_host"] == "public.example"
    assert rows[0]["capture_utc"] == "2026-10-26T09:00:00Z"
    assert rows[0]["metrics"]["dns_resolution"]["state"] == "NOT_OBSERVED"
    page = network_report_body(tmp_path, "AUD-X")
    assert "public.example" in page and "2026-10-26T09:00:00Z" in page
    assert "SECRET" not in page and "password" not in page
    assert db.read_bytes() == original
