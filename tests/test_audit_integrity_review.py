"""#375: local AUD integrity review remains read-only and conservative."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import sqlite3

from rasai.audit_integrity_review_375 import inspect_audit_integrity, main


AUD = "AUD-TEST0012345678"


def _audit(tmp_path):
    root = tmp_path / AUD
    root.mkdir()
    (root / "artifacts").mkdir()
    report = root / "report-catalog"
    report.mkdir()
    (report / "manifest.json").write_text('{"contract":"CATALOG-REPORT-002"}', encoding="utf-8")
    (report / "integrity").mkdir()
    (report / "integrity" / "audit-snapshot.db").write_bytes(b"fixture snapshot")
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript("""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT
            );
            CREATE TABLE synthetic_apdex_runs (
                audit_id TEXT PRIMARY KEY, attempted_samples INTEGER,
                valid_samples INTEGER, invalid_samples INTEGER, status TEXT
            );
            CREATE TABLE synthetic_apdex_samples (
                sample_id TEXT PRIMARY KEY,
                audit_id TEXT REFERENCES audits(audit_id)
            );
            CREATE TABLE synthetic_ux_apdex_runs (
                audit_id TEXT PRIMARY KEY, attempted_samples INTEGER,
                valid_samples INTEGER, invalid_samples INTEGER, status TEXT
            );
            CREATE TABLE synthetic_ux_apdex_samples (
                sample_id TEXT PRIMARY KEY,
                audit_id TEXT REFERENCES audits(audit_id)
            );
            CREATE TABLE perplexity_search_runs (
                run_id TEXT PRIMARY KEY, audit_id TEXT REFERENCES audits(audit_id)
            );
        """)
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)", (AUD, "COMPLETED", "COMPLETE")
        )
        con.execute(
            "INSERT INTO synthetic_apdex_runs VALUES (?,?,?,?,?)",
            (AUD, 10, 10, 0, "PARTIAL"),
        )
        for idx in range(10):
            con.execute(
                "INSERT INTO synthetic_apdex_samples VALUES (?,?)",
                (f"SNP-{idx}", AUD),
            )
        con.execute(
            "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?,?,?)",
            (AUD, 2, 2, 0, "PARTIAL"),
        )
        for idx in range(2):
            con.execute(
                "INSERT INTO synthetic_ux_apdex_samples VALUES (?,?)",
                (f"UX-{idx}", AUD),
            )
    return root


def _mocks(monkeypatch):
    from rasai import catalog_report_site as site, console_cost
    monkeypatch.setattr(
        site, "verify_catalog_report_package", lambda *_args: (True, ())
    )
    monkeypatch.setattr(
        site, "catalog_report_is_fresh", lambda **_kwargs: True,
    )
    monkeypatch.setattr(
        console_cost, "actual_usage", lambda _root: SimpleNamespace(
            ai_attempts=8, ai_successes=8,
            input_tokens=133319, cached_input_tokens=1536,
            output_tokens=46215, reasoning_tokens=9108,
            total_tokens=179534,
            costs=(("USD", 0.13599239),),
            web_external_calls=1,
            web_services=(("PAGESPEED_INSIGHTS", 1),),
        ),
    )


def _hashes(root):
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*") if path.is_file()
    }


def test_release_baseline_review_reconciles_console_counts_without_source_writes(
    tmp_path, monkeypatch, capsys,
):
    root = _audit(tmp_path)
    _mocks(monkeypatch)
    before = _hashes(root)
    data = inspect_audit_integrity(
        root,
        expected_ai_attempts=8,
        expected_web_calls=1,
        expected_navigation_attempts=10,
    )
    assert data["status"] == "STRUCTURALLY_VERIFIED"
    assert data["checks"]["sqlite_integrity"] is True
    assert data["checks"]["foreign_keys"] is True
    assert data["checks"]["report_package_sha256_assurance"] is True
    assert data["checks"]["report_matches_current_audit"] is True
    assert data["checks"]["source_files_unchanged_by_review"] is True
    assert data["observed"]["usage"]["ai_attempts"] == 8
    assert data["observed"]["usage"]["total_tokens"] == 179534
    assert data["observed"]["usage"]["estimated_ai_costs"]["USD"] == 0.13599239
    assert data["observed"]["navigation_apdex"]["run_status"] == "PARTIAL"
    assert data["observed"]["perplexity_runs"] == 0
    assert data["baseline_tag"] == "v0.8.0"
    assert data["audit_writes"] == data["provider_requests"] == 0
    assert before == _hashes(root)
    assert main([
        "--audit-dir", str(root),
        "--expected-ai-attempts", "8", "--expected-web-calls", "1",
        "--expected-navigation-attempts", "10",
    ]) == 0
    assert "STRUCTURALLY_VERIFIED" in capsys.readouterr().out
    assert before == _hashes(root)


def test_release_review_abstains_if_report_package_or_current_source_invalid(
    tmp_path, monkeypatch,
):
    root = _audit(tmp_path)
    _mocks(monkeypatch)
    from rasai import catalog_report_site as site
    monkeypatch.setattr(site, "verify_catalog_report_package",
                        lambda *_args: (False, ("hash mismatch",)))
    monkeypatch.setattr(site, "catalog_report_is_fresh",
                        lambda **_kwargs: False)
    data = inspect_audit_integrity(root, expected_ai_attempts=8)
    assert data["status"] == "NOT_VERIFIED"
    assert "REPORT_PACKAGE_INVALID" in data["errors"]
    assert "REPORT_SOURCE_MISMATCH_OR_NOT_FINAL" in data["errors"]
    assert data["observed"]["report_package_problems"] == ["hash mismatch"]


def test_release_review_detects_counts_mismatch_and_invalid_m23_samples(
    tmp_path, monkeypatch,
):
    root = _audit(tmp_path)
    _mocks(monkeypatch)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("DELETE FROM synthetic_apdex_samples WHERE sample_id='SNP-0'")
    data = inspect_audit_integrity(
        root, expected_ai_attempts=7, expected_web_calls=2,
        expected_navigation_attempts=9,
    )
    assert data["status"] == "NOT_VERIFIED"
    assert "NAVIGATION_APDEX_DATA_INCONSISTENT" in data["errors"]
    assert "AI_ATTEMPT_COUNT_VS_CONSOLE_MISMATCH" in data["errors"]
    assert "WEB_CALL_COUNT_VS_CONSOLE_MISMATCH" in data["errors"]
    assert "NAVIGATION_APDEX_COUNT_VS_CONSOLE_MISMATCH" in data["errors"]


def test_release_review_detects_sqlite_fk_violation_or_another_aud(
    tmp_path, monkeypatch,
):
    root = _audit(tmp_path)
    _mocks(monkeypatch)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("INSERT INTO synthetic_apdex_samples VALUES (?,?)",
                    ("FOREIGN", "AUD-BAD0123456789"))
        con.execute("INSERT INTO audits VALUES (?,?,?)",
                    ("AUD-OTHER123456789", "COMPLETED", "COMPLETE"))
    data = inspect_audit_integrity(root)
    assert data["status"] == "NOT_VERIFIED"
    assert "SQLITE_FOREIGN_KEY_VIOLATIONS" in data["errors"]
    assert "AUDIT_IDENTITY_MISMATCH_OR_MULTIPLE_AUDS" in data["errors"]


def test_release_review_rejects_missing_audit_without_creating_file(tmp_path):
    root = tmp_path / AUD
    root.mkdir()
    data = inspect_audit_integrity(root)
    assert data["status"] == "NOT_VERIFIED"
    assert "AUD_INCOMPLETA_OU_ARQUIVOS_BASE_AUSENTES" in data["errors"]
    assert not (root / "audit.db").exists()
