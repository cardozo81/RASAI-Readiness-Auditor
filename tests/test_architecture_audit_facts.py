"""Audit-only architectural facts feed CAT-01 and relevant AI without refetch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

from rasai.architecture_audit_facts import (
    architecture_audit_facts_html, read_architecture_audit_facts,
)
from rasai.improvement_intelligence import _evidence_fingerprint, _instructions


def fixture(tmp_path: Path, *, corrupt: bool = False) -> Path:
    db = tmp_path / "audit.db"
    artifact = tmp_path / "artifacts" / "raw.html"
    artifact.parent.mkdir(parents=True)
    html = '<html><div id="root"></div><script src="/assets.js"></script></html>'
    artifact.write_text(html, encoding="utf-8")
    stored = hashlib.sha256(html.encode()).hexdigest()
    if corrupt:
        stored = "0" * 64
    metadata = {
        "architecture_artifact_binding": {
            "version": "m3-artifact-binding-v1",
            "raw_sha256": stored,
            "rendered_sha256": None,
            "manifest_attested": False,
        },
        "raw_http": {"redirect_count": 1, "status": 200, "network_error": None},
        "capture_quality": {
            "state": "INCOMPLETE", "final": {"dom_nodes": 180, "main_text_length": 25},
        },
        "document_source": {"bytes": len(html)},
        "rendered_dom": {"bytes": 230},
        "browser_identity": {"descriptor": "Pixel 7", "tls_validation": "ENABLED"},
        "engine": "chromium",
        "script_runtime": {"count": 6},
        "dom_observations": {"count": 12},
        "runtime_diagnostics": {"count": 2},
        "navigation": {"settle_outcome": "BOUNDED_TIMEOUT"},
        "bounded_lazy_probe": {"attempted": False, "state": "NOT_REQUIRED"},
    }
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE pages (page_id TEXT PRIMARY KEY, audit_id TEXT)")
        con.execute("""CREATE TABLE page_snapshots(
            snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,
            raw_artifact_ref TEXT,rendered_artifact_ref TEXT,
            browser_metadata TEXT,architecture_classification TEXT
        )""")
        con.execute("INSERT INTO pages VALUES ('P1','AUD-1')")
        con.execute("INSERT INTO pages VALUES ('P2','AUD-OTHER')")
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?)",
                    ("SNP-1", "P1", "MOBILE", "artifacts/raw.html", None,
                     json.dumps(metadata), "UNKNOWN"))
        con.execute("INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?)",
                    ("SNP-2", "P2", "DESKTOP", "artifacts/raw.html", None,
                     json.dumps(metadata), "CSR_SPA"))
    return db


def test_catalog01_replays_structured_advisory_from_bound_raw_only(tmp_path):
    db = fixture(tmp_path)
    facts = read_architecture_audit_facts(db, "AUD-1")
    assert len(facts) == 1
    item = facts[0]
    assert item["audit_id"] == "AUD-1"
    assert item["snapshot_id"] == "SNP-1"
    assert item["observed_architecture"] == "UNKNOWN"
    assert item["raw_verified_against_capture_digest"] is True
    assert item["raw_signals"]["scripts_external"] == 1
    assert item["raw_signals"]["app_root"] is True
    assert item["hypothesis"]["candidate"] == "CSR_SPA"
    assert item["hypothesis"]["confidence"] == "LOW"
    assert item["measurement_inference_authorized"] is False
    assert item["score_effect"] is False
    assert item["http_status_observed"] == 200
    assert item["runtime_script_resources_count"] == 6
    assert item["runtime_dom_observations_count"] == 12
    assert item["runtime_diagnostic_count"] == 2
    assert item["raw_html_bytes_observed"] == len(
        '<html><div id="root"></div><script src="/assets.js"></script></html>'
    )
    assert not read_architecture_audit_facts(db, "AUD-1", snapshot_id="SNP-2")
    html = architecture_audit_facts_html(db, "AUD-1")
    assert "CAT" not in html or "CAT-01" not in html
    assert "Hipótese preliminar, não comprovada" in html
    assert "Arquitetura registrada (M6)" not in html
    assert "Limites da descoberta de rede" in html
    assert "Status HTTP da captura" in html
    assert "Rede simulada" not in html
    assert "Scripts com telemetria de runtime" in html
    assert "Recursos declarados no DOM" in html
    assert "CSS, APIs e subframes na rede" in html
    assert "Topologia da infraestrutura" in html
    assert "Observações de mutação do DOM" in html
    assert "Limite de espera atingido" in html
    assert "não atesta o certificado" in html
    assert "SNP-2" not in html
    assert "Scripts externos declarados no HTML inicial" in html


def test_digest_tamper_cannot_produce_structural_hypotheses(tmp_path):
    db = fixture(tmp_path, corrupt=True)
    record = read_architecture_audit_facts(db, "AUD-1")[0]
    assert record["raw_verified_against_capture_digest"] is False
    assert record["raw_signals"] is None
    assert record["hypothesis"] is None
    assert "RAW_NOT_VERIFIABLE" in architecture_audit_facts_html(db, "AUD-1")


def test_missing_and_legacy_snapshots_do_not_guess_architecture(tmp_path):
    db = tmp_path / "empty.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE unrelated (id TEXT)")
    assert read_architecture_audit_facts(db, "AUD-1") == []
    assert "Não há snapshots" in architecture_audit_facts_html(db, "AUD-1")


def test_ai_evidence_fingerprint_includes_architecture_changes():
    initial = _evidence_fingerprint([], {}, [], {"observed_architecture": "UNKNOWN"})
    changed = _evidence_fingerprint([], {}, [], {"observed_architecture": "CSR_SPA"})
    assert initial != changed
    assert initial == _evidence_fingerprint([], {}, [], {"observed_architecture": "UNKNOWN"})


def test_ai_task_instructions_distinguish_reference_numbers_from_measured():
    text = _instructions("pt-BR", ("TECHNICAL_HTML", "PERFORMANCE"))
    assert "supporting_context.architecture" in text
    assert "Numeric limits or ideal values" in text
    assert "never turn UNKNOWN into verified SPA/SSR" in text
    assert "never alter historic Apdex" in text.lower().replace("never", "never") or "Never alter historic Apdex" in text
