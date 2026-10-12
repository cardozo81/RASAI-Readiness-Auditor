"""#311: explicit read-only CONS-3 source selection for GEO advisory."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from rasai.geo_cons_companion_311 import build_cons_geo_advisory, main


def _cons(tmp_path, *, source=None):
    root = tmp_path / "audits"
    output = root / "consolidated" / "CONS-20261009-0001"
    output.mkdir(parents=True)
    audit_names = source or ["AUD-ALPHA", "AUD-BETA"]
    for name in ("AUD-ALPHA", "AUD-BETA"):
        aud = root / name
        aud.mkdir()
        with sqlite3.connect(aud / "audit.db") as con:
            con.execute(
                "CREATE TABLE audits(audit_id TEXT, status TEXT, completion_status TEXT)"
            )
            con.execute(
                "INSERT INTO audits VALUES (?, 'COMPLETED', 'COMPLETE')", (name,)
            )
    manifest = {
        "cons_id": output.name,
        "report_format_version": "CONS-3",
        "request_fingerprint": "a" * 64,
        "source_audits": [
            {"audit_id": name, "db_path": "C:/ESCAPE/external/audit.db"}
            for name in audit_names
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (output / "report.html").write_text("<h1>Sealed externally</h1>", encoding="utf-8")
    return root, output


def test_311_cons_companion_reuses_only_source_ids_and_never_writes(tmp_path):
    root, cons = _cons(tmp_path)
    original = {
        str(p): sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*") if p.is_file()
    }
    value = build_cons_geo_advisory(cons, root)
    assert value["audits_requested"] == 2
    assert value["audits_eligible"] == 0
    assert value["provider_requests"] == value["audit_writes"] == 0
    assert [x["audit_id"] for x in value["excluded"]] == ["AUD-ALPHA", "AUD-BETA"]
    assert all(x["reason"] == "GEO_SNAPSHOT_TABLE_MISSING" for x in value["excluded"])
    assert value["cons_reference"]["integration_status"].endswith("NOT_NATIVE_CONS")
    assert value["cons_reference"]["manifest_cryptographically_attested"] is False
    assert value["cons_reference"]["native_cons_report_modified"] is False
    assert value["timelines"] == []
    after = {str(p): sha256(p.read_bytes()).hexdigest()
             for p in root.rglob("*") if p.is_file()}
    assert after == original


def test_311_cons_companion_respects_positive_preview_output_without_promoting_trends(
    tmp_path, monkeypatch,
):
    root, cons = _cons(tmp_path)
    from rasai import geo_cons_companion_311 as companion
    def proof(paths):
        assert [p.name for p in paths] == ["AUD-ALPHA", "AUD-BETA"]
        assert all(p.parent == root for p in paths)
        return {
            "contract_version": "RASAI-GEO-LONGITUDINAL-ADVISORY-001",
            "audits_requested": 2,
            "audits_eligible": 2,
            "excluded": [],
            "timelines": [{"trend_conclusion": "N/D"}],
            "provider_requests": 0,
            "audit_writes": 0,
        }
    monkeypatch.setattr(companion, "build_geo_longitudinal_preview", proof)
    result = companion.build_cons_geo_advisory(cons, root)
    assert result["timelines"][0]["trend_conclusion"] == "N/D"
    assert result["cons_reference"]["manifest_request_fingerprint"] == "a" * 64


@pytest.mark.parametrize("issue", [
    "traversal", "duplicate", "wrong_id", "wrong_version",
    "wrong_fingerprint", "missing_html", "missing_source",
])
def test_311_cons_companion_fails_closed_on_unsafe_manifest(tmp_path, issue):
    root, cons = _cons(tmp_path)
    path = cons / "manifest.json"
    doc = json.loads(path.read_text())
    if issue == "traversal":
        doc["source_audits"][0]["audit_id"] = "../../sibling"
    elif issue == "duplicate":
        doc["source_audits"][1]["audit_id"] = doc["source_audits"][0]["audit_id"]
    elif issue == "wrong_id":
        doc["cons_id"] = "CONS-FORGED"
    elif issue == "wrong_version":
        doc["report_format_version"] = "CONS-2"
    elif issue == "wrong_fingerprint":
        doc["request_fingerprint"] = "short"
    elif issue == "missing_html":
        (cons / "report.html").unlink()
    elif issue == "missing_source":
        doc["source_audits"] = []
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError):
        build_cons_geo_advisory(cons, root)


@pytest.mark.parametrize("duplicated_member", [
    '"cons_id":"CONS-20261009-0001","cons_id":"CONS-FORGED"',
    '"source_audits":[{"audit_id":"AUD-ALPHA"},{"audit_id":"AUD-BETA"}],'
    '"source_audits":[{"audit_id":"AUD-ALPHA"},{"audit_id":"AUD-BETA"}]',
    '"request_fingerprint":"' + "a" * 64 + '",'
    '"request_fingerprint":"' + "a" * 64 + '"',
    '"source_audits":[{"audit_id":"AUD-ALPHA","audit_id":"AUD-BETA"},'
    '{"audit_id":"AUD-BETA"}]',
])
def test_311_duplicate_cons_manifest_keys_refuse_advisory_before_aud_reads(
    tmp_path, monkeypatch, duplicated_member,
):
    """#311: key collisions in a local CONS file are not proof of source identity."""
    root, cons = _cons(tmp_path)
    from rasai import geo_cons_companion_311 as companion

    # JSON fragment is valid but ambiguous; a permissive parser would
    # select the final scalar/list/nested audit_id and continue.
    raw = (
        '{"report_format_version":"CONS-3",'
        '"cons_id":"CONS-20261009-0001",'
        '"request_fingerprint":"' + "a" * 64 + '",'
        '"source_audits":[{"audit_id":"AUD-ALPHA"},'
        '{"audit_id":"AUD-BETA"}],'
        + duplicated_member + '}'
    )
    assert isinstance(json.loads(raw), dict)
    (cons / "manifest.json").write_text(raw, encoding="utf-8")
    originals = {str(p): sha256(p.read_bytes()).hexdigest()
                 for p in root.rglob("*") if p.is_file()}
    invoked = []
    monkeypatch.setattr(
        companion, "build_geo_longitudinal_preview",
        lambda paths: invoked.append(paths),
    )
    with pytest.raises(ValueError, match="cannot parse CONS manifest"):
        build_cons_geo_advisory(cons, root)
    assert invoked == []
    assert {str(p): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()} == originals


def test_311_cons_companion_cli_html_does_not_change_cons_or_aud(tmp_path, capsys):
    root, cons = _cons(tmp_path)
    before = (cons / "manifest.json").read_bytes(), (cons / "report.html").read_bytes()
    assert main(["--cons-dir", str(cons), "--audits-root", str(root),
                 "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert "Nenhuma coorte GEO longitudinal elegível" in html
    assert "Esta visualização não faz parte de um CONS-* canônico" in html
    assert (cons / "manifest.json").read_bytes() == before[0]
    assert (cons / "report.html").read_bytes() == before[1]
