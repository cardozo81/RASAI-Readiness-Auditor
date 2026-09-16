from __future__ import annotations

from rasai.catalog_report_analysis import _rationale_parts, _technical_work_status
from rasai.catalog_report_contract import CATALOG_REPORT_PAGES
from rasai.catalog_report_presentation import _confidence_label, _shell, _table
from rasai.improvement_exchange_capture import _mark_latest_as_improvement
from rasai.ai_exchange_log import AiExchangeRecorder
from datetime import datetime, timezone


def test_primary_labels_hide_internal_unavailable_and_work_status() -> None:
    assert _confidence_label("UNAVAILABLE") == "Sem dados para estimar"
    assert _technical_work_status("SUCCESS") == "Etapa concluída"


def test_interactive_table_has_sorting_and_ten_row_pagination_contract() -> None:
    rows = [(index, f"item-{index}") for index in range(1, 22)]
    html = _table(("Ordem", "Item"), rows, sortable=True, page_size=10)
    assert "data-interactive-table='true'" in html
    assert "data-sortable='true'" in html
    assert "data-page-size='10'" in html
    assert "data-table-prev" in html
    assert "data-table-next" in html


def test_catalog_shell_uses_product_timezone_presentation() -> None:
    page = CATALOG_REPORT_PAGES[0]
    html = _shell(
        page,
        "AUD-TIME",
        "<p>2026-09-16T11:57:02+00:00</p><pre>2026-09-16T11:57:02+00:00</pre>",
    )
    assert "16/09/2026 08:57:02 (America/Sao_Paulo)" in html
    # Technical/raw blocks keep their original persisted timestamp.
    assert "<pre>2026-09-16T11:57:02+00:00</pre>" in html


def test_remediation_rationale_is_split_into_human_sections() -> None:
    parts = _rationale_parts(
        "Degradação/risco atual: barreira presente.\n"
        "Benefício esperado se aplicado: navegação mais clara.\n"
        "Justificativa técnica: regra automatizada falhou."
    )
    assert parts["risk"] == "barreira presente."
    assert parts["benefit"] == "navegação mais clara."
    assert parts["technical"] == "regra automatizada falhou."


def test_deep_analysis_exchange_gets_stable_purpose_label() -> None:
    recorder = AiExchangeRecorder()
    recorder.append_exchange(
        provider="OPENAI",
        model="gpt-test",
        endpoint="https://example.invalid/v1/responses",
        body=b'{"model":"gpt-test","text":{"format":{"name":"rasai_improvement_intelligence"}}}',
        started_at=datetime.now(timezone.utc),
        duration_ms=10,
        outcome="RESPONSE",
        response={"ok": True},
    )
    assert recorder.exchanges[-1].purpose == "AI_REQUEST"
    _mark_latest_as_improvement(recorder)
    assert recorder.exchanges[-1].purpose == "IMPROVEMENT_INTELLIGENCE"
