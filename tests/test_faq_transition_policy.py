"""Offline FAQ transition contract: no click or crawler claims."""
from rasai.faq_transition_policy import compare_faq_dom_views

URL = "https://example.test/faq"


def _html(expanded: bool, controls: int = 1) -> str:
    toggle = '<button aria-controls="faq-answer" aria-expanded="%s">Question</button>' % (
        "true" if expanded else "false"
    )
    return "<section>" + toggle * controls + (
        '<div id="faq-answer">Response visible in DOM</div>' if expanded else ""
    ) + "</section>"


def test_single_control_describes_snapshots_without_claiming_click() -> None:
    result = compare_faq_dom_views(
        _html(False), _html(True), target_id="faq-answer",
        before_url=URL, later_url=URL,
    )
    assert result["status"] == "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY"
    assert result["action_or_click_verified"] is False
    assert result["crawler_discovery_verified"] is False
    assert result["score_change_authorized"] is False


def test_duplicate_controls_fail_closed_even_if_states_agree() -> None:
    for pre, post in ((_html(False, 2), _html(True)), (_html(False), _html(True, 2))):
        result = compare_faq_dom_views(
            pre, post, target_id="faq-answer", before_url=URL, later_url=URL,
        )
        assert result["status"] == "NOT_COMPARABLE"
        assert result["reason"] == "DOM_CONTROL_OR_PANEL_AMBIGUOUS"


def test_cross_url_snapshots_cannot_be_compared() -> None:
    result = compare_faq_dom_views(
        _html(False), _html(True), target_id="faq-answer",
        before_url=URL, later_url="https://other.test/faq",
    )
    assert result["status"] == "NOT_COMPARABLE"


def test_duplicate_controls_are_ambiguous_in_observation() -> None:
    from rasai.faq_observation import inspect_faq_html

    result = inspect_faq_html(_html(False, 2))
    assert result["controls"] == 1
    assert result["ambiguous"] == 1
    assert result["collapsed"] == 0
    assert result["unmounted"] == 0
