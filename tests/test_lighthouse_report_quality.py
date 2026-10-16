from __future__ import annotations

from rasai.console_config import State, build_command
from rasai.console_execution_profiles import clear_profile, effective_profile, set_profile
from rasai.report_semantics import _lighthouse_score_state, _threshold_state


def test_complete_safe_profile_really_enables_full_lighthouse_transport() -> None:
    state = State(target="https://example.test/")
    session = set_profile(state, profile_id="complete-safe")
    try:
        with effective_profile(state, session):
            assert state.web_performance is True
            assert state.lighthouse_categories == (
                "performance,accessibility,best-practices,seo,agentic-browsing"
            )
            command = build_command(state)
            assert "--web-performance" in command
            index = command.index("--lighthouse-categories")
            assert command[index + 1] == state.lighthouse_categories
    finally:
        clear_profile(state)


def test_lighthouse_and_cwv_color_boundaries_are_canonical() -> None:
    assert _lighthouse_score_state("90/100", primary=True)[0] == "good"
    assert _lighthouse_score_state("89/100", primary=True)[0] == "warn"
    assert _lighthouse_score_state("50/100", primary=True)[0] == "warn"
    assert _lighthouse_score_state("49/100", primary=True)[0] == "bad"

    assert _threshold_state("2500 ms", good=2500.0, needs=4000.0, primary=True)[0] == "good"
    assert _threshold_state("2501 ms", good=2500.0, needs=4000.0, primary=True)[0] == "warn"
    assert _threshold_state("4001 ms", good=2500.0, needs=4000.0, primary=True)[0] == "bad"
    assert _threshold_state("200 ms", good=200.0, needs=500.0, primary=True)[0] == "good"
    assert _threshold_state("500 ms", good=200.0, needs=500.0, primary=True)[0] == "warn"
    assert _threshold_state("501 ms", good=200.0, needs=500.0, primary=True)[0] == "bad"
    assert _threshold_state("0.1", good=0.1, needs=0.25, primary=True)[0] == "good"
    assert _threshold_state("0.25", good=0.1, needs=0.25, primary=True)[0] == "warn"
    assert _threshold_state("0.251", good=0.1, needs=0.25, primary=True)[0] == "bad"
