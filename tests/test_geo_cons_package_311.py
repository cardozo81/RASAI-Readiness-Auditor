"""#311: separate GEO-cons report artifact with physical provenance, no CONS writes."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from rasai import geo_cons_package_311 as module


def _cons(tmp_path, *, missing_second=False):
    root = tmp_path / "audits"
    cons = root / "consolidated" / "CONS-20261011-311"
    cons.mkdir(parents=True)
    for name in ("AUD-LEFT", "AUD-RIGHT"):
        if missing_second and name == "AUD-RIGHT":
            continue
        aud = root / name
        aud.mkdir()
        with sqlite3.connect(aud / "audit.db") as db:
            db.execute("CREATE TABLE audits(audit_id TEXT,status TEXT,completion_status TEXT)")
            db.execute("INSERT INTO audits VALUES (?,'COMPLETED','COMPLETE')", (name,))
    manifest = {
        "cons_id": cons.name,
        "report_format_version": "CONS-3",
        "request_fingerprint": "a"*64,
        "source_audits": [
            {"audit_id": "AUD-LEFT", "db_path": "C:/untrusted-location.db"},
            {"audit_id": "AUD-RIGHT", "db_path": "../../untrusted/audit.db"},
        ],
    }
    (cons/"manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (cons/"report.html").write_text("<!doctype html><h1>CONS unchanged</h1>",
                                    encoding="utf-8")
    return root, cons


def _hashes(root):
    return {str(p): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_versioned_geo_package_is_idempotent_and_does_not_rewrite_cons(tmp_path):
    root, cons = _cons(tmp_path)
    before = _hashes(root)
    first = module.materialize_cons_geo_companion(cons, root)
    assert first["status"] == "MATERIALIZED"
    assert first["package_id"].startswith("GCOMP-")
    manifest = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["contract_version"] == "RASAI-CONS-GEO-COMPANION-PACKAGE-311-001"
    assert manifest["native_cons_modified"] is False
    assert manifest["geo_trends_calibrated"] is False
    assert manifest["cons_reference_cryptographically_attested"] is False
    assert manifest["source_cons_id"] == cons.name
    assert manifest["source_cons_manifest_sha256"] == before[str(cons/"manifest.json")]
    assert manifest["source_cons_report_sha256"] == before[str(cons/"report.html")]
    assert manifest["source_aud_db_sha256"] == {
        n: before[str(root/n/"audit.db")] for n in ("AUD-LEFT", "AUD-RIGHT")
    }
    assert manifest["advisory"]["audits_eligible"] == 0
    assert len(manifest["advisory"]["excluded"]) == 2
    assert manifest["audit_writes"] == 0 and manifest["provider_requests"] == 0
    html = Path(first["report_path"]).read_text(encoding="utf-8")
    assert "Nenhuma coorte GEO longitudinal elegível" in html
    assert "tendência" not in html or "N/D" in html
    assert all(sha256(Path(k).read_bytes()).hexdigest() == v
               for k, v in before.items())
    after_first = _hashes(root)
    second = module.materialize_cons_geo_companion(cons, root)
    assert second["status"] == "IDEMPOTENT_EXISTING"
    assert second["package_id"] == first["package_id"]
    assert _hashes(root) == after_first
    assert list((root/"consolidated").glob("CONS-*")) == [cons]


@pytest.mark.parametrize("collision", [
    "cons_id", "source_audits", "nested_audit_id",
])
def test_second_cons_manifest_read_rejects_ambiguous_json_before_gcomp_output(
    tmp_path, monkeypatch, collision,
):
    """#311: preview and package must not disagree on physical source identity."""
    root, cons = _cons(tmp_path)
    canonical = cons / "manifest.json"
    before = _hashes(root)
    # The first preview read uses a physical descriptor; the next read_text\n    # belongs to the packaging revalidation and must reject conflicts.\n    original_read_text = Path.read_text
    seen = {"n": 0}

    def conflicting_second_read(self, *args, **kwargs):
        raw = original_read_text(self, *args, **kwargs)
        if self != canonical:
            return raw
        seen["n"] += 1
        if seen["n"] != 1:
            return raw
        if collision == "nested_audit_id":
            forged = raw.replace(
                '"audit_id": "AUD-LEFT"',
                '"audit_id": "AUD-LEFT", "audit_id": "AUD-OTHER"',
            )
        elif collision == "cons_id":
            forged = raw[:-1] + ',"cons_id":"CONS-OTHER"}'
        else:
            forged = (
                raw[:-1] + ',"source_audits":['
                '{"audit_id":"AUD-LEFT"},{"audit_id":"AUD-MISSING"}]}'
            )
        assert isinstance(json.loads(forged), dict)
        return forged

    monkeypatch.setattr(Path, "read_text", conflicting_second_read)
    with pytest.raises(ValueError, match="CONS source manifest JSON invalid"):
        module.materialize_cons_geo_companion(cons, root)
    assert seen["n"] == 1
    assert not (root / "consolidated-geo-companions").exists()
    assert _hashes(root) == before


def test_absent_source_aud_is_explicit_nd_not_forged(tmp_path):
    root, cons = _cons(tmp_path, missing_second=True)
    item = module.materialize_cons_geo_companion(cons, root)
    stored = json.loads(Path(item["manifest_path"]).read_text(encoding="utf-8"))
    assert stored["source_aud_db_sha256"]["AUD-RIGHT"] is None
    assert stored["advisory"]["audits_eligible"] == 0
    assert "AUD-RIGHT" in [x["audit_id"] for x in stored["advisory"]["excluded"]]


def test_existing_corrupted_geo_sidecar_is_never_overwritten(tmp_path):
    root, cons = _cons(tmp_path)
    first = module.materialize_cons_geo_companion(cons, root)
    report = Path(first["report_path"])
    report.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="existing GEO companion package differs"):
        module.materialize_cons_geo_companion(cons, root)
    assert report.read_bytes() == b"tampered"


def test_reject_unsafe_cons_source_and_stale_fingerprints(tmp_path, monkeypatch):
    root, cons = _cons(tmp_path)
    doc = cons / "manifest.json"
    payload = json.loads(doc.read_text(encoding="utf-8"))
    payload["cons_id"] = "CONS-DIFFERENT"
    doc.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        module.materialize_cons_geo_companion(cons, root)
    assert not (root/"consolidated-geo-companions").exists()


def test_unverified_numeric_trend_must_not_be_published(tmp_path, monkeypatch):
    root, cons = _cons(tmp_path)
    real = module.build_cons_geo_advisory
    def unsafe_preview(*args, **kwargs):
        preview = real(*args, **kwargs)
        preview["timelines"] = [{"trend_conclusion": "IMPROVED", "trend_rate": .8}]
        return preview
    monkeypatch.setattr(module, "build_cons_geo_advisory", unsafe_preview)
    with pytest.raises(ValueError, match="unverified GEO trends"):
        module.materialize_cons_geo_companion(cons, root)
    assert not (root/"consolidated-geo-companions").exists()


def test_live_sqlite_sidecar_is_not_snapshot_materialized(tmp_path):
    root, cons = _cons(tmp_path)
    companion_db = root/"AUD-LEFT"/"audit.db-wal"
    companion_db.write_bytes(b"unverified live journal")
    with pytest.raises(ValueError, match="SQLite sidecars"):
        module.materialize_cons_geo_companion(cons, root)
    assert not (root/"consolidated-geo-companions").exists()


def test_cli_must_be_explicitly_authorized(tmp_path, capsys):
    root, cons = _cons(tmp_path)
    args = ["--cons-dir", str(cons), "--audits-root", str(root)]
    with pytest.raises(SystemExit) as exc:
        module.main(args)
    assert exc.value.code == 2
    assert not (root/"consolidated-geo-companions").exists()
    capsys.readouterr()
    assert module.main([*args,"--write-geo-companion"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "MATERIALIZED"


def test_symlink_destination_rejected(tmp_path):
    root, cons = _cons(tmp_path)
    outside = tmp_path/"outside"
    outside.mkdir()
    link = root/"consolidated-geo-companions"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this runner")
    with pytest.raises(ValueError, match="unsafe GEO companion output"):
        module.materialize_cons_geo_companion(cons, root)
    assert not list(outside.iterdir())


def test_second_geo_projection_must_match_initial_source_snapshot(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    original = _hashes(root)
    real = module.build_cons_geo_advisory
    seen = {"calls": 0}

    def a_moving_projection(*args, **kwargs):
        seen["calls"] += 1
        result = real(*args, **kwargs)
        if seen["calls"] == 2:
            result["excluded"][0]["reason"] = "CHANGED_AFTER_FIRST_PREVIEW"
        return result

    monkeypatch.setattr(module, "build_cons_geo_advisory", a_moving_projection)
    with pytest.raises(ValueError, match="GEO companion projection changed"):
        module.materialize_cons_geo_companion(cons, root)
    assert seen["calls"] == 2
    assert not (root / "consolidated-geo-companions").exists()
    assert _hashes(root) == original


def test_aud_changes_during_second_projection_aborts_new_sidecar(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    real = module.build_cons_geo_advisory
    seen = {"calls": 0}

    def mutating_projection(*args, **kwargs):
        seen["calls"] += 1
        projection = real(*args, **kwargs)
        if seen["calls"] == 2:
            with sqlite3.connect(root / "AUD-LEFT" / "audit.db") as db:
                db.execute(
                    "UPDATE audits SET status='PARTIAL_RETRYABLE'"
                )
        return projection

    monkeypatch.setattr(module, "build_cons_geo_advisory", mutating_projection)
    with pytest.raises(ValueError, match="source AUD changed"):
        module.materialize_cons_geo_companion(cons, root)
    assert seen["calls"] == 2
    assert not (root / "consolidated-geo-companions").exists()


def test_existing_geo_package_is_not_returned_as_success_if_aud_changes(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    first = module.materialize_cons_geo_companion(cons, root)
    previous = Path(first["manifest_path"]).read_bytes()
    real = module.build_cons_geo_advisory
    calls = {"n": 0}

    def changing_source(*args, **kwargs):
        calls["n"] += 1
        preview = real(*args, **kwargs)
        if calls["n"] == 2:
            # Mutate after all input SHA values are captured but before
            # the existing package's identity is accepted as idempotent.
            with sqlite3.connect(root / "AUD-LEFT" / "audit.db") as con:
                con.execute(
                    "UPDATE audits SET status='PARTIAL_RETRYABLE'"
                )
        return preview

    monkeypatch.setattr(module, "build_cons_geo_advisory", changing_source)
    with pytest.raises(ValueError, match="source AUD changed"):
        module.materialize_cons_geo_companion(cons, root)
    assert calls["n"] == 2
    assert Path(first["manifest_path"]).read_bytes() == previous


def test_sidecar_created_during_second_projection_is_rejected(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    real = module.build_cons_geo_advisory
    count = {"n": 0}

    def adding_sidecar(*args, **kwargs):
        count["n"] += 1
        output = real(*args, **kwargs)
        if count["n"] == 2:
            (root / "AUD-LEFT" / "audit.db-wal").write_bytes(b"concurrent transaction")
        return output

    monkeypatch.setattr(module, "build_cons_geo_advisory", adding_sidecar)
    with pytest.raises(ValueError, match="gained SQLite sidecars"):
        module.materialize_cons_geo_companion(cons, root)
    assert not (root / "consolidated-geo-companions").exists()


def test_cons_report_modified_during_staging_never_gets_stale_gcomp(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    source_digests = _hashes(root)
    original_write = Path.write_bytes
    seen = {"staging_reports": 0}

    def change_cons_after_staging_report(self, data):
        count = original_write(self, data)
        if self.name == "report.html" and self.parent.name.startswith(
            ".gcomp-staging-"
        ):
            seen["staging_reports"] += 1
            (cons / "report.html").write_text(
                "<!doctype html><h1>Changed before publication</h1>",
                encoding="utf-8",
            )
        return count

    monkeypatch.setattr(Path, "write_bytes", change_cons_after_staging_report)
    with pytest.raises(ValueError, match="CONS source changed"):
        module.materialize_cons_geo_companion(cons, root)
    assert seen["staging_reports"] == 1
    destination = root / "consolidated-geo-companions"
    assert not list(destination.glob("GCOMP-*"))
    assert not list(destination.glob(".gcomp-staging-*"))
    assert all(
        sha256(Path(path).read_bytes()).hexdigest() == digest
        for path, digest in source_digests.items()
        if path != str(cons / "report.html")
    )


def test_new_aud_journal_during_gcomp_staging_aborts_atomic_publish(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    source_digest = sha256((root / "AUD-LEFT" / "audit.db").read_bytes()).hexdigest()
    original_write = Path.write_bytes
    calls = {"n": 0}

    def add_journal_after_staging_file(self, data):
        saved = original_write(self, data)
        if self.name == "report.html" and self.parent.name.startswith(
            ".gcomp-staging-"
        ):
            calls["n"] += 1
            original_write(
                root / "AUD-LEFT" / "audit.db-journal", b"concurrent SQLite write"
            )
        return saved

    monkeypatch.setattr(Path, "write_bytes", add_journal_after_staging_file)
    with pytest.raises(ValueError, match="gained SQLite sidecars"):
        module.materialize_cons_geo_companion(cons, root)
    assert calls["n"] == 1
    destination = root / "consolidated-geo-companions"
    assert not list(destination.glob("GCOMP-*"))
    assert not list(destination.glob(".gcomp-staging-*"))
    assert sha256((root / "AUD-LEFT" / "audit.db").read_bytes()).hexdigest() == source_digest


@pytest.mark.parametrize(
    ("actual", "observed", "message"),
    [
        (b"1234", b"123456789", "grew beyond verification byte limit"),
        (b"12345678", b"1234", "size changed during verification"),
    ],
    ids=["concurrent-growth", "concurrent-truncation"],
)
def test_gcomp_digest_detects_size_race_during_bounded_physical_read(
    tmp_path, monkeypatch, actual, observed, message,
):
    from io import BytesIO
    path = tmp_path / "source-test.db"
    path.write_bytes(actual)
    monkeypatch.setattr(module, "_MAX_SOURCE_BYTES", 8)
    original_open = Path.open

    def transient_open(self, *args, **kwargs):
        if self == path:
            return BytesIO(observed)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", transient_open)
    with pytest.raises(ValueError, match=message):
        module._file_digest(path)


@pytest.mark.parametrize(
    ("before_bytes", "after_bytes"),
    [
        (b"observed-full-payload", b"short"),
        (b"short", b"observed-full-payload"),
    ],
    ids=["physical-truncation-inside-open", "physical-growth-inside-open"],
)
def test_gcomp_sha_refuses_file_replacement_between_initial_stat_and_open(
    tmp_path, monkeypatch, before_bytes, after_bytes,
):
    """#311: matching final size and read length cannot erase initial size."""
    path = tmp_path / "source-race.db"
    path.write_bytes(before_bytes)
    original_open = Path.open
    switched = []

    def racing_open(self, mode="r", *args, **kwargs):
        if self == path and mode == "rb" and not switched:
            switched.append(True)
            with original_open(self, "wb") as target:
                target.write(after_bytes)
        return original_open(self, mode, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", racing_open)
        with pytest.raises(ValueError, match="source size changed during verification"):
            module._file_digest(path)

    assert switched == [True]
    assert path.read_bytes() == after_bytes
    assert not list(tmp_path.glob("*.tmp"))


def test_native_geo_cons_commands_preserve_cons_and_require_package_opt_in(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint
    root, cons = _cons(tmp_path)
    before = _hashes(root)
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("GCOMP read-only CLI must not install audit runtime"),
    )
    monkeypatch.setattr(
        entrypoint, "_activate_persisted_cli_secrets",
        lambda: pytest.fail("GCOMP CLI must not access provider secrets"),
    )
    args = ["--audits-root", str(root), "--cons-dir", str(cons)]
    assert entrypoint.main(["geo-cons-review", *args, "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert html.startswith("<!doctype html>")
    assert "Nenhuma coorte GEO longitudinal elegível" in html
    assert "N/D" in html
    assert _hashes(root) == before
    assert not (root / "consolidated-geo-companions").exists()

    with pytest.raises(SystemExit) as err:
        entrypoint.main(["geo-cons-package", *args])
    assert err.value.code == 2
    capsys.readouterr()
    assert not (root / "consolidated-geo-companions").exists()

    assert entrypoint.main([
        "geo-cons-package", *args, "--write-geo-companion",
    ]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "MATERIALIZED"
    manifest = json.loads(Path(created["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["contract_version"] == (
        "RASAI-CONS-GEO-COMPANION-PACKAGE-311-001"
    )
    assert manifest["native_cons_modified"] is False
    assert manifest["geo_trends_calibrated"] is False
    assert manifest["audit_writes"] == manifest["provider_requests"] == 0
    assert entrypoint.main([
        "geo-cons-package", *args, "--write-geo-companion",
    ]) == 0
    repeat = json.loads(capsys.readouterr().out)
    assert repeat["status"] == "IDEMPOTENT_EXISTING"
    assert repeat["package_id"] == created["package_id"]
    assert all(sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in before.items())
    assert list((root / "consolidated").glob("CONS-*")) == [cons]
