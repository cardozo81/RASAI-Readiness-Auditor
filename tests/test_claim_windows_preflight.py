"""#603: no-provider evidence-preflight checks on synthetic local AUD."""
import importlib.util
import json
from pathlib import Path
import sqlite3

PATH = Path(__file__).resolve().parents[1] / "scripts" / "claim_review_windows_acceptance.py"
spec = importlib.util.spec_from_file_location("rasai_claim_603_windows_preflight", PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def _aud(tmp_path):
    root = tmp_path / gate.AUD_ID
    root.mkdir()
    with sqlite3.connect(root / "audit.db") as db:
        db.executescript(
            "CREATE TABLE audits(audit_id TEXT,status TEXT,completion_status TEXT);"
            "CREATE TABLE pages(page_id TEXT,audit_id TEXT);"
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,captured_at TEXT,main_content_ref TEXT);"
        )
        db.execute("INSERT INTO audits VALUES (?,'COMPLETED','COMPLETE')", (gate.AUD_ID,))
        db.execute("INSERT INTO pages VALUES ('PG1',?)", (gate.AUD_ID,))
        db.execute(
            "INSERT INTO page_snapshots VALUES ('SNP1','PG1',"
            "'2026-10-14T19:00:00-03:00','artifacts/main.txt')"
        )
    return root


def _packet(tmp_path):
    root = tmp_path / "private-review"
    root.mkdir()
    (root / "claim.txt").write_text("contract claim", encoding="utf-8")
    (root / "document.txt").write_text("not official", encoding="utf-8")
    (root / "receipt.json").write_text('{"review":{}, "mac":"UNSIGNED"}', encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({
        "audit_id": gate.AUD_ID, "at_date": "2026-10-14",
        "claims": [{
            "claim_id": "C1", "snapshot_id": "SNP1", "product_scope": "P1",
            "claim_file": "claim.txt", "document_file": "document.txt",
            "receipt_file": "receipt.json",
        }],
    }), encoding="utf-8")
    return root / "manifest.json"


def test_readonly_autodiscovery_and_utc_capture_date(tmp_path):
    root = _aud(tmp_path)
    original = (root / "audit.db").read_bytes()
    data = gate.inspect(audit_directory=None, search_root=tmp_path, manifest=None, env={})
    assert data["status"] == "PRIVATE_SIGNED_PACKET_REQUIRED"
    assert data["snapshots"] == data["snapshots_with_utc_date"] == 1
    assert data["capture_utc_days"] == ["2026-10-14"]
    assert (root / "audit.db").read_bytes() == original
    assert data["audit_writes"] == data["provider_requests"] == 0


def test_unsigned_private_packet_is_never_treated_as_authenticated(tmp_path):
    root = _aud(tmp_path)
    packet = _packet(tmp_path)
    data = gate.inspect(audit_directory=root, search_root=None, manifest=packet, env={})
    assert data["status"] == "PRIVATE_REVIEW_CREDENTIALS_REQUIRED"
    assert data["packet_status"] == "PRIVATE_FILES_PRESENT_NOT_YET_AUTHENTICATED"
    output = json.dumps(data)
    assert "contract claim" not in output and "UNSIGNED" not in output


def test_no_aud_and_bad_unzoned_time_fail_closed(tmp_path):
    data = gate.inspect(audit_directory=None, search_root=tmp_path, manifest=None, env={})
    assert data["status"] == "AUD_DIRECTORY_REQUIRED"
    assert list(tmp_path.iterdir()) == []
    assert gate._utc_day("2026-10-14T15:00:00") is None


def test_duplicate_manifest_keys_and_ambiguous_aud_directory(tmp_path):
    aud = _aud(tmp_path)
    invalid = tmp_path / "bad.json"
    invalid.write_text('{"audit_id":"one","audit_id":"two"}', encoding="utf-8")
    data = gate.inspect(audit_directory=aud, search_root=None, manifest=invalid, env={})
    assert data["status"] == "PRIVATE_PACKET_NOT_READY"
    nested = tmp_path / "nested" / gate.AUD_ID
    nested.mkdir(parents=True)
    (nested / "audit.db").write_bytes(b"fake")
    ambiguous = gate.inspect(audit_directory=None, search_root=tmp_path, manifest=None, env={})
    assert ambiguous["status"] == "MULTIPLE_AUD_CANDIDATES"
    assert ambiguous["candidate_count"] == 2


def test_packet_symlink_to_outside_is_refused(tmp_path):
    aud = _aud(tmp_path)
    packet = _packet(tmp_path)
    doc = packet.parent / "document.txt"
    doc.unlink()
    try:
        doc.symlink_to(tmp_path / "outside-secret")
    except (NotImplementedError, OSError):
        return
    status = gate.inspect(audit_directory=aud, search_root=None, manifest=packet, env={})
    assert status["status"] == "PRIVATE_PACKET_NOT_READY"


def test_explicit_nonexistent_manifest_is_distinct_from_invalid_packet(tmp_path):
    aud = _aud(tmp_path)
    absent = tmp_path / "private" / "manifest.json"
    result = gate.inspect(audit_directory=aud, search_root=None, manifest=absent, env={})
    assert result["status"] == result["packet_status"] == "PRIVATE_MANIFEST_MISSING"
    assert result["packet_claims"] == 0
    assert not absent.exists()
