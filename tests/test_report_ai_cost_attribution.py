from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.report_ai_cost_attribution import enrich_ai_cost_attribution


def _create_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE ai_provider_attempts (
                audit_id TEXT, attempt_id TEXT, url TEXT, device TEXT,
                provider TEXT, model TEXT, semantic_contract_version TEXT, status TEXT,
                input_tokens INTEGER, cached_input_tokens INTEGER, output_tokens INTEGER,
                reasoning_tokens INTEGER, total_tokens INTEGER,
                estimated_cost REAL, cost_currency TEXT
            );
            CREATE TABLE content_remediation_attempts (
                audit_id TEXT, attempt_id TEXT, url TEXT, device TEXT,
                provider TEXT, model TEXT, contract_version TEXT, status TEXT,
                input_tokens INTEGER, cached_input_tokens INTEGER, output_tokens INTEGER,
                reasoning_tokens INTEGER, total_tokens INTEGER,
                estimated_cost REAL, cost_currency TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                # Same Mobile report: first provider fails contract after measurable usage,
                # AUTO falls back to a second provider that succeeds. Both costs belong here.
                ("AUD-1", "A1", "https://example.test/a", "MOBILE", "OPENAI", "model-a", "M18-SEMANTIC-22-v1", "CONTRACT_ERROR", 100, 10, 20, 5, 120, 0.10, "USD"),
                ("AUD-1", "A1B", "https://example.test/a", "MOBILE", "DEEPSEEK", "model-b", "M18-SEMANTIC-22-v1", "SUCCESS", 80, 0, 20, 0, 100, 0.07, "USD"),
                ("AUD-1", "A2", "https://example.test/a", "DESKTOP", "OPENAI", "model-a", "M24-TECHNICAL-REMEDIATION-v2", "SUCCESS", 200, 0, 40, 0, 240, 0.20, "USD"),
                ("AUD-1", "A3", "https://example.test/a", "-", "OPENAI", "model-a", "IMPROVEMENT-INTELLIGENCE-001", "SUCCESS", 300, 0, 50, 0, 350, 0.30, "USD"),
                ("AUD-1", "A4", "https://example.test/a", "-", "OPENAI", "model-a", "SOURCE-QUALITY-AI-v1", "SUCCESS", 400, 0, 60, 0, 460, 0.50, "USD"),
                # Unknown future contract must remain visible instead of disappearing.
                ("AUD-1", "A5", "https://example.test/a", "-", "QWEN", "model-q", "FUTURE-AI-999", "SUCCESS", 50, 0, 10, 0, 60, 0.08, "USD"),
            ),
        )
        connection.execute(
            "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("AUD-1", "C1", "https://example.test/a", "MOBILE", "OPENAI", "model-a", "M20-CONTENT-REMEDIATION-v3", "SUCCESS", 500, 0, 70, 0, 570, 0.40, "USD"),
        )
        connection.commit()
    finally:
        connection.close()


def _write_report(path: Path) -> None:
    path.write_text("<html><body><main><h1>Report</h1></main></body></html>", encoding="utf-8")


def test_cost_attribution_explains_multi_provider_fallback_and_owner(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    filenames = (
        "index.html",
        "mobile.html",
        "context.html",
        "crawling-discovery.html",
        "improvement-intelligence.html",
        "content-suggestions.html",
        "references.html",
        "ai-usage.html",
    )
    for filename in filenames:
        _write_report(report_dir / filename)
    database = tmp_path / "audit.db"
    _create_db(database)
    workspace = SimpleNamespace(root=tmp_path, database=database)

    enrich_ai_cost_attribution(audit_id="AUD-1", workspace=workspace)  # type: ignore[arg-type]

    mobile = (report_dir / "mobile.html").read_text(encoding="utf-8")
    assert "data-ai-cost-attribution='true'" in mobile
    assert "0.17000000 USD" in mobile
    assert "OPENAI" in mobile and "DEEPSEEK" in mobile
    assert "model-a" in mobile and "model-b" in mobile
    assert "Providers/modelos envolvidos</small><strong>2" in mobile
    assert "CONTRACT_ERROR" not in mobile  # local summary stays user-oriented
    assert "Análise semântica do contexto Mobile" in mobile
    assert "Todas as tentativas são consideradas, inclusive as que antecederam um fallback" in mobile

    expected_costs = {
        "crawling-discovery.html": "0.20000000 USD",
        "improvement-intelligence.html": "0.30000000 USD",
        "context.html": "0.50000000 USD",
        "content-suggestions.html": "0.40000000 USD",
        "index.html": "0.08000000 USD",
    }
    for filename, cost in expected_costs.items():
        html = (report_dir / filename).read_text(encoding="utf-8")
        assert cost in html

    index = (report_dir / "index.html").read_text(encoding="utf-8")
    assert "Contrato de IA ainda sem regra específica" in index
    assert "QWEN" in index

    references = (report_dir / "references.html").read_text(encoding="utf-8")
    assert "Sem consumo IA direto" in references
    assert "Nenhum consumo direto de IA atribuído a este relatório" in references

    ai_usage = (report_dir / "ai-usage.html").read_text(encoding="utf-8")
    assert "data-ai-cost-rollup='true'" in ai_usage
    assert "1.65000000 USD" in ai_usage
    assert "Mapa de alocação: relatório × provider/modelo" in ai_usage
    assert "Consumo global por provider/modelo" in ai_usage
    assert "Motivo da alocação" in ai_usage
    assert "CONTRACT_ERROR" in ai_usage
    assert "DEEPSEEK" in ai_usage and "QWEN" in ai_usage
    assert "https://example.test/a" in ai_usage
    assert "M20-CONTENT-REMEDIATION-v3" in ai_usage

    enrich_ai_cost_attribution(audit_id="AUD-1", workspace=workspace)  # type: ignore[arg-type]
    assert (report_dir / "mobile.html").read_text(encoding="utf-8").count(
        "data-ai-cost-attribution='true'"
    ) == 1
    assert (report_dir / "ai-usage.html").read_text(encoding="utf-8").count(
        "data-ai-cost-rollup='true'"
    ) == 1


def test_cost_attribution_handles_unknown_cost_without_hiding_attempt(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    _write_report(report_dir / "mobile.html")
    _write_report(report_dir / "ai-usage.html")
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """CREATE TABLE ai_provider_attempts (
                audit_id TEXT, attempt_id TEXT, url TEXT, device TEXT,
                provider TEXT, model TEXT, semantic_contract_version TEXT, status TEXT,
                input_tokens INTEGER, cached_input_tokens INTEGER, output_tokens INTEGER,
                reasoning_tokens INTEGER, total_tokens INTEGER,
                estimated_cost REAL, cost_currency TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("AUD-U", "U1", "https://example.test/u", "MOBILE", "MIMO", "model-m", "M18-SEMANTIC-22-v1", "ERROR", None, None, None, None, None, None, "USD"),
        )
        connection.commit()
    finally:
        connection.close()
    workspace = SimpleNamespace(root=tmp_path, database=database)

    enrich_ai_cost_attribution(audit_id="AUD-U", workspace=workspace)  # type: ignore[arg-type]

    mobile = (report_dir / "mobile.html").read_text(encoding="utf-8")
    assert "MIMO" in mobile
    assert "Não mensurável pelo provider" in mobile
    assert "1 tentativa(s) sem total retornado" in mobile


def test_cost_attribution_handles_missing_telemetry_tables(tmp_path: Path) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    _write_report(report_dir / "readiness.html")
    _write_report(report_dir / "ai-usage.html")
    database = tmp_path / "audit.db"
    sqlite3.connect(database).close()
    workspace = SimpleNamespace(root=tmp_path, database=database)

    enrich_ai_cost_attribution(audit_id="AUD-EMPTY", workspace=workspace)  # type: ignore[arg-type]

    readiness = (report_dir / "readiness.html").read_text(encoding="utf-8")
    ai_usage = (report_dir / "ai-usage.html").read_text(encoding="utf-8")
    assert "Sem consumo IA direto" in readiness
    assert "0 · sem chamadas" in readiness
    assert "Nenhuma tentativa externa de IA foi persistida" in ai_usage
