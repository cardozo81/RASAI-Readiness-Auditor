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
from rasai.consolidation.reader import source_file_fingerprint
from rasai.consolidation.domain_comparative_package_210 import (
    materialize_same_domain_package, main as package_cli,
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


def _physical_sources(root: Path, index: Path):
    with sqlite3.connect(index) as con:
        con.execute("ALTER TABLE source_audits ADD COLUMN db_path TEXT")
        for name, url in con.execute(
            "SELECT audit_id, url FROM audit_urls ORDER BY audit_id"
        ).fetchall():
            folder = root / name
            folder.mkdir()
            db = folder / "audit.db"
            with sqlite3.connect(db) as source:
                source.execute(
                    "CREATE TABLE audits(audit_id TEXT, status TEXT, completion_status TEXT)"
                )
                source.execute(
                    "INSERT INTO audits VALUES (?, 'COMPLETED', 'COMPLETE')", (name,)
                )
                source.execute("CREATE TABLE pages(audit_id TEXT, normalized_url TEXT)")
                source.execute("INSERT INTO pages VALUES (?,?)", (name, url))
            con.execute(
                "UPDATE source_audits SET db_path=?,source_fingerprint=? WHERE audit_id=?",
                (f"{name}/audit.db", source_file_fingerprint(db), name),
            )


def test_opt_in_physical_source_reconciliation_is_read_only_and_noncausal(tmp_path, capsys):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    before = {str(p): sha256(p.read_bytes()).hexdigest()
              for p in root.rglob("*") if p.is_file()}
    proof = domain_preview_from_index(
        root, ("AUD-ONE", "AUD-TWO"), verify_source_metadata=True
    )
    ref = proof["index_reference"]
    assert proof["eligible"] is True
    assert ref["source_audits_reopened_for_freshness"] is True
    assert ref["source_file_metadata_matched"] is True
    assert ref["source_url_identity_verified"] is True
    assert ref["source_package_freshness_verified"] is False
    assert ref["native_cons3_created"] is False
    assert main(["--audits-root", str(root), "--audit-id", "AUD-ONE",
                 "--audit-id", "AUD-TWO", "--verify-source-metadata",
                 "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert "isso não autentica os bytes das AUDs" in html
    assert "frescor criptográfico" in html
    assert "nenhum relatório CONS" in html
    assert {str(p): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()} == before
    assert not (root / "consolidated").exists()


def test_opt_in_rejects_stale_index_and_forged_source_url(tmp_path):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    source = root / "AUD-TWO" / "audit.db"
    with sqlite3.connect(source) as con:
        con.execute(
            "UPDATE pages SET normalized_url='https://example.org/different'"
        )
    before = source.read_bytes()
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        domain_preview_from_index(
            root, ("AUD-ONE", "AUD-TWO"), verify_source_metadata=True
        )
    with sqlite3.connect(idx) as con:
        con.execute(
            "UPDATE source_audits SET source_fingerprint=? WHERE audit_id='AUD-TWO'",
            (source_file_fingerprint(source),),
        )
    with pytest.raises(ValueError, match="URL mismatch"):
        domain_preview_from_index(
            root, ("AUD-ONE", "AUD-TWO"), verify_source_metadata=True
        )
    assert source.read_bytes() == before


def test_opt_in_rejects_legacy_index_without_db_path_and_physical_sidecars(tmp_path):
    root, idx = _index(tmp_path)
    with pytest.raises(ValueError, match="incomplete analytical index schema"):
        domain_preview_from_index(
            root, ("AUD-ONE", "AUD-TWO"), verify_source_metadata=True
        )
    _physical_sources(root, idx)
    source = root / "AUD-ONE" / "audit.db"
    sidecar = source.parent / "audit.db-wal"
    sidecar.write_bytes(b"unverified")
    try:
        with pytest.raises(ValueError, match="sidecars"):
            domain_preview_from_index(
                root, ("AUD-ONE", "AUD-TWO"), verify_source_metadata=True
            )
    finally:
        sidecar.unlink()


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


def test_versioned_cdom_package_is_idempotent_isolated_and_immutable(tmp_path):
    root, index = _index(tmp_path)
    _physical_sources(root, index)
    originals = {str(p): sha256(p.read_bytes()).hexdigest()
                 for p in root.rglob("*") if p.is_file()}
    result = materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    assert result["status"] == "MATERIALIZED"
    assert result["package_id"].startswith("CDOM-")
    package_dir = root / "consolidated-domain" / result["package_id"]
    manifest = json.loads((package_dir / "manifest.json").read_text())
    assert manifest["contract_version"] == "CONS-DOMAIN-COMPARATIVE-1"
    assert manifest["native_cons3_created"] is False
    assert manifest["source_package_freshness_verified"] is False
    assert manifest["page_score_or_apdex_deltas_eligible"] is False
    assert manifest["source_audit_ids"] == ["AUD-ONE", "AUD-TWO"]
    assert set(manifest["source_file_metadata_fingerprints"]) == {
        "AUD-ONE", "AUD-TWO"
    }
    assert manifest["provider_requests"] == manifest["audit_writes"] == 0
    assert "report.html" in result["html_path"]
    html = (package_dir / "report.html").read_text(encoding="utf-8")
    assert "Prévia comparativa por domínio" in html
    assert "URLs distintas" in html
    assert "frescor criptográfico" in html
    assert not (root / "consolidated").exists()
    before_package = {
        p.name: sha256(p.read_bytes()).hexdigest() for p in package_dir.iterdir()
    }
    same = materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    assert same["status"] == "IDEMPOTENT_EXISTING"
    assert same["package_id"] == result["package_id"]
    assert {
        p.name: sha256(p.read_bytes()).hexdigest() for p in package_dir.iterdir()
    } == before_package
    assert {str(p): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if str(p) in originals} == originals


def test_cdom_package_rejects_ineligible_and_legacy_without_outputs(tmp_path):
    root, index = _index(tmp_path)
    _physical_sources(root, index)
    for ids in (("AUD-ONE", "AUD-OTHER"), ("AUD-ONE", "AUD-ONE")):
        with pytest.raises(ValueError):
            materialize_same_domain_package(root, ids)
    assert not (root / "consolidated-domain").exists()
    with sqlite3.connect(index) as con:
        con.execute(
            "UPDATE source_audits SET completion_status='PARTIAL_RETRYABLE' "
            "WHERE audit_id='AUD-TWO'"
        )
    with pytest.raises(ValueError):
        materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    assert not (root / "consolidated-domain").exists()


def test_cdom_package_refuses_modified_existing_report(tmp_path):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    result = materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    report = Path(result["html_path"])
    report.write_text("tampered HTML")
    with pytest.raises(ValueError, match="will not overwrite"):
        materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    assert report.read_text() == "tampered HTML"


def test_cdom_rejects_source_changes_between_preview_and_package(tmp_path, monkeypatch):
    from rasai.consolidation import domain_comparative_package_210 as module
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    original = module.source_file_fingerprint
    monkeypatch.setattr(module, "source_file_fingerprint", lambda path: "f" * 64)
    with pytest.raises(ValueError, match="source changed"):
        module.materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    assert not (root / "consolidated-domain").exists()
    monkeypatch.setattr(module, "source_file_fingerprint", original)


def test_cdom_package_cli_explicit_opt_in(tmp_path, capsys):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    args = ["--audits-root", str(root), "--audit-id", "AUD-ONE",
            "--audit-id", "AUD-TWO"]
    with pytest.raises(SystemExit) as exc:
        package_cli(args)
    assert exc.value.code == 2
    assert not (root / "consolidated-domain").exists()
    capsys.readouterr()
    assert package_cli([*args, "--write-domain-package"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "MATERIALIZED"
    assert Path(output["html_path"]).is_file()
    assert not (root / "consolidated").exists()


def test_cdom_package_rejects_symlinked_output_root(tmp_path):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    linked = root / "consolidated-domain"
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not allow symlink fixture")
    with pytest.raises(ValueError, match="unsafe comparison package"):
        materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    assert not list(outside.iterdir())


def test_cdom_v2_opt_in_local_source_bytes_pin_does_not_rewrite_v1(tmp_path):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    before = {
        str(p): sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }
    v1 = materialize_same_domain_package(root, ("AUD-ONE", "AUD-TWO"))
    v2 = materialize_same_domain_package(
        root, ("AUD-ONE", "AUD-TWO"), verify_source_bytes=True,
    )
    assert v1["package_id"] != v2["package_id"]
    manifest1 = json.loads(Path(v1["manifest_path"]).read_text(encoding="utf-8"))
    manifest2 = json.loads(Path(v2["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest1["contract_version"] == "CONS-DOMAIN-COMPARATIVE-1"
    assert "source_file_sha256" not in manifest1
    assert manifest2["contract_version"] == "CONS-DOMAIN-COMPARATIVE-2"
    assert manifest2["source_bytes_locally_verified"] is True
    assert manifest2["source_package_freshness_verified"] is False
    assert manifest2["native_cons3_created"] is False
    assert manifest2["source_file_sha256"] == {
        a: sha256((root / a / "audit.db").read_bytes()).hexdigest()
        for a in ("AUD-ONE", "AUD-TWO")
    }
    assert materialize_same_domain_package(
        root, ("AUD-ONE", "AUD-TWO"), verify_source_bytes=True,
    )["status"] == "IDEMPOTENT_EXISTING"
    assert materialize_same_domain_package(
        root, ("AUD-ONE", "AUD-TWO"),
    )["package_id"] == v1["package_id"]
    assert all(sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in before.items())


def test_cdom_v2_abstains_when_source_bytes_change_before_publication(
    tmp_path, monkeypatch,
):
    from rasai.consolidation import domain_comparative_package_210 as mod
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    old = mod._source_sha256
    counts = {"seen": 0}
    def changed_on_second_pass(source, remaining):
        counts["seen"] += 1
        digest, consumed = old(source, remaining)
        if counts["seen"] == 3:
            return "0" * 64, consumed
        return digest, consumed
    monkeypatch.setattr(mod, "_source_sha256", changed_on_second_pass)
    with pytest.raises(ValueError, match="bytes changed"):
        mod.materialize_same_domain_package(
            root, ("AUD-ONE", "AUD-TWO"), verify_source_bytes=True,
        )
    assert counts["seen"] >= 3
    assert not (root / "consolidated-domain").exists()


def test_cdom_v2_digest_budget_fail_closed_without_materialization(
    tmp_path, monkeypatch,
):
    from rasai.consolidation import domain_comparative_package_210 as mod
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    monkeypatch.setattr(mod, "_MAX_HASH_BYTES_TOTAL", 64)
    with pytest.raises(ValueError, match="SHA-256 evidence budget"):
        mod.materialize_same_domain_package(
            root, ("AUD-ONE", "AUD-TWO"), verify_source_bytes=True,
        )
    assert not (root / "consolidated-domain").exists()


def test_cdom_v2_cli_opt_in_with_crypto_file_digest(tmp_path, capsys):
    root, idx = _index(tmp_path)
    _physical_sources(root, idx)
    args = [
        "--audits-root", str(root), "--audit-id", "AUD-ONE",
        "--audit-id", "AUD-TWO", "--write-domain-package",
        "--verify-source-bytes",
    ]
    assert package_cli(args) == 0
    result = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["contract_version"] == "CONS-DOMAIN-COMPARATIVE-2"
    assert all(len(d) == 64 for d in manifest["source_file_sha256"].values())
    assert result["audit_writes"] == result["provider_requests"] == 0
