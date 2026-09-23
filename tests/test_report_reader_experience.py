from __future__ import annotations

import sqlite3

from rasai.report_reader_experience import (
    build_report_experience_context,
    enhance_consolidated_experience,
    enhance_report_experience,
)


def _context(*, status: str = "SUCCESS", url_count: int = 3):
    return {
        "audit_id": "AUD-TEST",
        "contract": {
            "processing_status": "COMPLETE",
            "score_status": "FINAL",
            "report_status": "FINAL",
            "consolidation_eligible": 1,
            "required_items": 2,
            "successful_items": 2,
            "pending_items": 0,
            "blocked_items": 0,
            "expired_items": 0,
            "reprocess_count": 0,
        },
        "work_items": (
            {
                "component": "WEB_PERFORMANCE",
                "scope_key": "AUDIT",
                "required": 1,
                "status": status,
                "attempt_count": 1,
                "retryable": 1,
                "last_error_class": None,
                "last_error_code": None,
            },
        ),
        "url_count": url_count,
        "devices": ("MOBILE", "DESKTOP"),
    }


def test_audit_page_gets_context_status_and_transparency_dialog() -> None:
    html = "<html><head></head><body><main class='app-main'><header><h1>Web Performance</h1></header><footer class='footer'>fim</footer></main></body></html>"
    rendered = enhance_report_experience(html, filename="web-performance.html", context=_context())

    assert "Estado desta análise" in rendered
    assert "Concluída" in rendered
    assert "3 URLs" in rendered
    assert "Mobile + Desktop" in rendered
    assert "Entenda esta página" in rendered
    assert "Dados previstos para esta página" in rendered
    assert "Estado materializado nesta auditoria" in rendered
    assert "Origem dos dados" in rendered
    assert "PageSpeed API" in rendered
    assert "Dados persistidos · sem recálculo no HTML" in rendered


def test_failed_dependency_is_not_presented_as_success() -> None:
    html = "<html><head></head><body><main class='app-main'><header><h1>Web Performance</h1></header></main></body></html>"
    context = _context(status="FAILED_RETRYABLE", url_count=1)
    rendered = enhance_report_experience(html, filename="web-performance.html", context=context)

    assert "Não concluída" in rendered
    assert "Falhou; pode ser reprocessado" in rendered
    assert "1 URL" in rendered


def test_dashboard_adds_reader_path_without_recalculating_data() -> None:
    html = "<html><head></head><body><main class='app-main'><header><h1>Visão geral</h1></header><div id='score'>82</div></main></body></html>"
    rendered = enhance_report_experience(html, filename="index.html", context=_context())

    assert "Auditoria concluída" in rendered
    assert "Entender a avaliação" in rendered
    assert "Ver o que corrigir" in rendered
    assert "Verificar o que mudou" in rendered
    assert "<div id='score'>82</div>" in rendered


def test_reader_layer_is_idempotent() -> None:
    html = "<html><head></head><body><main class='app-main'><header><h1>Web Performance</h1></header></main></body></html>"
    first = enhance_report_experience(html, filename="web-performance.html", context=_context())
    second = enhance_report_experience(first, filename="web-performance.html", context=_context())

    assert second == first
    assert second.count("rasai-reader-experience-v1") == 1
    assert second.count("data-rasai-page-help='true'") == 1
    assert second.count("data-rasai-analysis-status='true'") == 1


def test_accessibility_state_follows_requested_lighthouse_category() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE web_performance_runs(
          audit_id TEXT, enabled INTEGER, status TEXT, reason TEXT, categories TEXT
        );
        INSERT INTO web_performance_runs VALUES(
          'AUD-TEST',1,'SUCCESS',NULL,'["performance"]'
        );
        CREATE TABLE web_performance_attempts(audit_id TEXT);
        INSERT INTO web_performance_attempts VALUES('AUD-TEST');
        CREATE TABLE web_performance_observations(
          audit_id TEXT, accessibility_score REAL
        );
        """
    )
    context = build_report_experience_context(connection, "AUD-TEST")
    connection.close()

    items = [item for item in context["work_items"] if item["component"] == "ACCESSIBILITY_DATA"]
    assert len(items) == 1
    assert items[0]["status"] == "DISABLED"

    html = "<html><head></head><body><main><header><h1>Acessibilidade</h1></header></main></body></html>"
    rendered = enhance_report_experience(html, filename="accessibility.html", context=context)
    assert "Dados não solicitados" in rendered
    assert "ACCESSIBILITY_CATEGORY_NOT_REQUESTED" in rendered


def test_standards_can_be_complete_with_external_service_limitation() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE standards_metric_observations(audit_id TEXT);
        INSERT INTO standards_metric_observations VALUES('AUD-TEST');
        CREATE TABLE standards_service_runs(
          audit_id TEXT, service_id TEXT, requested INTEGER, configured INTEGER,
          effective_enabled INTEGER, state TEXT, targets_attempted INTEGER,
          targets_succeeded INTEGER
        );
        INSERT INTO standards_service_runs VALUES(
          'AUD-TEST','W3C_HTML',1,1,1,'ERROR',1,0
        );
        """
    )
    context = build_report_experience_context(connection, "AUD-TEST")
    connection.close()

    html = "<html><head></head><body><main><header><h1>Métricas e padrões</h1></header></main></body></html>"
    rendered = enhance_report_experience(html, filename="standards.html", context=context)
    assert "Concluída com limitações" in rendered
    assert "Métricas e padrões materializados" in rendered
    assert "Serviço externo de padrões" in rendered
    assert "Falhou; pode ser reprocessado" in rendered


def test_requested_standards_service_without_configuration_is_not_disabled() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE standards_metric_observations(audit_id TEXT);
        INSERT INTO standards_metric_observations VALUES('AUD-TEST');
        CREATE TABLE standards_service_runs(
          audit_id TEXT, service_id TEXT, requested INTEGER, configured INTEGER,
          effective_enabled INTEGER, state TEXT, targets_attempted INTEGER,
          targets_succeeded INTEGER
        );
        INSERT INTO standards_service_runs VALUES(
          'AUD-TEST','GOOGLE_SEARCH_CONSOLE',1,0,0,'NOT_CONFIGURED',0,0
        );
        """
    )
    context = build_report_experience_context(connection, "AUD-TEST")
    connection.close()

    external = [item for item in context["work_items"] if item["component"] == "STANDARDS_EXTERNAL"]
    assert len(external) == 1
    assert external[0]["status"] == "NOT_CONFIGURED"

    html = "<html><head></head><body><main><header><h1>Métricas e padrões</h1></header></main></body></html>"
    rendered = enhance_report_experience(html, filename="standards.html", context=context)
    assert "Configuração necessária" in rendered
    assert "Não solicitado" not in rendered


def test_consolidated_gets_same_status_language_and_help() -> None:
    html = "<html><head></head><body><main><header><h1>Consolidado</h1></header><footer>fim</footer></main></body></html>"
    artifact = {
        "changes": (
            {"status": "IMPROVED"},
            {"status": "REGRESSED"},
        ),
        "ai": {"requested": True, "status": "COMPLETE"},
    }
    rendered = enhance_consolidated_experience(html, artifact)

    assert "Estado do consolidado" in rendered
    assert "1 melhora(s) / resolução(ões) observada(s)" in rendered
    assert "1 regressão(ões) / novo(s) sinal(is)" in rendered
    assert "IA especialista concluída" in rendered
    assert "Entenda este relatório" in rendered
    assert "Melhora observada não prova causalidade" in rendered
