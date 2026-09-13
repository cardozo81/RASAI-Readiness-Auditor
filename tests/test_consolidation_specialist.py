from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from rasai.consolidation.cons4 import request_fingerprint
from rasai.consolidation.index import ConsolidationIndex
from rasai.consolidation.service import generate, normalize_filter
from rasai.consolidation.specialist import build_evolution, preview_specialist


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workspace(root: Path, audit_id: str, *, when: str, rule_result: str, score: float) -> Path:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    database = workspace / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, project_name TEXT, created_at TEXT, started_at TEXT,
                completed_at TEXT, status TEXT, completion_status TEXT, auditor_version TEXT, ruleset_version TEXT
            );
            CREATE TABLE audit_targets (target_id TEXT PRIMARY KEY,audit_id TEXT,normalized_origin TEXT,target_type TEXT);
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            CREATE TABLE page_snapshots (
                snapshot_id TEXT PRIMARY KEY,page_id TEXT,device TEXT,captured_at TEXT,http_status INTEGER,
                final_url TEXT,canonical TEXT,meta_robots TEXT,title TEXT
            );
            CREATE TABLE rule_executions (
                audit_id TEXT,rule_id TEXT,page_id TEXT,device TEXT,result TEXT,observed_value TEXT,error TEXT,executed_at TEXT
            );
            CREATE TABLE findings (
                audit_id TEXT,severity TEXT,category TEXT,rule_id TEXT,page_id TEXT,device TEXT,status TEXT,title TEXT,observed_value TEXT
            );
            CREATE TABLE scores (
                score_id TEXT PRIMARY KEY,audit_id TEXT,dimension TEXT,device TEXT,value REAL,coverage REAL,
                confidence TEXT,consolidation_status TEXT,scoring_version TEXT,calculated_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO audits VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, "Projeto", when, when, when, "COMPLETED", "COMPLETE", "1.0", "RULESET-1"),
        )
        connection.execute("INSERT INTO audit_targets VALUES (?,?,?,?)", (f"T-{audit_id}", audit_id, "https://example.test", "DOMAIN"))
        connection.execute("INSERT INTO pages VALUES (?,?,?)", (f"P-{audit_id}", audit_id, "https://example.test/a"))
        connection.execute(
            "INSERT INTO page_snapshots VALUES (?,?,?,?,?,?,?,?,?)",
            (f"S-{audit_id}", f"P-{audit_id}", "MOBILE", when, 200, "https://example.test/a", "https://example.test/a", "index,follow", "Produto A"),
        )
        connection.execute(
            "INSERT INTO rule_executions VALUES (?,?,?,?,?,?,?,?)",
            (audit_id, "BR-GEO-011", f"P-{audit_id}", "MOBILE", rule_result, "{}", None, when),
        )
        connection.execute(
            "INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?)",
            (audit_id, "HIGH", "INDEXABILITY", "BR-GEO-011", f"P-{audit_id}", "MOBILE", "OPEN", "Indexabilidade", "{}"),
        )
        connection.execute(
            "INSERT INTO scores VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"SC-{audit_id}", audit_id, "INDEXABILITY", "MOBILE", score, 1.0, "HIGH", "CONSOLIDATED", "SCORE-GEO-004", when),
        )
        connection.commit()
    finally:
        connection.close()
    return workspace


def test_consolidated_report_adds_deterministic_evolution_and_fix_verification_read_only() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = _workspace(root, "AUD-BASE", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        current = _workspace(root, "AUD-CURRENT", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        before = {_digest(baseline / "audit.db"), _digest(current / "audit.db")}
        result = generate(root, normalize_filter(domains=("example.test",), devices=("MOBILE",)))
        after = {_digest(baseline / "audit.db"), _digest(current / "audit.db")}
        assert before == after
        html = result.report_path.read_text(encoding="utf-8")
        assert "Evolução determinística" in html
        assert "Verificação de correções" in html
        assert "Fix Verification" not in html
        assert "BR-GEO-011" in html
        assert "FIXED" in html
        assert "Análise especialista por IA" not in html
        artifact = json.loads((result.report_dir / "specialist-analysis.json").read_text(encoding="utf-8"))
        assert artifact["ai"]["requested"] is False
        assert artifact["comparison"]["baseline_audit_id"] == "AUD-BASE"
        assert artifact["comparison"]["current_audit_id"] == "AUD-CURRENT"
        assert any(item["status"] == "FIXED" for item in artifact["fix_verification"])


def test_comparison_modes_select_expected_pair() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-001", when="2026-07-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-002", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=75)
        _workspace(root, "AUD-003", when="2026-09-01T10:00:00Z", rule_result="PASS", score=85)
        index = ConsolidationIndex(root)
        index.refresh()
        first_last = build_evolution(root, normalize_filter(comparison_mode="FIRST_LAST"))
        assert first_last.comparison.baseline.audit_id == "AUD-001"
        assert first_last.comparison.current.audit_id == "AUD-003"
        latest = build_evolution(root, normalize_filter(comparison_mode="LATEST_PREVIOUS"))
        assert latest.comparison.baseline.audit_id == "AUD-002"
        assert latest.comparison.current.audit_id == "AUD-003"
        manual = build_evolution(root, normalize_filter(comparison_mode="MANUAL", baseline_audit_id="AUD-001", current_audit_id="AUD-002"))
        assert manual.comparison.baseline.audit_id == "AUD-001"
        assert manual.comparison.current.audit_id == "AUD-002"


def test_ai_choice_changes_request_identity_without_persisting_secrets() -> None:
    base = normalize_filter(domains=("example.test",), comparison_mode="FIRST_LAST")
    ai = normalize_filter(
        domains=("example.test",), comparison_mode="FIRST_LAST", specialist_ai=True,
        ai_provider="openai", ai_model="gpt-5.6-luna", ai_reasoning="LOW", ai_timeout_seconds=180,
    )
    assert request_fingerprint("source", base) != request_fingerprint("source", ai)
    canonical = ai.canonical()
    assert canonical["specialist_ai"] is True
    assert canonical["ai_provider"] == "openai"
    assert not any("key" in key.casefold() or "secret" in key.casefold() for key in canonical)


def test_cost_preview_uses_canonical_pricing_and_request_token_hints() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-BASE", when="2026-08-01T10:00:00Z", rule_result="FAIL", score=70)
        _workspace(root, "AUD-CURRENT", when="2026-09-01T10:00:00Z", rule_result="PASS", score=82)
        ConsolidationIndex(root).refresh()
        filters = normalize_filter(specialist_ai=True, ai_provider="openai", ai_model="gpt-5.6-luna", ai_reasoning="LOW")
        provider = SimpleNamespace(name="OPENAI", model="gpt-5.6-luna", reasoning_profile="LOW", requested_reasoning_effort="LOW")
        with patch("rasai.consolidation.specialist._build_ai", return_value=provider):
            preview = preview_specialist(root, filters)
        assert preview.available is True
        assert preview.selected is not None
        assert preview.selected.provider == "OPENAI"
        assert preview.selected.estimated_input_tokens >= 2000
        assert preview.selected.estimated_output_tokens > 0
        assert preview.selected.estimated_cost is not None
        assert preview.selected.currency == "USD"


def test_one_audit_keeps_consolidation_available_without_false_evolution() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _workspace(root, "AUD-ONLY", when="2026-09-01T10:00:00Z", rule_result="PASS", score=80)
        result = generate(root, normalize_filter())
        manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
        assert manifest["evolution_analysis"]["status"] == "UNAVAILABLE"
        assert result.report_path.is_file()
