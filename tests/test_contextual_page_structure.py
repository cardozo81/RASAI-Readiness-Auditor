"""Page title and H1-H6 trace are physical, bounded, additive, private."""
from rasai.contextual_content import _Markup
from rasai.contextual_page_structure import qualify_capture, report_overlay
from tests.test_contextual_content import observed


def _markup(html):
    parser = _Markup(html)
    parser.feed(html)
    parser.close()
    return parser


def test_title_all_heading_levels_and_v1_unchanged():
    html = ('<html><head><title>Seguro &amp; assistência</title></head><body>'
        '<nav><h2>Menu de produtos</h2></nav><main><h1>Seguro</h1>'
        '<h2>Benefícios</h2><h3>Proteções</h3><h4>Condições</h4>'
        '<h5>Documentos</h5><h6>Regulamento</h6><a href="/termos.pdf">Termos</a>'
        '</main></body></html>')
    c = observed(html)
    frozen = [dict(r) for r in c["occurrences"]]
    overlay = qualify_capture(c, _markup(html))
    assert c["occurrences"] == frozen
    assert overlay["title"]["text"] == "Seguro & assistência"
    assert overlay["title_count"] == 1
    assert overlay["heading_count"] == 7
    assert overlay["headings"][0]["scope"] == "NAVIGATION_OR_TEMPLATE"
    assert {h["tag"] for h in overlay["headings"]} == {
        "h1", "h2", "h3", "h4", "h5", "h6"}
    assert any(h["occurrence_id"] is None for h in overlay["headings"] if h["tag"] == "h6")
    assert overlay["evidence_categories"]["DOCUMENT_REFERENCE"] == 1
    c["page_structure_overlay_v3"] = overlay
    assert report_overlay([c])["counts"]["headings"] == 7


def test_no_markup_is_nd_not_zero():
    c = observed("<main><h1>Teste</h1></main>")
    missing = qualify_capture(c, None)
    assert missing["heading_count"] is None
    assert report_overlay([c])["counts"]["headings"] is None


def test_heading_caps_do_not_displace_v1_or_invent_absence():
    html = "<main>" + "<h2>Texto comprovado</h2>" * 55 + "</main>"
    c = observed(html)
    qualified = qualify_capture(c, _markup(html))
    assert qualified["heading_count"] == 55
    assert len(qualified["headings"]) == 48
    assert qualified["headings_omitted"] == 7
    assert "HEADING_LIMIT_PARTIAL" in qualified["limitations"]
