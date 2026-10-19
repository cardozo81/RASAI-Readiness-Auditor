"""Sidecar-specific advisory review never mutates a sealed AUD or Apdex."""
from __future__ import annotations

from hashlib import sha256
import json
import sqlite3

from rasai.apdex_content_readiness_observation import (
    PrimaryContentReadiness, STRICT_PROVENANCE_VERSION,
)
from rasai.apdex_readiness_sidecar import write_readiness_sidecar
from rasai.apdex_readiness_review import inspect_content_readiness_review
from rasai.apdex_readiness_review_html import content_readiness_review_html
from rasai.apdex_readiness_review_cli import main


def _fixture(tmp_path, monkeypatch, status="OBSERVED"):
    from rasai import catalog_report_site
    monkeypatch.setattr(
        catalog_report_site, "catalog_report_is_fresh",
        lambda *, audit_id, workspace: True,
    )
    aud = tmp_path / "AUD-CONTENT-322"
    aud.mkdir()
    db = aud / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE audits("
            "audit_id TEXT PRIMARY KEY,status TEXT,completion_status TEXT)"
        )
        con.execute(
            "INSERT INTO audits VALUES('AUD-CONTENT-322','COMPLETED','COMPLETE')"
        )
    report = aud / "report-catalog"
    report.mkdir()
    (report / "manifest.json").write_bytes(b'{"contract":"TEST"}')
    observation = PrimaryContentReadiness(
        sample_id="M25<&>1", context_id="CONTEXT-1", page_id="PAGE-1",
        device="MOBILE", architecture="CSR_SPA",
        method_version=STRICT_PROVENANCE_VERSION,
        status=status, load_ms=200.0,
        primary_content_ms=390.0 if status == "OBSERVED" else None,
        post_load_delta_ms=190.0 if status == "OBSERVED" else None,
        observation_window_ms=1200,
        reason="stable_primary_dom_text" if status == "OBSERVED" else "no_checkpoints",
    )
    item = write_readiness_sidecar(aud, observation)
    return aud, item


def _bytes(aud):
    return {
        str(path): sha256(path.read_bytes()).hexdigest()
        for path in aud.rglob("*") if path.is_file()
    }


def test_322_observed_documentary_review_shows_separate_load_and_ready(tmp_path, monkeypatch, capsys):
    aud, item = _fixture(tmp_path, monkeypatch)
    before = _bytes(aud)
    packet = item.read_bytes()
    review = inspect_content_readiness_review(aud, item)
    assert review["status"] == "DOCUMENTARY_SIDECAR_OBSERVED"
    assert review["producer_declared_only"] is True
    assert review["physical_sample_attested"] is False
    assert review["apdex_recalculated"] is False
    assert review["observation"]["post_load_delta_ms"] == 190
    assert review["observation"]["load_ms"] == 200
    html = content_readiness_review_html(review)
    assert "200 ms" in html and "390 ms" in html and "190 ms" in html
    assert "M25&lt;&amp;&gt;1" in html
    assert "não modifica o Apdex homologado" in html
    assert main(["--audit-directory", str(aud), "--sidecar", str(item)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == "DOCUMENTARY_SIDECAR_OBSERVED"
    assert main([
        "--audit-directory", str(aud), "--sidecar", str(item),
        "--format", "html",
    ]) == 0
    assert "Registro experimental" in capsys.readouterr().out
    assert _bytes(aud) == before
    assert item.read_bytes() == packet


def test_322_timeout_is_censored_and_never_claims_content_ready(tmp_path, monkeypatch):
    aud, item = _fixture(tmp_path, monkeypatch, status="TIMEOUT")
    review = inspect_content_readiness_review(aud, item)
    assert review["status"] == "DOCUMENTARY_SIDECAR_OBSERVED"
    assert review["observation"]["primary_content_ms"] is None
    html = content_readiness_review_html(review)
    assert "Janela excedida" in html
    assert "190 ms" not in html
    assert "N/D" in html


def test_322_tampered_sidecar_and_wrong_aud_do_not_publish_claims(
    tmp_path, monkeypatch, capsys,
):
    aud, item = _fixture(tmp_path, monkeypatch)
    existing = item.read_bytes()
    item.write_bytes(existing + b"x")
    result = inspect_content_readiness_review(aud, item)
    assert result["status"] == "NOT_VERIFIABLE"
    assert result["observation"] is None
    assert "N/D" in content_readiness_review_html(result)
    assert main(["--audit-directory", str(aud), "--sidecar", str(item)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "NOT_VERIFIABLE"
    item.write_bytes(existing)
    wrong = tmp_path / "AUD-OTHER"
    wrong.mkdir()
    assert inspect_content_readiness_review(wrong, item)["status"] == "NOT_VERIFIABLE"
    assert not (wrong / "audit.db").exists()
