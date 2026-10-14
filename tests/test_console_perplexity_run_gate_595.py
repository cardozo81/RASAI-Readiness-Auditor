"""#595: INI Perplexity inputs are proposed at launch, never billable on load."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import ModuleType

import pytest

from rasai.console_catalog_plan import _PLANS, set_selected_catalog_ids
from rasai.console_perplexity_run_gate_595 import (
    confirm_draft_for_this_aud, draft_pending_confirmation, install,
)
from rasai.console_search_intelligence import SearchConsoleState


@pytest.fixture(autouse=True)
def isolate_plans():
    _PLANS.clear()
    try:
        yield
    finally:
        _PLANS.clear()


def configured(monkeypatch):
    monkeypatch.setenv("RASAI_PERPLEXITY_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "opaque-test-key-never-display")
    state = SearchConsoleState(
        perplexity_draft_queries=("seguro para família",),
        perplexity_draft_search_type="fast",
    )
    set_selected_catalog_ids(state, ["CAT-05"])
    return state


def wrap_run(callback):
    module = ModuleType("fake_local_console")
    module.run_audit_from_console = callback
    install(module)
    return module.run_audit_from_console


def test_no_paid_intent_is_restored_until_execution_confirmation(monkeypatch):
    state = configured(monkeypatch)
    assert draft_pending_confirmation(state)
    assert state.perplexity_queries == ()
    assert state.perplexity_search_type == "web"
    prior = state.perplexity_last_status
    out = StringIO()
    with redirect_stdout(out):
        response = confirm_draft_for_this_aud(state, read=lambda prompt: "N")
    assert response == "N"
    assert state.perplexity_queries == ()
    assert state.perplexity_last_status == prior
    assert "seguro para família" in out.getvalue()
    assert "opaque-test-key-never-display" not in out.getvalue()


def test_decline_optional_provider_still_runs_aud_without_perplexity(monkeypatch):
    state = configured(monkeypatch)
    observed = []
    run = wrap_run(lambda current: observed.append(
        (current.perplexity_queries, current.perplexity_search_type)
    ) or 0)
    monkeypatch.setattr("builtins.input", lambda prompt="": "N")
    with redirect_stdout(StringIO()):
        assert run(state) == 0
    assert observed == [((), "web")]
    assert state.perplexity_queries == ()


def test_accept_explicitly_activates_draft_only_around_the_current_run(monkeypatch):
    state = configured(monkeypatch)
    observed = []
    run = wrap_run(lambda current: observed.append(
        (current.perplexity_queries, current.perplexity_search_type)
    ) or 0)
    answers = iter(("C", "N"))
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    with redirect_stdout(StringIO()) as output:
        assert run(state) == 0
        assert run(state) == 0
    assert observed == [(("seguro para família",), "fast"), ((), "web")]
    assert state.perplexity_queries == ()
    assert state.perplexity_draft_queries == ("seguro para família",)
    assert output.getvalue().count("CONFIRMAÇÃO PERPLEXITY") == 2


def test_general_financial_gate_can_decline_even_after_provider_acceptance(monkeypatch):
    state = configured(monkeypatch)
    invoked = []
    # Stub canonical cost gate's cancelled result. No audit/provider call allowed.
    def financial_gate(current):
        assert current.perplexity_queries == ("seguro para família",)
        invoked.append("financial_confirmation")
        return 0

    run = wrap_run(financial_gate)
    monkeypatch.setattr("builtins.input", lambda prompt="": "C")
    with redirect_stdout(StringIO()):
        assert run(state) == 0
    assert invoked == ["financial_confirmation"]
    assert state.perplexity_queries == ()
    assert state.perplexity_last_status == "NOT_REQUESTED"


def test_back_prevents_aud_execution_and_flags_post_run_as_declined(monkeypatch):
    from rasai.console_first_run_cost_preview import _DECLINED

    state = configured(monkeypatch)
    calls = []
    run = wrap_run(lambda current: calls.append("BAD") or 0)
    monkeypatch.setattr("builtins.input", lambda prompt="": "V")
    with redirect_stdout(StringIO()):
        assert run(state) == 0
    try:
        assert calls == []
        assert state.status == "READY"
        assert id(state) in _DECLINED
        assert state.perplexity_queries == ()
    finally:
        _DECLINED.discard(id(state))


def test_d_optout_blocks_launch_proposal_only_for_this_aud(monkeypatch):
    state = configured(monkeypatch)
    state.perplexity_skip_draft_this_aud = True
    assert not draft_pending_confirmation(state)
    called = []
    run = wrap_run(lambda current: called.append(current.perplexity_queries) or 0)
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": pytest.fail("unexpected consent prompt")
    )
    with redirect_stdout(StringIO()):
        assert run(state) == 0
    assert called == [()]
    assert state.perplexity_skip_draft_this_aud is False
    assert draft_pending_confirmation(state)


def test_disabled_missing_key_and_unselected_cat05_never_offer_provider(monkeypatch):
    state = configured(monkeypatch)
    set_selected_catalog_ids(state, ["CAT-01"])
    assert not draft_pending_confirmation(state)
    set_selected_catalog_ids(state, ["CAT-05"])
    monkeypatch.delenv("PERPLEXITY_API_KEY")
    assert not draft_pending_confirmation(state)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "fake")
    monkeypatch.setenv("RASAI_PERPLEXITY_ENABLED", "false")
    assert not draft_pending_confirmation(state)


def test_explicit_session_request_does_not_prompt_again(monkeypatch):
    state = configured(monkeypatch)
    state.perplexity_queries = ("termo da sessão",)
    state.perplexity_search_type = "web"
    assert not draft_pending_confirmation(state)
    observed = []
    run = wrap_run(lambda current: observed.append(current.perplexity_queries) or 0)
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": pytest.fail("manual opt-in must not prompt twice")
    )
    assert run(state) == 0
    assert observed == [("termo da sessão",)]
    assert state.perplexity_queries == ("termo da sessão",)


def test_exception_does_not_leak_paid_consent_or_mutate_saved_draft(monkeypatch):
    state = configured(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda prompt="": "C")
    def failing_runner(current):
        assert current.perplexity_queries == ("seguro para família",)
        raise RuntimeError("fake run failure")

    with pytest.raises(RuntimeError, match="fake run failure"):
        with redirect_stdout(StringIO()):
            wrap_run(failing_runner)(state)
    assert state.perplexity_queries == ()
    assert state.perplexity_search_type == "web"
    assert state.perplexity_last_status == "NOT_REQUESTED"
    assert state.perplexity_draft_queries == ("seguro para família",)
