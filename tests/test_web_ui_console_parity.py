from __future__ import annotations

from rasai.web.ui import PILOT_UI_HTML


def test_saas_ui_exposes_report_actions_for_audits_and_consolidated_history() -> None:
    html = PILOT_UI_HTML

    assert "Abrir relatório" in html
    assert "js-report" in html
    assert "openReport(b.dataset.audit)" in html

    assert "Histórico de consolidados" in html
    assert "js-cons-history" in html
    assert "/consolidated-reports/" in html
    assert "/result" in html


def test_saas_consolidated_ui_uses_same_selection_modes_and_optional_ai_as_console() -> None:
    html = PILOT_UI_HTML

    assert '<option value="ALL">Todas do intervalo</option>' in html
    assert '<option value="SUCCESS_ONLY">Somente concluídas com sucesso</option>' in html
    assert '<option value="MANUAL">Selecionar manualmente</option>' in html
    assert '<option value="none">Sem IA</option>' in html
    assert "BASE" in html
    assert "ATUAL" in html
