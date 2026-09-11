from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile

from rasai import rasai_readiness_reporting as readiness
from rasai.report_observation_reconciliation import (
    _ux_dashboard_card,
    content_remediation_diagnostic,
    profile_execution_section,
    sari_band,
)


def test_sari_visual_bands_follow_current_five_band_contract() -> None:
    assert sari_band(100) == ("expected", "Excelente", "90-100")
    assert sari_band(90) == ("expected", "Excelente", "90-100")
    assert sari_band(89.9) == ("expected", "Alta", "75-89")
    assert sari_band(75) == ("expected", "Alta", "75-89")
    assert sari_band(74.9) == ("near", "Moderada", "60-74")
    assert sari_band(60) == ("near", "Moderada", "60-74")
    assert sari_band(59.9) == ("below", "Baixa", "40-59")
    assert sari_band(40) == ("below", "Baixa", "40-59")
    assert sari_band(39.9) == ("critical", "Crítica", "0-39")
    assert sari_band(0) == ("critical", "Crítica", "0-39")
    assert sari_band(None) == ("neutral", "Não determinado", "sem score válido")


def test_experience_apdex_dashboard_card_is_materialized_from_population_summary() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_dir = root / "report"
        report_dir.mkdir()
        (report_dir / "apdex-experience.html").write_text("<html></html>", encoding="utf-8")
        connection = sqlite3.connect(root / "audit.db")
        try:
            connection.executescript(
                """
                CREATE TABLE synthetic_ux_apdex_runs (
                    enabled INTEGER NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE synthetic_ux_apdex_summaries (
                    summary_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    device TEXT NOT NULL,
                    target_samples INTEGER NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    apdex_score REAL,
                    final_group INTEGER NOT NULL
                );
                INSERT INTO synthetic_ux_apdex_runs VALUES (1,'SUCCESS');
                INSERT INTO synthetic_ux_apdex_summaries VALUES
                    ('A','https://example.test/a','POPULATION',100,100,0.91,1),
                    ('B','https://example.test/b','POPULATION',100,98,0.76,1);
                """
            )
            connection.commit()
        finally:
            connection.close()

        html = _ux_dashboard_card(readiness, report_dir)
        assert "Synthetic User Experience Apdex" in html
        assert "0.760-0.910" in html
        assert "198/200 amostras válidas" in html
        assert "apdex-experience.html" in html


def test_experience_apdex_profile_trace_explains_attempts_and_main_responses() -> None:
    samples = [
        {
            "url": "https://example.test/",
            "device": "MOBILE",
            "profile_id": "RASAI_MOBILE_BALANCED",
            "classification": "SATISFIED",
            "http_status": 200,
            "status": "SUCCESS",
            "xhr_fetch_count": 2,
            "request_failed_count": 0,
            "http_error_count": 0,
        },
        {
            "url": "https://example.test/",
            "device": "MOBILE",
            "profile_id": "RASAI_MOBILE_BALANCED",
            "classification": None,
            "http_status": None,
            "status": "TIMEOUT",
            "xhr_fetch_count": 1,
            "request_failed_count": 1,
            "http_error_count": 0,
        },
    ]
    summaries = [
        {
            "url": "https://example.test/",
            "device": "MOBILE",
            "profile_id": "RASAI_MOBILE_BALANCED",
            "target_samples": 1,
        }
    ]
    html = profile_execution_section({"samples": samples, "summaries": summaries})
    assert "Tentativas e retornos da população sintética" in html
    assert "RASAI_MOBILE_BALANCED" in html
    assert "200 x1; sem resposta x1" in html
    assert "SUCCESS x1; TIMEOUT x1" in html
    assert "1/2" in html
    assert "1/1" in html
    assert "XHR/fetch" in html
    assert "subrequests" in html


def test_content_remediation_empty_state_distinguishes_disabled_and_no_eligible_findings() -> None:
    severity, message = content_remediation_diagnostic(
        {
            "enabled": 0,
            "status": "DISABLED",
            "eligible_findings": 0,
            "reason": None,
        },
        0,
    )
    assert severity == "neutral"
    assert "desabilitada" in message
    assert "default OFF" in message

    severity, message = content_remediation_diagnostic(
        {
            "enabled": 1,
            "status": "NO_ELIGIBLE_FINDINGS",
            "eligible_findings": 0,
            "reason": "NO_ELIGIBLE_FINDINGS",
        },
        0,
    )
    assert severity == "neutral"
    assert "nenhum finding era elegível" in message
    assert "não indica erro de provider" in message


def test_content_remediation_empty_state_flags_missing_provider_or_unexpected_zero_attempts() -> None:
    severity, message = content_remediation_diagnostic(
        {
            "enabled": 1,
            "status": "NOT_CONFIGURED",
            "eligible_findings": 3,
            "reason": "NO_HEALTHY_PROVIDER",
        },
        0,
    )
    assert severity == "warn"
    assert "nenhum provider saudável/configurado" in message

    severity, message = content_remediation_diagnostic(
        {
            "enabled": 1,
            "status": "DEGRADED",
            "eligible_findings": 2,
            "reason": "PROVIDER_ERROR",
        },
        0,
    )
    assert severity == "warn"
    assert "nenhuma tentativa externa foi persistida" in message
    assert "PROVIDER_ERROR" in message
