from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
import os

import pytest

from rasai import console_search_intelligence as search
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_search_parameter_menu import (
    _edit_content_comparison,
    _render_execution_menu,
    configure_search_parameters,
)
from rasai.search_intelligence.config import SerpRuntimeConfig


@pytest.fixture(autouse=True)
def _serp_environment():
    before = dict(os.environ)
    os.environ.update(
        {
            "RASAI_SERP_MODE": "live",
            "RASAI_SERP_PROVIDER": "serpapi",
            "RASAI_SERPAPI_API_KEY": "test-key",
            "RASAI_SERP_MAX_QUERIES": "10",
            "RASAI_SERP_MAX_REQUESTS": "10",
            "RASAI_SERP_MAX_DEPTH": "20",
            "RASAI_SERP_MAX_COMPETITORS": "5",
            "RASAI_SERP_RETRIES": "1",
            "RASAI_SERP_TIMEOUT_SECONDS": "20",
            "RASAI_SERP_MIN_INTERVAL_SECONDS": "1",
        }
    )
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def _run(state: SearchConsoleState, answers: list[str]) -> str:
    output = StringIO()
    with patch("builtins.input", side_effect=answers), redirect_stdout(output):
        configure_search_parameters(search, state)
    return output.getvalue()


def test_serp_action_opens_parameter_menu_before_editing() -> None:
    state = SearchConsoleState(search_depth=20, search_device="mobile")

    rendered = _run(state, ["4", "2", "V"])

    assert "[ PROVIDER / LIMITES APLICADOS ]" in rendered
    assert "[ O QUE PESQUISAR - PRÓXIMA EXECUÇÃO ]" in rendered
    assert "1. Termos de busca" in rendered
    assert "2. Localidade" in rendered
    assert "3. Profundidade desejada" in rendered
    assert "4. Dispositivo da busca" in rendered
    assert "5. Análise de concorrentes" in rendered
    assert "6. Comparação de conteúdo" in rendered
    assert "7. Máx. páginas concorrentes" in rendered
    assert "11. IA competitiva" in rendered
    assert "12. Contexto YMYL da IA" in rendered
    assert "1. Mobile" in rendered
    assert "2. Desktop" in rendered
    assert state.search_device == "desktop"


def test_term_count_is_bounded_by_provider_request_budget() -> None:
    state = SearchConsoleState(search_depth=20)

    rendered = _run(state, ["1", "um; dois; três", "V"])

    # depth=20 means two result pages; retries=1 means four attempts per query.
    # max_requests=10 therefore permits two complete queries conservatively.
    assert "no máximo 2 termo(s)" in rendered
    assert "Valor inválido: use de 1 a 2 termo(s)" in rendered
    assert state.search_queries == ()


def test_depth_editor_limits_range_to_effective_provider_budget() -> None:
    os.environ["RASAI_SERP_MAX_DEPTH"] = "50"
    state = SearchConsoleState(search_depth=20)
    state.search_queries = ("um", "dois")

    rendered = _run(state, ["3", "21", "V"])

    assert "Faixa aceita nesta execução: 1..20" in rendered
    assert "máximo efetivo para Top 20" in rendered
    assert "Valor inválido: informe um inteiro entre 1 e 20" in rendered
    assert state.search_depth == 20


def test_region_can_be_cleared_explicitly_without_ambiguous_blank_input() -> None:
    state = SearchConsoleState(search_region="Porto Alegre, RS, Brazil")

    rendered = _run(state, ["2", "LIMPAR", "V"])

    assert "Use LIMPAR para remover a localidade" in rendered
    assert state.search_region == ""


def test_competitive_editor_uses_closed_enum_and_shows_scope() -> None:
    state = SearchConsoleState(search_competitive=True)

    rendered = _run(state, ["5", "2", "V"])

    assert "1. Ativada" in rendered
    assert "2. Desativada" in rendered
    assert "até 5 concorrente(s) observados" in rendered
    assert state.search_competitive is False


def test_disable_action_clears_terms_and_marks_search_not_requested() -> None:
    state = SearchConsoleState()
    state.search_queries = ("seguro auto",)
    state.search_last_status = "PENDING"

    _run(state, ["D", "V"])

    assert state.search_queries == ()
    assert state.search_last_status == "NOT_REQUESTED"
    assert state.search_last_detail == ""


def test_missing_live_provider_credential_blocks_parameter_changes() -> None:
    os.environ.pop("RASAI_SERPAPI_API_KEY", None)
    state = SearchConsoleState()

    rendered = _run(state, ["1", "V"])

    assert "Provider não apto" in rendered
    assert "RASAI_SERPAPI_API_KEY" in rendered
    assert state.search_queries == ()


def test_content_comparison_stays_a_closed_optional_search_input() -> None:
    state = SimpleNamespace(
        search_queries=("seguro auto",),
        search_depth=10,
        search_region="",
        search_device="mobile",
        search_competitive=True,
        search_compare_content=False,
    )
    config = SerpRuntimeConfig.from_environment()
    output = StringIO()

    with redirect_stdout(output):
        _render_execution_menu(state, config)
    assert "6. Comparação de conteúdo" in output.getvalue()

    output = StringIO()
    with patch("builtins.input", return_value="1"), redirect_stdout(output):
        _edit_content_comparison(state)

    assert "HTTP adicional" in output.getvalue()
    assert "não ativa IA" in output.getvalue()
    assert state.search_compare_content is True


def test_competitive_content_controls_are_closed_and_effective(monkeypatch) -> None:
    from rasai import console_catalog_plan as plan

    state = SearchConsoleState(search_compare_content=True, ai_provider="openai")
    monkeypatch.setattr(plan, "ai_provider_readiness", lambda current: (True, "apta"))

    rendered = _run(
        state,
        [
            "7", "4",
            "8", "12.5",
            "9", "1500000",
            "10", "2",
            "11", "1",
            "12", "2",
            "V",
        ],
    )

    assert "Faixa aceita: 0..5" in rendered
    assert state.search_max_content_pages == 4
    assert state.search_content_timeout_seconds == 12.5
    assert state.search_content_max_bytes == 1_500_000
    assert state.search_content_max_redirects == 2
    assert state.search_ai_competitive is True
    assert state.search_ymyl_mode == "ON"


def test_competitive_ai_requires_content_but_can_be_requested_without_ready_provider() -> None:
    state = SearchConsoleState(search_compare_content=False, search_ai_competitive=False)

    rendered = _run(state, ["11", "1", "V"])
    assert "ative primeiro a Comparação de conteúdo" in rendered
    assert state.search_ai_competitive is False

    state.search_compare_content = True
    rendered = _run(state, ["11", "1", "V"])
    assert "ficará pendente" in rendered
    assert state.search_ai_competitive is True



def test_all_twelve_search_inputs_round_trip_to_the_same_rendered_state(monkeypatch) -> None:
    from rasai import console_catalog_plan as plan

    state = SearchConsoleState(ai_provider="openai")
    plan._PLANS.clear()
    plan.set_selected_catalog_ids(state, ["CAT-05"])
    monkeypatch.setattr(plan, "ai_provider_readiness", lambda current: (True, "apta"))

    rendered = _run(
        state,
        [
            "1", "seguro de vida",
            "2", "Brazil",
            "3", "10",
            "4", "2",
            "5", "2",
            "6", "1",
            "7", "4",
            "8", "12.5",
            "9", "1500000",
            "10", "2",
            "11", "1",
            "12", "2",
            "V",
        ],
    )

    assert state.search_queries == ("seguro de vida",)
    assert state.search_region == "Brazil"
    assert state.search_depth == 10
    assert state.search_device == "desktop"
    assert state.search_competitive is False
    assert state.search_compare_content is True
    assert state.search_max_content_pages == 4
    assert state.search_content_timeout_seconds == 12.5
    assert state.search_content_max_bytes == 1_500_000
    assert state.search_content_max_redirects == 2
    assert state.search_ai_competitive is True
    assert state.search_ymyl_mode == "ON"
    assert plan.ai_execution_enabled(state) is True

    # The next redraw reads the same state fields that the editors changed.
    assert "Termos de busca          : seguro de vida" in rendered
    assert "Localidade               : Brazil" in rendered
    assert "Profundidade desejada    : Top 10" in rendered
    assert "Dispositivo da busca     : Desktop" in rendered
    assert "Análise de concorrentes  : Desativada" in rendered
    assert "Comparação de conteúdo   : Ativada" in rendered
    assert "IA competitiva          : Ativada" in rendered


def test_disabling_content_comparison_also_disables_dependent_competitive_ai() -> None:
    state = SearchConsoleState(
        search_compare_content=True,
        search_ai_competitive=True,
        ai_provider="openai",
    )

    rendered = _run(state, ["6", "2", "V"])

    assert state.search_compare_content is False
    assert state.search_ai_competitive is False
    assert "IA competitiva também foi desativada" in rendered


def test_competitive_ai_block_reason_remains_visible_on_redraw(monkeypatch) -> None:
    from rasai import console_catalog_plan as plan

    state = SearchConsoleState(
        search_compare_content=True,
        search_ai_competitive=False,
        ai_provider="none",
    )
    monkeypatch.setattr(plan, "ai_provider_readiness", lambda current: (False, "IA principal não configurada"))

    rendered = _run(state, ["11", "1", "V"])

    assert state.search_ai_competitive is True
    assert "IA competitiva ativada" in rendered
    assert "ficará pendente" in rendered
    assert "IA principal não configurada" in rendered
