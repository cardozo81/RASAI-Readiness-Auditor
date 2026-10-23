"""F3 #646: per-AUD architecture report/CLI is descriptive and read-only."""
from __future__ import annotations

import json
import re
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
    assert "A arquitetura identificada durante a coleta" in output
    assert "Somente" not in output or "somente" in output.lower()
    assert "https://example.org/a" in output
    assert "<code>S-1</code>" in output
    assert "Apdex de navegação ou de experiência" in output
    assert not re.search(r"(?<![A-Za-z0-9])M\d{1,3}(?![A-Za-z0-9])", output)


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


def test_646_requested_vs_final_destination_is_visible_without_query_secrets(tmp_path):
    root, folder, db = _aud(tmp_path, mode="AUTO")
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE page_snapshots SET requested_url=?, final_url=? "
            "WHERE snapshot_id='S-1'",
            (
                "https://example.org/a?access_token=PRIVATE_REQUEST_TOKEN",
                "https://www.example.org/final?authorization=PRIVATE_FINAL_TOKEN",
            ),
        )
    before = db.read_bytes()
    projected = inspect_audit_architecture_context(root, "AUD-646")
    assert projected["status"] == "ADVISORY_OBSERVED"
    row = next(r for r in projected["snapshots"] if r["snapshot_id"] == "S-1")
    assert row["final_target_differs_from_requested"] is True
    # Reclassification is allowed to abstain when physically matched evidence
    # for the new URL cannot be established; no fallback from other snapshots.
    page = architecture_audit_context_html(projected)
    assert "URL final observada" in page
    assert "https://example.org/a?" in page
    assert "https://www.example.org/final?" in page
    assert "parâmetros omitidos" in page
    assert "PRIVATE_REQUEST_TOKEN" not in page
    assert "PRIVATE_FINAL_TOKEN" not in page
    assert "URLs solicitada e final diferentes" in page
    assert db.read_bytes() == before


def test_646_architecture_report_escapes_urls_and_does_not_promote_redirect_to_fact(tmp_path):
    root, folder, db = _aud(tmp_path, mode="UNFORCED")
    result = inspect_audit_architecture_context(root, "AUD-646")
    assert result["status"] == "ADVISORY_OBSERVED"
    detached = dict(result)
    detached["snapshots"] = [dict(row) for row in result["snapshots"]]
    detached["snapshots"][0]["final_url"] = (
        "https://example.org/path?q=PRIVATE_SCRIPT"
        "&track=%3Cscript%3E"
    )
    detached["snapshots"][0]["final_target_differs_from_requested"] = True
    result_html = architecture_audit_context_html(detached)
    assert "PRIVATE_SCRIPT" not in result_html
    assert "<script>" not in result_html
    assert "não extrapolar" in result_html
    assert "não demonstra sozinha" in result_html
    assert all(row["effective_architecture"] is None for row in result["snapshots"])


def test_646_cli_json_redacts_raw_query_and_userinfo_without_reclassifying_m6(
    tmp_path, capsys,
):
    root, folder, database = _aud(tmp_path, mode="UNFORCED")
    with sqlite3.connect(database) as con:
        con.execute(
            "UPDATE page_snapshots SET requested_url=?, final_url=? "
            "WHERE snapshot_id='S-1'",
            (
                "https://user:PRIVATE_PASSWORD@example.org/a?"
                "token=PRIVATE_REQUEST_TOKEN#PRIVATE_FRAG",
                "https://api:PRIVATE_PASS@www.example.org/final?"
                "sig=PRIVATE_FINAL_SIGNATURE#SECRET",
            ),
        )
    before = database.read_bytes()
    # The internal advisory projection keeps exact URLs for physical M6
    # identity matching. The CLI publication boundary redacts only output.
    physical = inspect_audit_architecture_context(root, "AUD-646")
    assert physical["status"] == "ADVISORY_OBSERVED"
    original = next(row for row in physical["snapshots"]
                    if row["snapshot_id"] == "S-1")
    assert "PRIVATE_REQUEST_TOKEN" in original["requested_url"]
    assert original["final_target_differs_from_requested"] is True
    assert main([str(folder), "--consumer-matrix"]) == 0
    displayed = capsys.readouterr().out
    for secret in (
        "PRIVATE_PASSWORD", "PRIVATE_REQUEST_TOKEN", "PRIVATE_FRAG",
        "PRIVATE_PASS", "PRIVATE_FINAL_SIGNATURE", "SECRET",
    ):
        assert secret not in displayed
    cli = json.loads(displayed)
    assert cli["raw_url_tokens_exposed"] is False
    assert cli["url_exposure"] == "SCHEME_HOST_PATH_ONLY_QUERY_REDACTED"
    row = next(record for record in cli["snapshots"] if record["snapshot_id"] == "S-1")
    assert row["requested_url"].startswith("https://example.org/a?")
    assert row["final_url"].startswith("https://www.example.org/final?")
    assert "parâmetros omitidos" in row["final_url"]
    assert row["selected_mode"] == "UNFORCED"
    assert row["effective_architecture"] is None
    assert database.read_bytes() == before
