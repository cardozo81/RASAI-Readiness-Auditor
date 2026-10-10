"""Read-only human-facing Perplexity readiness for the next audit (#318).

Enabled + credential does not authorize a commercial Search API request. The
operator must explicitly supply Perplexity queries. This helper does not
mutate a pending request, open the network, or infer intent from SERP terms.
"""
from __future__ import annotations

from typing import Any, Mapping
import os

_FILTERS = (
    "RASAI_PERPLEXITY_COUNTRY",
    "RASAI_PERPLEXITY_SEARCH_LANGUAGE_FILTER",
    "RASAI_PERPLEXITY_SEARCH_DOMAIN_FILTER",
    "RASAI_PERPLEXITY_SEARCH_RECENCY_FILTER",
    "RASAI_PERPLEXITY_SEARCH_AFTER_DATE",
    "RASAI_PERPLEXITY_SEARCH_BEFORE_DATE",
    "RASAI_PERPLEXITY_LAST_UPDATED_AFTER",
    "RASAI_PERPLEXITY_LAST_UPDATED_BEFORE",
    "RASAI_PERPLEXITY_MAX_CONTENT_UNITS",
    "RASAI_PERPLEXITY_MAX_CONTENT_UNITS_PER_PAGE",
)


def inspect_perplexity_readiness(
    state: Any, *, environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Report configuration plus per-AUD opt-in, without leaking credentials."""
    env = os.environ if environment is None else environment
    from rasai.console_search_intelligence import perplexity_enabled
    active = perplexity_enabled(env)
    key_present = bool(str(env.get("PERPLEXITY_API_KEY") or "").strip())
    requests = tuple(getattr(state, "perplexity_queries", ()) or ())
    kind = str(getattr(state, "perplexity_search_type", "web") or "web").strip().upper()
    requested = bool(requests)
    enabled = bool(active)
    filters = sum(bool(str(env.get(name) or "").strip()) for name in _FILTERS)
    if not enabled:
        status = "DESABILITADA - NENHUMA PESQUISA"
    elif not key_present:
        status = "CREDENCIAL AUSENTE - NENHUMA PESQUISA"
    elif not requested:
        status = "NÃO SOLICITADA - DEFINIR QUERIES NO CAT-05"
    elif kind not in {"WEB", "FAST"}:
        status = "TIPO INVÁLIDO - REVISAR CAT-05"
    else:
        status = "SOLICITADA - SUJEITA À CONFIRMAÇÃO DE EXECUÇÃO"
    return {
        "enabled": enabled,
        "credential_configured": key_present,
        "queries_requested": requested,
        "query_count": len(requests),
        "mode": kind,
        "optional_filters_configured": filters,
        "status": status,
        "executable_request_pending": enabled and key_present and requested and kind in {"WEB", "FAST"},
    }


def render_perplexity_readiness(state: Any, *, brief: bool = False) -> None:
    """A plain console-facing summary for both integration and AUD setup."""
    data = inspect_perplexity_readiness(state)
    print("\nPERPLEXITY - PREPARAÇÃO DA PESQUISA EXTERNA")
    print(f"  Integração           : {'HABILITADA' if data['enabled'] else 'DESABILITADA'}")
    print(f"  Credencial           : {'CONFIGURADA' if data['credential_configured'] else 'AUSENTE'}")
    print(f"  Pesquisa nesta AUD   : {'SOLICITADA' if data['queries_requested'] else 'NÃO SOLICITADA'}")
    print(f"  Queries / modo       : {data['query_count']} / {data['mode']}")
    print(f"  Situação             : {data['status']}")
    if not brief:
        print(f"  Filtros adicionais   : {data['optional_filters_configured']} definido(s); opcionais")
    print("  Para solicitar: Preparar auditoria > CAT-05 > P. Perplexity >")
    print("    1. Definir queries ou 6. Copiar termos SERP com autorização.")
    print("  Habilitação e chave NÃO executam pesquisa. Queries SERP não são herdadas.")
    print("  Pesquisa Perplexity pode consumir quota/custo e depende de aceite explícito.")
