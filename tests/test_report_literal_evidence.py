"""Regression for literal DOM evidence in report humanization (#599).

HTML escaped DOM is source evidence, not editorial copy; preserving the exact
identifiers is necessary to match the original captured page.
"""
from __future__ import annotations

from html import unescape

from rasai.report_presentation import humanize_report_html


def test_escaped_dom_attribute_values_are_not_humanized() -> None:
    input_tag = (
        "&lt;input type=&quot;hidden&quot; "
        "id=&quot;LIFEShowcase-GTM-GTM_CPF&quot; "
        "data-testid=&quot;LIFEShowcase-GTM-GTM_CPF&quot; "
        "data-component-type=&quot;DYNAMIC_SCRIPT_INJECTION&quot; "
        "name=&quot;GTM_CPF&quot;&gt;"
    )
    html = "<div class='pre'>" + input_tag + "</div>"
    rendered = humanize_report_html(html, page_name="cat-09.html")
    assert rendered == html
    assert 'id="LIFEShowcase-GTM-GTM_CPF"' in unescape(rendered)
    assert "Condição técnica não catalogada" not in rendered


def test_escaped_dom_snippets_and_editorial_labels_are_separate() -> None:
    escaped = (
        "&lt;div id=&quot;GTM_CPF&quot; "
        "data-component-type=&quot;DYNAMIC_SCRIPT_INJECTION&quot;&gt;"
        "GTM_CPF"
        "&lt;/div&gt;"
    )
    html = "<p><strong>HTTP_ACQUISITION_INCOMPLETE</strong></p><div>" + escaped + "</div>"
    rendered = humanize_report_html(html, page_name="cat-09.html")
    assert "Aquisição HTTP incompleta" in rendered
    assert '&lt;div id=&quot;GTM_CPF&quot;' in rendered
    assert 'data-component-type=&quot;DYNAMIC_SCRIPT_INJECTION&quot;' in rendered


def test_html_escaped_scripts_remain_escaped_and_are_not_executed() -> None:
    payload = "&lt;script src=&quot;https://example.com/GTM_CPF.js&quot;&gt;&lt;/script&gt;"
    rendered = humanize_report_html("<div>" + payload + "</div>")
    assert payload in rendered
    assert "<script" not in rendered
