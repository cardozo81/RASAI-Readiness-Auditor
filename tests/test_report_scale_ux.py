from __future__ import annotations

from rasai.report_scale_ux import enhance_report_html_for_scale


def test_scale_ux_is_idempotent_and_embeds_three_url_threshold() -> None:
    html = "<html><head></head><body><main></main></body></html>"
    once = enhance_report_html_for_scale(html)
    twice = enhance_report_html_for_scale(once)

    assert once == twice
    assert once.count("rasai-scale-ux-v1") == 1
    assert once.count("rasai-scale-ux-script-v1") == 1
    assert "URL_THRESHOLD=3" in once
    assert "Todas as URLs" in once
    assert "Filtrar contexto" in once
    assert "Itens por página" in once


def test_scale_ux_preserves_original_report_payload() -> None:
    payload = (
        "<html><head><title>Relatório</title></head><body>"
        "<article class='page-card'><h3 class='page-url'>https://example.test/a</h3></article>"
        "<article class='page-card'><h3 class='page-url'>https://example.test/b</h3></article>"
        "</body></html>"
    )
    enhanced = enhance_report_html_for_scale(payload)

    assert "https://example.test/a" in enhanced
    assert "https://example.test/b" in enhanced
    assert enhanced.count("class='page-card'") == 2
    assert "LARGE_CARD_FALLBACK=20" in enhanced
