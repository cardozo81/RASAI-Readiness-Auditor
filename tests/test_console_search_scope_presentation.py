from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_search_scope_presentation import render_search_scope


def test_cat05_scope_uses_friendly_execution_concepts() -> None:
    state = SearchConsoleState(
        target="https://example.com/",
        language="pt-BR",
        market="BR",
        device="mobile",
    )
    state.search_queries = ("seguro auto", "seguro residencial")
    state.search_depth = 20
    state.search_region = "Porto Alegre, RS, Brazil"
    state.search_device = "desktop"
    state.search_competitive = True

    output = StringIO()
    with patch(
        "rasai.console_catalog_plan.raw_capability_status",
        return_value=("APTO", "property compatível com o alvo"),
    ), redirect_stdout(output):
        render_search_scope(state)

    rendered = output.getvalue()
    assert "ESCOPO DESTA EXECUÇÃO" in rendered
    assert "O QUE PESQUISAR" in rendered
    assert "Termos de busca" in rendered
    assert "seguro auto; seguro residencial" in rendered
    assert "Quantidade de termos" in rendered
    assert "Localidade" in rendered
    assert "Porto Alegre, RS, Brazil" in rendered
    assert "Profundidade desejada" in rendered
    assert "Top 20" in rendered
    assert "Dispositivo da busca" in rendered
    assert "Desktop" in rendered
    assert "Análise de concorrentes" in rendered
    assert "GOOGLE SEARCH CONSOLE" in rendered
    assert "GSC e SERP são fontes independentes" in rendered
    assert "search_queries" not in rendered
    assert "RASAI_" not in rendered
