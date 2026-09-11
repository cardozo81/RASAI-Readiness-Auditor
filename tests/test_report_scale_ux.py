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

    # Regression: innerText depends on layout/display. Once pagination set display:none,
    # hidden rows returned empty text and later URL selections falsely found no data.
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

    # The controller is embedded globally, but its runtime threshold only activates
    # URL filtering when at least two distinct URLs exist in the same collection.
    assert "URL_THRESHOLD=2" in html
    assert "urlsFor(items).length>=URL_THRESHOLD" in html
