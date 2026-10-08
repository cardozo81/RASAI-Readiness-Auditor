"""#318: explicit SERP->Perplexity copy never implies an external call."""
from __future__ import annotations

from unittest.mock import patch

from rasai import console_search_intelligence as search
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_search_parameter_menu import _copy_serp_terms_to_perplexity


def test_explicit_serp_copy_requires_affirmative_confirmation(capsys) -> None:
    state = SearchConsoleState(search_queries=("seguro de vida", "previdência"))
    with patch("builtins.input", return_value="N"):
        _copy_serp_terms_to_perplexity(search, state)
    assert state.perplexity_queries == ()
    assert "Sem autorização" in capsys.readouterr().out


def test_serp_copy_preserves_explicit_scope_without_network(monkeypatch) -> None:
    state = SearchConsoleState(
        search_queries=("seguro de vida", "previdência"),
        perplexity_search_type="fast",
    )
    monkeypatch.setattr(
        search, "execute_perplexity_search",
        lambda *args, **kw: (_ for _ in ()).throw(AssertionError("HTTP is not allowed")),
    )
    with patch("builtins.input", return_value="S"):
        _copy_serp_terms_to_perplexity(search, state)
    assert state.perplexity_queries == state.search_queries
    assert state.perplexity_search_type == "fast"
    assert state.perplexity_last_status in {"PENDING", "DISABLED_BY_USER"}


def test_serp_copy_never_truncates_budget_or_invents_queries(capsys) -> None:
    state = SearchConsoleState(search_queries=())
    with patch("builtins.input", side_effect=AssertionError("no prompt")):
        _copy_serp_terms_to_perplexity(search, state)
    assert state.perplexity_queries == ()
    assert "Não há termos" in capsys.readouterr().out

    state.search_queries = ("a", "b", "c", "d", "e", "f")
    with patch("builtins.input", side_effect=AssertionError("no prompt")):
        _copy_serp_terms_to_perplexity(search, state)
    assert state.perplexity_queries == ()
    assert "limite Perplexity" in capsys.readouterr().out


def test_post_aud_console_action_needs_explicit_billing_confirmation(monkeypatch, capsys) -> None:
    from pathlib import Path
    from types import SimpleNamespace
    from rasai.console_search_parameter_menu import _external_geo_supplement
    from rasai.persistence import AuditWorkspace
    from rasai import geo_post_audit_complement

    state = SearchConsoleState(perplexity_queries=("seguro de vida",))
    calls: list[dict] = []

    def fake_run(workspace, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status="SUCCESS", request_executed=True,
                               billability="TRUE", directory=Path("/fake/supplement"))

    monkeypatch.setattr(AuditWorkspace, "open", classmethod(
        lambda cls, path: SimpleNamespace(root=Path("/fake/AUD-TEST-1"))
    ))
    monkeypatch.setattr(geo_post_audit_complement, "run_post_audit_geo_supplement", fake_run)
    with patch("builtins.input", side_effect=["/fake/AUD-TEST-1", "new-intent", "S", "N"]):
        _external_geo_supplement(state)
    assert not calls
    with patch("builtins.input", side_effect=["/fake/AUD-TEST-1", "new-intent", "S", "S"]):
        _external_geo_supplement(state)
    assert len(calls) == 1
    assert calls[0]["explicit_cost_authorization"] is True
    assert calls[0]["search_options"]["country"] == "BR"
    assert calls[0]["search_options"]["max_results"] == 10
    assert calls[0]["audit_id"] == "AUD-TEST-1"
    assert "Operação não autorizada" in capsys.readouterr().out


def test_post_aud_console_action_requires_queries_before_filesystem(monkeypatch, capsys) -> None:
    from rasai.console_search_parameter_menu import _external_geo_supplement
    state = SearchConsoleState(perplexity_queries=())
    with patch("builtins.input", side_effect=AssertionError("no IO allowed")):
        _external_geo_supplement(state)
    assert "Configure primeiro queries" in capsys.readouterr().out
