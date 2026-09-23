"""Friendly CAT-05 execution-scope presentation.

Search execution inputs are not environment variables. This module makes them first-class
operator concepts without changing the Search runtime contract or persistence model.
"""
from __future__ import annotations

from typing import Any

from rasai.console_ui import CYAN, DIM, paint
from rasai.configuration_value_labels import configuration_value_info
from rasai.console_ui_catalog import info, section

_INSTALLED = False


def _friendly_device(value: object) -> str:
    normalized = str(value or "mobile").strip().casefold()
    if normalized == "desktop":
        return "Desktop"
    if normalized == "both":
        return "Mobile + Desktop"
    return "Mobile"


def render_search_scope(state: Any) -> None:
    """Render execution-owned Search inputs separately from reusable service settings."""
    from rasai.console_catalog_plan import raw_capability_status

    queries = tuple(getattr(state, "search_queries", ()) or ())
    depth = max(int(getattr(state, "search_depth", 20) or 20), 1)
    region = str(getattr(state, "search_region", "") or "").strip()

    section("ESCOPO DESTA EXECUÇÃO")
    info("URL / entrada", getattr(state, "target", "") or "<não informada>")
    info("Idioma / mercado", f"{getattr(state, 'language', '-')} / {getattr(state, 'market', '-')}")
    info("Device da auditoria", _friendly_device(getattr(state, "device", "mobile")))

    print()
    print(paint("O QUE PESQUISAR", CYAN, bold=True))
    info("Termos de busca", "; ".join(queries) if queries else "<não configurados>")
    info("Quantidade de termos", len(queries))
    info("Localidade", region or "<usa apenas país/mercado da auditoria>")
    info("Profundidade desejada", f"Top {depth}")
    info("Dispositivo da busca", _friendly_device(getattr(state, "search_device", "mobile")))
    info(
        "Análise de concorrentes",
        "Ativada" if bool(getattr(state, "search_competitive", True)) else "Desativada",
    )
    info(
        "Comparação de conteúdo",
        "Ativada" if bool(getattr(state, "search_compare_content", False)) else "Desativada",
    )
    info("Máx. páginas concorrentes", int(getattr(state, "search_max_content_pages", 3)))
    info("Timeout de conteúdo", f"{float(getattr(state, 'search_content_timeout_seconds', 10.0)):g} s")
    info("Máx. bytes por página", int(getattr(state, "search_content_max_bytes", 2_000_000)))
    info("Máx. redirects", int(getattr(state, "search_content_max_redirects", 5)))
    info(
        "IA competitiva",
        "Ativada" if bool(getattr(state, "search_ai_competitive", False)) else "Desativada",
    )
    info(
        "Contexto YMYL da IA",
        configuration_value_info(
            "SEARCH_YMYL_MODE",
            str(getattr(state, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
        ),
    )
    print(
        paint(
            "Estes valores pertencem à próxima execução. 'Profundidade desejada' é o Top N consultado; não é o limite máximo permitido pelo serviço. A IA competitiva usa exclusivamente a IA principal configurada e só executa após a comparação determinística e o selo de evidências.",
            DIM,
        )
    )

    print()
    print(paint("GOOGLE SEARCH CONSOLE", CYAN, bold=True))
    status, detail = raw_capability_status(state, "google-search-console")
    info("Estado para a URL atual", status)
    if detail:
        print(paint(f"  {detail}", DIM))
    print(
        paint(
            "GSC e SERP são fontes independentes. Configurar ou falhar uma delas não configura nem invalida automaticamente a outra.",
            DIM,
        )
    )


def install() -> None:
    """Replace only the CAT-05 context renderer in the public catalog UI."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_catalog_ui as catalog_ui

    original = catalog_ui._render_context
    if getattr(original, "_rasai_search_scope_presentation", False):
        _INSTALLED = True
        return

    def render_context(state: Any, catalog: Any) -> None:
        if str(getattr(catalog, "id", "")) == "CAT-05":
            render_search_scope(state)
            return
        original(state, catalog)

    render_context._rasai_search_scope_presentation = True  # type: ignore[attr-defined]
    render_context._rasai_original = original  # type: ignore[attr-defined]
    catalog_ui._render_context = render_context
    _INSTALLED = True
