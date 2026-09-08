from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

import pytest

from rasai.console_collection import load_collection_coverage
from rasai.m20_ai import (
    ContentEvidenceInput,
    ContentFindingInput,
    ContentRemediationContractError,
    ContentRemediationRequest,
    _validate_response,
    content_remediation_schema,
)
from rasai.m23_reporting import _apdex_sensitivity_table, _diagnostic_notes
from rasai.rasai_readiness_reporting import _dashboard
from rasai.scoring import _metadata


def _request() -> ContentRemediationRequest:
    return ContentRemediationRequest(
        snapshot_id="S1",
        page_id="P1",
        page_url="https://example.test/",
        device="mobile",
        title="Produto 2026",
        main_content="Texto observado 2026.",
        findings=(ContentFindingInput(
            finding_id="F1", rule_id="BR-GEO-041", title="Finding", severity="MEDIUM",
            expected_condition="cond", observed_value={"x": "y"}, evidence_ids=("E1",),
        ),),
        evidence=(ContentEvidenceInput("E1", "CONTENT", "snapshot", {"text": "2026"}),),
    )


def test_dashboard_uses_persisted_lighthouse_scale_and_metric_conditions(tmp_path: Path) -> None:
    data = {
        "scores": [{
            "device": "MOBILE", "dimension": "OVERALL_READINESS", "coverage": 0.963,
            "confidence": "LOW", "consolidation_status": "PARTIAL", "value": 90.7,
        }],
        "web": [{
            "device": "mobile", "cwv_assessment": "FAIL", "performance_score": 5.0,
            "accessibility_score": 78.0,
        }],
        "web_run": {"enabled": 1, "status": "SUCCESS"},
        "apdex_run": {"enabled": 1},
        "apdex": [{"device": "mobile", "apdex_score": 0.825, "final_group": 0}],
    }
    html = _dashboard(data, tmp_path)
    assert "500/100" not in html
    assert "7800/100" not in html
    assert "<strong>5/100</strong>" in html
    assert "<strong>78/100</strong>" in html
    assert "Crítico - nenhum contexto aprovado" in html
    assert "Crítico - Poor (severidade visual RASAi)" in html
    assert "Quase no esperado - Needs Improvement" in html
    assert "Quase no esperado - Fair" in html
    assert "Quase no esperado - medição parcial" in html


def test_m20_schema_is_bounded_to_request_ids() -> None:
    schema = content_remediation_schema(_request())
    props = schema["properties"]["suggestions"]["items"]["properties"]
    assert props["finding_id"]["enum"] == ["F1"]
    assert props["evidence_ids"]["items"]["enum"] == ["E1"]


def test_m20_contract_error_has_safe_specific_code() -> None:
    payload = {
        "suggestions": [{
            "finding_id": "F-UNKNOWN", "objective": "x", "target_location": "body",
            "proposed_text": "Texto 2026", "evidence_ids": ["E1"], "confidence": 0.8,
            "review_note": "review",
        }]
    }
    with pytest.raises(ContentRemediationContractError) as error:
        _validate_response(payload, _request())
    assert error.value.code == "M20_INVALID_FINDING_REFERENCE"


def test_console_distinguishes_crux_embedded_from_direct_api() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = sqlite3.connect(root / "audit.db")
        db.executescript("""
            CREATE TABLE web_performance_runs(
              audit_id TEXT, enabled INTEGER, status TEXT, reason TEXT, categories TEXT, updated_at TEXT
            );
            INSERT INTO web_performance_runs VALUES('A',1,'SUCCESS',NULL,'["performance","accessibility"]','2026-09-08T00:00:00Z');
            CREATE TABLE web_performance_attempts(service TEXT,status TEXT);
            INSERT INTO web_performance_attempts VALUES('PAGESPEED_INSIGHTS','SUCCESS');
            CREATE TABLE web_performance_observations(
              accessibility_score REAL,pagespeed_artifact_reference TEXT,error_summary TEXT,field_source TEXT
            );
            INSERT INTO web_performance_observations VALUES(78,'artifacts/psi.json',NULL,'PAGESPEED_CRUX');
        """)
        db.commit(); db.close()
        coverage = load_collection_coverage(root)
        assert coverage is not None
        assert coverage.pagespeed_successes == 1
        assert coverage.crux_via_pagespeed == 1
        assert coverage.crux_attempts == 0
        assert coverage.crux_successes == 0


def test_apdex_diagnostics_separate_execution_errors_from_web_signals() -> None:
    row = {
        "valid_samples": 20, "frustrated_count": 0, "tolerating_count": 7,
        "coefficient_of_variation": 0.316, "median_ms": 2451, "p95_ms": 3213,
        "trend_percent": 2.0, "application_error_count": 0, "timeout_count": 0,
        "navigation_error_count": 0, "invalid_samples": 0,
    }
    web = {
        "cwv_assessment": "FAIL", "performance_score": 5.0, "lcp_p75_ms": 3071,
        "inp_p75_ms": 390, "cls_p75": 0.9,
    }
    notes = dict(_diagnostic_notes(row, web))
    assert "Nenhum erro de aplicação/navegação/timeout" in notes["Erros e integridade da execução"]
    assert "Lighthouse Performance=5/100" in notes["Revisar Web Performance"]
    assert "não entram na sua fórmula" in notes["Revisar Web Performance"]


def test_apdex_sensitivity_marks_configured_threshold() -> None:
    samples = [
        {"status": "SUCCESS", "duration_ms": 2200, "classification": "SATISFIED"},
        {"status": "SUCCESS", "duration_ms": 2600, "classification": "TOLERATING"},
        {"status": "SUCCESS", "duration_ms": 6100, "classification": "TOLERATING"},
    ]
    html = _apdex_sensitivity_table(samples, 2.5)
    assert "2.5 s (configurado)" in html
    assert "não calibração por resultado" in html


def test_robots_and_sitemap_are_already_score_inputs_without_ai_dependency() -> None:
    for rule_id in ("BR-GEO-003", "BR-GEO-017", "BR-GEO-018"):
        metadata = _metadata(rule_id)
        assert metadata.dimension == "TECHNICAL_ACCESSIBILITY"
