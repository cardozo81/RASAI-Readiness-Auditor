from __future__ import annotations

from pathlib import Path

from rasai.indicator_provenance import (
    INDICATORS,
    PROVENANCE_MARKER,
    enrich_indicator_provenance_html,
)
from rasai.report_semantics import enhance_report_html


def _shell() -> str:
    return "<html><body><header class='hero'><h1>Teste</h1></header><main></main></body></html>"


def test_device_page_exposes_evidence_role_not_duplicate_score() -> None:
    html = enrich_indicator_provenance_html(_shell(), page_name="mobile.html")
    assert PROVENANCE_MARKER in html
    assert "Evidências RASAi por dispositivo" in html
    assert "Indicadores agregados RASAi ficam exclusivamente" in html
    assert "references.html#indicator-provenance" in html


def test_central_report_semantics_pipeline_applies_provenance() -> None:
    html = enhance_report_html(_shell(), page_name="mobile.html", report_dir=Path("."))
    assert PROVENANCE_MARKER in html
    assert "Evidências RASAi por dispositivo" in html


def test_rasai_page_has_explicit_internal_methodological_nature() -> None:
    html = enrich_indicator_provenance_html(_shell(), page_name="readiness.html")
    assert "Heurística RASAi evidence-based" in html
    assert "SARI-001" in html
    assert "SCORE-GEO-002" in html


def test_external_metric_pages_are_not_presented_as_rasai_score() -> None:
    html = enrich_indicator_provenance_html(_shell(), page_name="web-performance.html")
    assert "Métricas externas definidas" in html
    assert "sem convertê-los em SARI-001" in html

    accessibility = enrich_indicator_provenance_html(_shell(), page_name="accessibility.html")
    assert "WCAG 2.2 é standard externo" in accessibility
    assert "não equivale a certificação" in accessibility


def test_apdex_separates_external_method_from_operator_threshold() -> None:
    html = enrich_indicator_provenance_html(_shell(), page_name="apdex.html")
    assert "Método Apdex externo + T configurado pelo operador" in html
    assert "perfil sintético" in html


def test_references_panel_contains_source_logic_and_internal_boundary() -> None:
    html = enrich_indicator_provenance_html(_shell(), page_name="references.html")
    assert "De onde vem cada indicador" in html
    assert "Search &amp; AI Readiness Index (SARI-001)" in html
    assert "Heurística RASAi" in html
    assert "https://www.w3.org/TR/WCAG22/" in html
    assert "https://web.dev/articles/vitals" in html
    assert "https://www.rfc-editor.org/rfc/rfc9309.html" in html
    assert "https://www.apdex.org/wp-content/uploads/2020/09/ApdexTechnicalSpecificationV11_000.pdf" in html
    assert "não homologa automaticamente o SARI-001" in html


def test_enrichment_is_idempotent_and_unknown_pages_are_untouched() -> None:
    once = enrich_indicator_provenance_html(_shell(), page_name="ai-usage.html")
    twice = enrich_indicator_provenance_html(once, page_name="ai-usage.html")
    assert once == twice
    assert enrich_indicator_provenance_html(_shell(), page_name="other.html") == _shell()


def test_inventory_has_explicit_classification_and_no_fake_external_source_for_internal_index() -> None:
    assert INDICATORS
    score = next(item for item in INDICATORS if item.indicator.startswith("Search & AI Readiness Index"))
    assert score.classification == "RASAI_HEURISTIC"
    assert score.source_url is None
    assert "SCORE-GEO-002" in score.rasai_logic
    assert all(item.classification for item in INDICATORS)
