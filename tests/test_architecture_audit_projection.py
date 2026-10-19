"""F3 #646: per-AUD architecture report/CLI is descriptive and read-only."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rasai.architecture_audit_projection import inspect_audit_architecture_context
from rasai.architecture_audit_html import architecture_audit_context_html
from rasai.architecture_audit_cli import main
from rasai.architecture_consumer_eligibility import architecture_consumer_eligibility
from rasai.architecture_choice import ArchitectureChoice
from rasai.architecture_choice_audit_adapter import prepare_audit_choice_configuration
from rasai.audit_configuration_reuse import KIND_CONSOLE, persist_audit_configuration


def _aud(tmp_path, *, mode=None, declared=None):
    root = tmp_path / "audits"
    folder = root / "AUD-646"
    folder.mkdir(parents=True)
    database = folder / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO audits VALUES('AUD-646')")
        con.execute("CREATE TABLE pages(page_id TEXT,audit_id TEXT)")
        con.execute(
            "CREATE TABLE page_snapshots("
            "snapshot_id TEXT,page_id TEXT,device TEXT,"
            "requested_url TEXT,final_url TEXT,architecture_classification TEXT,"
            "raw_artifact_ref TEXT,rendered_artifact_ref TEXT)"
        )
        con.executemany("INSERT INTO pages VALUES (?,?)", [
            ("P-1", "AUD-646"), ("P-2", "AUD-646"),
        ])
        con.executemany("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?)", [
            ("S-1", "P-1", "MOBILE", "https://example.org/a",
             "https://example.org/a", "CSR_SPA", "artifacts/raw/a.html",
             "artifacts/rendered/a.html"),
            ("S-2", "P-2", "DESKTOP", "https://example.org/b",
             "https://example.org/b", "STATIC_OR_SSR", "artifacts/raw/b.html",
             "artifacts/rendered/b.html"),
        ])
    if mode:
        configuration = prepare_audit_choice_configuration(
            {"targets": ["https://example.org/a"]},
            choice=ArchitectureChoice(mode, declared),
        )
        persist_audit_configuration(
            database, audit_id="AUD-646", kind=KIND_CONSOLE,
            configuration=configuration,
        )
    return root, folder, database


@pytest.mark.parametrize("mode,declared,expected_first,source", [
    ("AUTO", None, "CSR_SPA", "AUTO_DISCOVERY"),
    ("UNFORCED", None, None, "UNFORCED"),
    ("DECLARED", "HYDRATED", "HYDRATED", "USER_DECLARED"),
])
def test_646_sealed_selection_and_m6_are_separate_per_snapshot(
    tmp_path, mode, declared, expected_first, source,
):
    root, folder, db = _aud(tmp_path, mode=mode, declared=declared)
    physical = db.read_bytes()
    result = inspect_audit_architecture_context(root, "AUD-646")
    assert result["status"] == "ADVISORY_OBSERVED"
    assert result["audit_writes"] == result["provider_requests"] == 0
    assert result["applied_to_scoring"] is False
    rows = {r["snapshot_id"]: r for r in result["snapshots"]}
    assert set(rows) == {"S-1", "S-2"}
    assert rows["S-1"]["observed_architecture"] == "CSR_SPA"
    assert rows["S-1"]["effective_architecture"] == expected_first
    assert rows["S-1"]["source"] == source
    assert rows["S-2"]["observed_architecture"] == "STATIC_OR_SSR"
    assert rows["S-2"]["requested_url"] == "https://example.org/b"
    assert rows["S-2"]["device"] == "DESKTOP"
    if mode == "DECLARED":
        assert all(row["discrepancy"] for row in rows.values())
        assert all(row["source"] == "USER_DECLARED" for row in rows.values())
    else:
        assert not any(row["discrepancy"] for row in rows.values())
    assert db.read_bytes() == physical
    output = architecture_audit_context_html(result)
    assert "Arquitetura descoberta pelo M6" in output
    assert "Somente" not in output or "somente" in output.lower()
    assert "https://example.org/a" in output
    assert "<code>S-1</code>" in output
    assert "M23/M25" in output


def test_646_legacy_does_not_inherit_now_current_operator_preference(tmp_path):
    root, _folder, db = _aud(tmp_path)
    before = db.read_bytes()
    result = inspect_audit_architecture_context(root, "AUD-646")
    assert result["status"] == "ADVISORY_OBSERVED"
    assert result["selection"] == "UNFORCED"
    assert result["choice_origin"] == "UNVERIFIED_OR_LEGACY"
    assert all(row["effective_architecture"] is None for row in result["snapshots"])
    assert all(row["observed_architecture"] != "UNKNOWN" for row in result["snapshots"])
    assert db.read_bytes() == before


def test_646_rejects_cross_aud_page_and_snapshot_identifier_collisions(tmp_path):
    root, _folder, db = _aud(tmp_path, mode="AUTO")
    before = db.read_bytes()
    assert inspect_audit_architecture_context(root, "AUD-646")["status"] == "ADVISORY_OBSERVED"
    with sqlite3.connect(db) as con:
        con.execute("INSERT INTO pages VALUES ('P-1','AUD-OTHER')")
    corrupted = db.read_bytes()
    result = inspect_audit_architecture_context(root, "AUD-646")
    assert result["status"] == "NOT_VERIFIABLE"
    assert result["reason"] == "PHYSICAL_SNAPSHOT_IDENTITY_AMBIGUOUS"
    assert db.read_bytes() == corrupted
    assert before != corrupted


def test_646_not_sealed_sources_never_create_or_mutate_sqlite(tmp_path):
    root, folder, db = _aud(tmp_path)
    before = db.read_bytes()
    (folder / "audit.db-wal").write_bytes(b"pending WAL")
    result = inspect_audit_architecture_context(root, "AUD-646")
    assert result["status"] == "NOT_VERIFIABLE"
    assert "UNSEALED" in result["reason"]
    assert db.read_bytes() == before
    (folder / "audit.db-wal").unlink()
    db.unlink()
    result = inspect_audit_architecture_context(root, "AUD-646")
    assert result["status"] == "NOT_VERIFIABLE"
    assert not db.exists()


def test_646_cli_offline_one_aud_and_consumer_eligibility(tmp_path, capsys):
    root, folder, db = _aud(tmp_path, mode="AUTO")
    before = db.read_bytes()
    assert main([str(folder), "--consumer-matrix"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["status"] == "ADVISORY_OBSERVED"
    assert len(parsed["snapshots"]) == 2
    rows = {row["consumer"]: row for row in parsed["consumer_matrix"]}
    assert {key for key, row in rows.items() if row["decision"] == "ADVISORY_SAFE"} == {
        "descriptive_report", "m6_read_only_diagnostic",
    }
    for key in ("CAT-06", "CAT-07", "M23", "M25", "SCORE-GEO", "SARI", "IA"):
        assert rows[key]["decision"] != "ADVISORY_SAFE"
    assert tuple(rows) == tuple(row.consumer for row in architecture_consumer_eligibility())
    assert db.read_bytes() == before
    (folder / "audit.db-shm").write_bytes(b"pending")
    assert main([str(folder)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_VERIFIABLE"
