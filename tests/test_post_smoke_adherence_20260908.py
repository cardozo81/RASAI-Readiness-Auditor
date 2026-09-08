from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.console_config import State as BaseState, build_command
from rasai.console_m23 import State
from rasai.console_settings import load_console_config, save_console_config
from rasai.m23_apdex_profiles import NavigationMeasurement
from rasai.m23_persistence import M23Persistence
from rasai.persistence import AuditWorkspace


def test_ini_roundtrip_restores_nonsecret_environment_and_both_remediations(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "rasai-console.ini"
    state = State()
    state.ai_provider = "none"
    state.content_remediation = True
    state.technical_remediation = True
    state.web_performance = True
    state.synthetic_apdex = True
    state.apdex_threshold = 2.5
    state.apdex_samples = 100
    monkeypatch.setenv("RASAI_OPENAI_REASONING_EFFORT", "LOW")
    save_console_config(state, path)
    payload = path.read_text(encoding="utf-8")
    assert "[environment]" in payload
    assert "RASAI_AI_CONTENT_REMEDIATION = true" in payload
    assert "RASAI_AI_TECHNICAL_REMEDIATION = true" in payload
    assert "RASAI_APDEX_THRESHOLD_SECONDS = 2.5" in payload
    assert "API_KEY" not in payload

    for name in ("RASAI_AI_CONTENT_REMEDIATION", "RASAI_AI_TECHNICAL_REMEDIATION", "RASAI_APDEX_THRESHOLD_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    restored = State()
    result = load_console_config(restored, path)
    assert not result.warnings
    assert restored.content_remediation is True
    assert restored.technical_remediation is True
    assert os.environ["RASAI_AI_CONTENT_REMEDIATION"] == "true"
    assert os.environ["RASAI_AI_TECHNICAL_REMEDIATION"] == "true"
    assert os.environ["RASAI_APDEX_THRESHOLD_SECONDS"] == "2.5"


def test_build_command_explicitly_propagates_technical_remediation() -> None:
    state = BaseState(target="https://example.com", content_remediation=True, technical_remediation=True)
    command = build_command(state)
    assert "--ai-content-remediation" in command
    assert "--ai-technical-remediation" in command


def test_navigation_measurement_has_browser_diagnostics_contract() -> None:
    item = NavigationMeasurement(
        status="SUCCESS", duration_ms=100, http_status=200, final_url="https://example.com/",
        error_code=None, error_message=None, profile_applied=True, cpu_method="cpu", network_method="net",
        browser_diagnostics=({"type": "CONSOLE_ERROR", "message": "boom"},),
    )
    assert item.browser_diagnostics[0]["type"] == "CONSOLE_ERROR"


def test_report_sources_expose_discovery_scoring_and_balanced_dashboard() -> None:
    readiness = Path("src/rasai/rasai_readiness_reporting.py").read_text(encoding="utf-8")
    semantics = Path("src/rasai/report_semantics.py").read_text(encoding="utf-8")
    premium = Path("src/rasai/report_navigation.py").read_text(encoding="utf-8")
    assert "SARI - inputs técnicos de descoberta" in readiness
    assert "BR-GEO-003" in readiness and "BR-GEO-017" in readiness and "BR-GEO-018" in readiness
    assert "indicator-primary-grid" in readiness
    assert "indicator-supporting-grid" in readiness
    assert "repeat(4,minmax(0,1fr))" in semantics
    assert "max-width:100%;width:100%" in premium


def test_apdex_reporting_groups_browser_diagnostics_without_claiming_causality() -> None:
    source = Path("src/rasai/m23_reporting.py").read_text(encoding="utf-8")
    assert "Erros de console e browser agrupados" in source
    assert "não são tratados como causa comprovada" in source
    assert "CONSOLE_ERROR" in source and "REQUEST_FAILED" in source and "PAGE_ERROR" in source


def test_m24_copy_separates_advisory_layer_from_scored_base_rules() -> None:
    source = Path("src/rasai/m24_reporting.py").read_text(encoding="utf-8")
    assert "BR-GEO-003, BR-GEO-017 e BR-GEO-018 permanecem inputs do SARI-001" in source
    assert "IA técnica de crawling/discovery" in source
