"""#210: local-index read-only domain preview, never native CONS."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from rasai.consolidation.domain_comparative_index_210 import (
    domain_preview_from_index, main,
)


def _index(tmp_path: Path):
    root = tmp_path / "audits"
    idx = root / ".rasai"
    idx.mkdir(parents=True)
    path = idx / "consolidated-index.db"
    with sqlite3.connect(path) as con:
        con.executescript("""
            PRAGMA user_version=1;
            CREATE TABLE source_audits(
                audit_id TEXT PRIMARY KEY, event_time TEXT,
                status TEXT, completion_status TEXT, devices_json TEXT,
                url_count INTEGER, source_fingerprint TEXT
            );
            CREATE TABLE audit_urls(audit_id TEXT, url TEXT);
        """)
        for name, stamp, url in (
            ("AUD-ONE", "2026-10-10T10:00:00Z", "https://example.org/product-a"),
            ("AUD-TWO", "2026-10-10T11:00:00Z", "https://example.org/product-b"),
            ("AUD-OTHER", "2026-10-10T12:00:00Z", "https://another.org/product"),
        ):
            con.execute(
                "INSERT INTO source_audits VALUES (?,?,?,?,?,?,?)",
                (name, stamp, "COMPLETED", "COMPLETE", '["MOBILE"]', 1, "a"*64),
            )
            con.execute("INSERT INTO audit_urls VALUES (?,?)", (name, url))
    return root, path


def test_existing_index_yields_same_host_advisory_without_creating_cons(tmp_path):
    root, path = _index(tmp_path)
    before = sha256(path.read_bytes()).hexdigest()
    result = domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
    assert result["eligible"] is True
    assert result["comparison_mode"] == "SAME_DOMAIN_COMPARATIVE"
    assert result["production_cons_mode_changed"] is False
    assert result["audit_score_deltas_eligible"] is False
    assert result["apdex_or_cwv_deltas_eligible"] is False
    assert result["index_reference"]["source_audits_reopened_for_freshness"] is False
    assert result["index_reference"]["source_package_freshness_verified"] is False
    assert result["index_reference"]["native_cons3_created"] is False
    assert result["index_reference"]["index_writes"] == 0
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert sha256(path.read_bytes()).hexdigest() == before
    assert not (root / "consolidated").exists()


def test_different_hostname_and_incomplete_aud_refuse_comparison(tmp_path):
    root, path = _index(tmp_path)
    result = domain_preview_from_index(root, ("AUD-ONE", "AUD-OTHER"))
    assert result["reason"] == "DIFFERENT_HOSTNAMES"
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE source_audits SET completion_status='PARTIAL_RETRYABLE' "
            "WHERE audit_id='AUD-TWO'"
        )
    result = domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
    assert result["reason"] == "AUD_NOT_LOGICALLY_COMPLETE"


def test_invalid_selected_ids_and_multiple_urls_fail_closed(tmp_path):
    root, db = _index(tmp_path)
    for ids in (("AUD-ONE",), ("AUD-ONE", "AUD-ONE"),
                ("AUD-ONE", "../../escape"), ("AUD-ONE", "AUD-MISSING")):
        with pytest.raises(ValueError):
            domain_preview_from_index(root, ids)
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO audit_urls VALUES ('AUD-TWO', 'https://example.org/product-c')"
        )
    with pytest.raises(ValueError, match="exactly one"):
        domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))


def test_malformed_source_fingerprint_cannot_create_eligible_comparison(tmp_path):
    root, db = _index(tmp_path)
    for malformed in ("CORRUPT", "a" * 63, "z" * 64, " " + "a" * 64):
        with sqlite3.connect(db) as connection:
            connection.execute(
                "UPDATE source_audits SET source_fingerprint=? WHERE audit_id=?",
                (malformed, "AUD-TWO"),
            )
        before = db.read_bytes()
        with pytest.raises(ValueError, match="fingerprint"):
            domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
        assert db.read_bytes() == before
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE source_audits SET source_fingerprint=? WHERE audit_id=?",
            ("b" * 64, "AUD-TWO"),
        )
    # Correct syntax is necessary but does not attest the original AUD's
    # freshness or validate the cache fingerprint against a source file.
    value = domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
    assert value["eligible"] is True
    assert value["index_reference"]["source_package_freshness_verified"] is False


def test_missing_index_is_not_created(tmp_path):
    root = tmp_path / "audits"
    root.mkdir()
    with pytest.raises(ValueError, match="existing safe analytical index"):
        domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
    assert not (root / ".rasai").exists()


def test_cli_is_read_only_and_never_launches_consolidation(tmp_path, capsys):
    root, index = _index(tmp_path)
    original = index.read_bytes()
    assert main(["--audits-root", str(root),
                 "--audit-id", "AUD-ONE", "--audit-id", "AUD-TWO"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["eligible"] is True
    assert result["index_reference"]["read_only"] is True
    assert result["index_reference"]["source_package_freshness_verified"] is False
    assert index.read_bytes() == original


def test_wal_or_sqlite_journal_sidecar_abstains_without_reading_stale_index(tmp_path):
    root, db = _index(tmp_path)
    original = db.read_bytes()
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = db.parent / (db.name + suffix)
        sidecar.write_bytes(b"UNVERIFIED-IN-PROGRESS")
        try:
            with pytest.raises(ValueError, match="sidecars"):
                domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
            assert db.read_bytes() == original
        finally:
            sidecar.unlink()


def test_same_domain_html_is_read_only_responsive_and_printable(tmp_path, capsys):
    root, db = _index(tmp_path)
    before = db.read_bytes()
    assert main(["--format", "html", "--audits-root", str(root),
                 "--audit-id", "AUD-ONE", "--audit-id", "AUD-TWO"]) == 0
    html = capsys.readouterr().out
    assert "<!doctype html>" in html
    assert "Prévia comparativa por domínio (não é CONS)" in html
    assert "source_package_freshness_verified" not in html
    assert "frescor frente às AUDs não foi revalidado" in html
    assert "https://example.org/product-a" in html
    assert "https://example.org/product-b" in html
    assert "Métricas por URL" in html
    assert "N/D" in html
    assert "@media print" in html
    assert "@media(max-width:680px)" in html
    assert db.read_bytes() == before
    assert not (root / "consolidated").exists()


def test_same_domain_html_escapes_all_dynamic_audit_fields(tmp_path):
    from rasai.consolidation.domain_comparative_html_210 import (
        render_same_domain_advisory_html as render,
    )
    root, db = _index(tmp_path)
    result = domain_preview_from_index(root, ("AUD-ONE", "AUD-TWO"))
    result["audits"][0]["url"] = "https://example.org/<svg onload=alert(123)>"
    result["hostname"] = 'host"><script>danger</script>'
    html = render(result)
    assert "&lt;svg onload=alert(123)&gt;" in html
    assert "&lt;script&gt;danger&lt;/script&gt;" in html
    assert "<script>danger</script>" not in html
    assert "<svg onload=" not in html
    result["index_reference"]["source_package_freshness_verified"] = True
    with pytest.raises(ValueError, match="freshness"):
        render(result)


def test_same_domain_html_abstention_without_false_positive_table(tmp_path, capsys):
    root, db = _index(tmp_path)
    assert main(["--format", "html", "--audits-root", str(root),
                 "--audit-id", "AUD-ONE", "--audit-id", "AUD-OTHER"]) == 0
    html = capsys.readouterr().out
    assert "Não comparável: Os nomes de host" in html
    assert "<table>" not in html
    assert "antes/depois" in html
