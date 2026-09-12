from __future__ import annotations

from rasai.report_scale_ux import enhance_report_html_for_scale


def test_scale_ux_is_idempotent_and_activates_from_two_urls() -> None:
    html = "<html><head></head><body><main></main></body></html>"
    once = enhance_report_html_for_scale(html)
    twice = enhance_report_html_for_scale(once)

    assert once == twice
    assert once.count("rasai-scale-ux-v1") == 1
    assert once.count("rasai-scale-ux-script-v1") == 1
    assert "URL_THRESHOLD=2" in once
    assert "Todas as URLs" in once
    assert "Filtrar contexto" in once
    assert "Itens por página" in once


def test_scale_ux_preserves_original_report_payload_and_indexes_all_item_urls() -> None:
    payload = (
        "<html><head><title>Relatório</title></head><body>"
        "<article class='page-card'><h3 class='page-url'>https://example.test/a</h3>"
        "<p>Também afeta https://example.test/b</p></article>"
        "<article class='page-card'><h3 class='page-url'>https://example.test/c</h3></article>"
        "</body></html>"
    )
    enhanced = enhance_report_html_for_scale(payload)

    assert "https://example.test/a" in enhanced
    assert "https://example.test/b" in enhanced
    assert "https://example.test/c" in enhanced
    assert enhanced.count("class='page-card'") == 2
    assert "URL_THRESHOLD=2" in enhanced
    assert "urlsForItem" in enhanced
    assert "indexed.urls.includes(state.url)" in enhanced
    assert "LARGE_CARD_FALLBACK=20" in enhanced


def test_filter_index_is_stable_when_pagination_hides_rows() -> None:
    html = enhance_report_html_for_scale("<html><head></head><body><table><tbody></tbody></table></body></html>")

    assert "const stableText=item=>String((item&&item.textContent)||'')" in html
    assert "const itemCache=new WeakMap()" in html
    assert "const indexed=indexForItem(item)" in html
    assert "item.innerText" not in html


def test_population_cards_are_grouped_responsively_without_changing_values() -> None:
    payload = (
        "<html><head></head><body><section>"
        "<article class='population-card'>https://example.test/a 0.900</article>"
        "<article class='population-card'>https://example.test/b 0.700</article>"
        "</section></body></html>"
    )
    enhanced = enhance_report_html_for_scale(payload)

    assert "rasai-population-grid" in enhanced
    assert "groupPopulationCards" in enhanced
    assert "repeat(auto-fit" in enhanced
    assert "https://example.test/a 0.900" in enhanced
    assert "https://example.test/b 0.700" in enhanced


def test_scale_ux_keeps_single_url_as_simple_layout_contract() -> None:
    html = enhance_report_html_for_scale(
        "<html><head></head><body>"
        "<article class='page-card'><h3 class='page-url'>https://example.test/a</h3></article>"
        "</body></html>"
    )

    assert "URL_THRESHOLD=2" in html
    assert "urlsFor(items).length>=URL_THRESHOLD" in html


def test_reports_receive_consistent_section_outline_when_content_is_structured() -> None:
    payload = (
        "<html><head></head><body><main><header class='hero'><h1>Relatório</h1></header>"
        "<section><h2>Resumo executivo</h2></section>"
        "<section><h2>Evidências por URL</h2></section>"
        "<section><h2>Metodologia e limites</h2></section>"
        "</main></body></html>"
    )
    enhanced = enhance_report_html_for_scale(payload)

    assert "rasai-report-outline" in enhanced
    assert "Neste relatório" in enhanced
    assert "Seções do relatório" in enhanced
    assert "buildOutline" in enhanced
    assert "rasai-section-anchor" in enhanced
    assert "headings.length<3" in enhanced


def test_report_outline_is_hidden_for_print_and_does_not_change_source_headings() -> None:
    payload = (
        "<html><head></head><body><main>"
        "<h2>A</h2><h2>B</h2><h2>C</h2>"
        "</main></body></html>"
    )
    enhanced = enhance_report_html_for_scale(payload)

    assert "@media print" in enhanced
    assert ".rasai-report-outline{display:none!important}" in enhanced
    assert payload.count("<h2>") == 3
    assert enhanced.count("<h2>") == 3
