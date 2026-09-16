from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch
import os

import pytest

from rasai import console_search_intelligence as search
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_search_parameter_menu import configure_search_parameters


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
