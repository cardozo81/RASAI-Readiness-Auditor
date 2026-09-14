from __future__ import annotations

from rasai.report_reader_experience import enhance_consolidated_experience, enhance_report_experience


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
    assert "Dados que podem alimentar esta página" in rendered
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
