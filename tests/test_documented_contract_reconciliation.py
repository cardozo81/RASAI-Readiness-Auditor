from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace

import pytest

from rasai.documented_contract_reconciliation import (
    AUTO_EXCLUDE_ENV,
    _CURRENT_PSI_CATEGORIES,
    _install_ai_cost_report_fix,
    _install_ai_usage_presentation_fix,
    _install_current_pagespeed_categories,
    _install_scoring_wording_fix,
    _install_search_comparison_guidance,
    _install_auto_runtime_filter,
    _install_console_auto_capability_filter,
    parse_auto_exclusions,
)


def test_auto_exclusion_is_canonical_and_does_not_remove_key(monkeypatch) -> None:
    from rasai import console_config, provider_runtime_policy

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.setenv(AUTO_EXCLUDE_ENV, "openai")
    original_key = os.environ["OPENAI_API_KEY"]

    _install_auto_runtime_filter()
    _install_console_auto_capability_filter()

    assert parse_auto_exclusions() == ("openai",)
    capabilities = console_config.provider_capabilities()
    assert capabilities["openai"].available is True
    assert capabilities["auto"].available is True
    assert "OPENAI" not in capabilities["auto"].reason.split("pool AUTO", 1)[-1].split(";", 1)[0]
    assert os.environ["OPENAI_API_KEY"] == original_key

    routed = provider_runtime_policy.build_semantic_provider("auto")
    assert "OPENAI" not in [item.name for item in routed.providers]
    assert "OPENAI:USER_EXCLUDED_FROM_AUTO" in routed.excluded_configurations
    # Explicit selection is unaffected by AUTO membership.
    explicit = provider_runtime_policy.build_semantic_provider("openai")
    assert explicit.name == "OPENAI"
    assert os.environ["OPENAI_API_KEY"] == original_key


def test_auto_exclusion_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        parse_auto_exclusions("does-not-exist")


def test_current_pagespeed_contract_accepts_agentic_and_defaults_to_it(monkeypatch) -> None:
    from rasai import cli, m21_web_performance

    monkeypatch.delenv("RASAI_LIGHTHOUSE_CATEGORIES", raising=False)
    _install_current_pagespeed_categories()
    config = m21_web_performance.WebPerformanceConfig(enabled=True).validate()
    assert config.categories == _CURRENT_PSI_CATEGORIES
    assert cli._configured_lighthouse_categories(None) == _CURRENT_PSI_CATEGORIES
    explicit = m21_web_performance.WebPerformanceConfig(
        enabled=True,
        categories=("agentic-browsing",),
    ).validate()
    assert explicit.categories == ("agentic-browsing",)


def test_ai_cost_banner_uses_persisted_attempts_across_purposes() -> None:
    from rasai import report_navigation

    _install_ai_cost_report_fix()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        report = root / "report"
        report.mkdir()
        (report / "ai-usage.html").write_text(
            "<html><body><header><h1>AI</h1></header><main></main></body></html>",
            encoding="utf-8",
        )
        connection = sqlite3.connect(root / "audit.db")
        try:
            connection.execute(
                "CREATE TABLE ai_provider_attempts (semantic_contract_version TEXT, estimated_cost REAL, cost_currency TEXT)"
            )
            connection.execute(
                "CREATE TABLE content_remediation_attempts (estimated_cost REAL, cost_currency TEXT)"
            )
            connection.executemany(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?)",
                [
                    ("M18-AI-SEMANTIC-v2", 0.007147, "USD"),
                    ("M24-TECHNICAL-REMEDIATION-v2", 0.004345096, "USD"),
                    ("M24-TECHNICAL-REMEDIATION-v2", None, None),
                    ("M24-TECHNICAL-REMEDIATION-v2", 0.0010792, "USD"),
                ],
            )
            connection.execute(
                "INSERT INTO content_remediation_attempts VALUES (?,?)",
                (0.003432472, "USD"),
            )
            connection.commit()
        finally:
            connection.close()

        report_navigation._enhance_ai_cost_total(report)
        html = (report / "ai-usage.html").read_text(encoding="utf-8")
        assert "0.01600377 USD" in html
        assert "Análise semântica por IA 0.007147 USD" in html
        assert "Remediação técnica por IA 0.0054243 USD" in html
        assert "Remediação textual por IA 0.00343247 USD" in html
        assert "Consumo projetado total" not in html


def test_ai_usage_nested_badges_and_exchange_log_pre_are_transparent() -> None:
    from rasai import report_ai_runtime_enrichment, report_semantics

    _install_ai_usage_presentation_fix()
    assert "background:transparent" in report_ai_runtime_enrichment._RUNTIME_STYLE
    assert ".result-tag .badge.good" in report_semantics.SEMANTIC_CSS


def test_scoring_active_wording_is_weighted() -> None:
    from rasai import report_registry

    _install_scoring_wording_fix()
    stale = (
        "<p><strong>Overall:</strong> média aritmética de igual peso das dimensões aplicáveis "
        "que possuem valor e não estão em <code>NOT_CONSOLIDATED</code>. Uma dimensão legitimamente "
        "<code>NOT_APPLICABLE</code> sai do denominador.</p>"
    )
    current = report_registry._normalize_known_legacy_wording(stale, page_name="scoring.html")
    assert "média aritmética de igual peso" not in current
    assert "média ponderada pelos pesos versionados" in current


def test_search_report_explains_disabled_content_comparison() -> None:
    from rasai.search_intelligence import reporting

    _install_search_comparison_guidance()
    analysis = {
        "comparison_status": "CONTENT_COMPARISON_DISABLED",
        "methodology_version": "DETERMINISTIC-CORRELATIONAL-001",
        "artifact_reference": None,
        "candidate_count": 0,
        "gaps": "[]",
        "limitations": "[]",
    }
    html = reporting._competitive_section(analysis, [], [])
    assert "Por que as listas estão vazias" in html
    assert "classificação determinística dos resultados SERP" in html
    assert "Nenhuma página concorrente/cliente foi adquirida" in html
