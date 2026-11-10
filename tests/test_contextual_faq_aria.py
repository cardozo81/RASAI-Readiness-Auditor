"""ARIA FAQ v3: same DOM trace, additive evidence and no false site absence."""
from rasai.contextual_content import _Markup, observe_content
from rasai.contextual_faq_aria import qualify_capture, report_overlay
from tests.test_contextual_content import observed


def _trace(html):
    parser = _Markup(html)
    parser.feed(html)
    parser.close()
    return parser


def test_five_controls_one_answer_four_unobserved_without_changing_v1():
    controls = "".join(
        '<a role="button" aria-expanded="' + ("true" if i == 1 else "false") +
        '" aria-controls="answer' + str(i) + '">Como funciona o produto ' + str(i) + '?</a>'
        for i in range(1, 6)
    )
    html = '<main><section id="faq">' + controls + '<div id="answer1"><p>Resposta documentada nesta captura.</p></div></section></main>'
    capture = observed(html)
    original = [dict(row) for row in capture["occurrences"]]
    overlay = qualify_capture(capture, _trace(html))
    assert capture["occurrences"] == original
    assert overlay["counts"] == dict(controls=5, answer_present=1,
                                     not_observed_nd=4, ambiguous=0, excluded=0)
    assert len(overlay["controls"]) == 5
    assert [r["status"] for r in overlay["controls"]] == [
        "ANSWER_PRESENT_IN_DOM", *["NOT_OBSERVED_ND"] * 4]
    assert overlay["controls"][0]["answer"].startswith("Resposta documentada")
    assert overlay["controls"][1]["answer"] is None
    assert overlay["controls"][0]["source_sha256"] == capture["source_sha256"]
    capture["faq_aria_overlay_v3"] = overlay
    assert report_overlay([capture])["counts"] == overlay["counts"]


def test_closed_panel_with_dom_answer_is_present_not_missing():
    html = '<main><section id="faq"><a role="button" aria-controls="a" aria-expanded="false">Qual proteção?</a><div id="a" hidden>Proteção observada.</div></section></main>'
    row = qualify_capture(observed(html), _trace(html))["controls"][0]
    assert row["status"] == "ANSWER_PRESENT_IN_DOM"
    assert row["aria_expanded"] == "false"


def test_menu_inside_main_and_non_faq_control_excluded():
    html = '<main><section><a role="button" aria-controls="links" aria-expanded="false">Menu</a><div id="links"><a href="/a">A</a><a href="/b">B</a></div></section></main>'
    result = qualify_capture(observed(html), _trace(html))
    assert result["counts"]["excluded"] == 1


def test_duplicate_id_invalid_state_and_markup_unavailable_abstain():
    html = '<main><div id="faq"><a role="button" aria-controls="dup" aria-expanded="false">Qual prazo?</a><span id="dup">A</span><span id="dup">B</span><a role="button" aria-controls="outro" aria-expanded="maybe">Como?</a></div></main>'
    overlay = qualify_capture(observed(html), _trace(html))
    assert overlay["counts"]["ambiguous"] == 2
    assert all(item["status"] == "INVALID_OR_AMBIGUOUS_ND" for item in overlay["controls"])
    assert qualify_capture(observed(html))["counts"]["controls"] is None
    assert report_overlay([observed(html)])["counts"]["controls"] is None


def test_details_summary_v1_not_promoted_to_aria():
    html = '<main><details><summary>Como funciona?</summary><p>Resposta.</p></details></main>'
    assert qualify_capture(observed(html), _trace(html))["counts"]["controls"] == 0
