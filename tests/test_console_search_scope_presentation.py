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


def test_cat05_scope_exposes_perplexity_as_independent_external_research(monkeypatch) -> None:
    monkeypatch.delenv("PERPLEXITY_API_KEY", raising=False)
    state = SearchConsoleState(
        target="https://example.com/",
        language="pt-BR",
        market="BR",
        device="mobile",
        perplexity_queries=("rasai readiness", "search readiness"),
        perplexity_search_type="fast",
    )

    output = StringIO()
    with patch(
        "rasai.console_catalog_plan.raw_capability_status",
        return_value=("NÃO CONFIGURADO", "GSC opcional"),
    ), redirect_stdout(output):
        render_search_scope(state)

    rendered = output.getvalue()
    assert "PERPLEXITY SEARCH INTELLIGENCE" in rendered
    assert "SOLICITADA" in rendered
    assert "Quantidade de queries" in rendered
    assert "2" in rendered
    assert "FAST" in rendered
    assert "NÃO CONFIGURADA" in rendered
    assert "não substitui SERP observada" in rendered
    assert "não entra no scoring" in rendered
    assert "Persistência de queries e modo" in rendered
    assert "RASCUNHO INI - SEM SOLICITAÇÃO AUTOMÁTICA" in rendered
    assert "reutilizar e confirmar novamente" in rendered



def test_cat05_scope_after_ini_restore_explains_intent_not_inherited(tmp_path, monkeypatch):
    """#523: saving reusable SERP must not silently restore paid Perplexity."""
    from rasai import console_settings
    from rasai.console_complete_persistence import install as install_persistence
    from rasai.console_ui_refactor import _install_search_persistence

    _install_search_persistence()
    install_persistence()
    monkeypatch.setenv("RASAI_PERPLEXITY_ENABLED", "true")
    monkeypatch.setenv("PERPLEXITY_API_KEY", "NEVER_PRINT_OPERATOR_TOKEN_523")

    source = SearchConsoleState(
        target="https://example.org/policy",
        search_queries=("insurance BR",),
        perplexity_queries=("PRIVATE_PAID_QUERY_523",),
        perplexity_search_type="fast",
    )
    ini = tmp_path / "operator.ini"
    console_settings.save_console_config(source, ini)
    original = ini.read_bytes()
    assert b"PRIVATE_PAID_QUERY_523" in original
    assert b"NEVER_PRINT_OPERATOR_TOKEN_523" not in original

    fresh = SearchConsoleState()
    loaded = console_settings.load_console_config(fresh, ini)
    assert not loaded.warnings
    assert fresh.search_queries == ("insurance BR",)
    assert fresh.perplexity_queries == ()
    assert fresh.perplexity_search_type == "web"
    assert fresh.perplexity_draft_queries == ("PRIVATE_PAID_QUERY_523",)
    assert fresh.perplexity_draft_search_type == "fast"
    assert ini.read_bytes() == original

    output = StringIO()
    with patch(
        "rasai.console_catalog_plan.raw_capability_status",
        return_value=("NÃO CONFIGURADO", "GSC opcional"),
    ), redirect_stdout(output):
        render_search_scope(fresh)
    visible = output.getvalue()
    assert "RASCUNHO INI - SEM SOLICITAÇÃO AUTOMÁTICA" in visible
    assert "reutilizar e confirmar novamente" in visible
    assert "NÃO SOLICITADA" in visible
    assert "Quantidade de queries" in visible
    assert "PRIVATE_PAID_QUERY_523" not in visible
    assert "NEVER_PRINT_OPERATOR_TOKEN_523" not in visible
    assert ini.read_bytes() == original
