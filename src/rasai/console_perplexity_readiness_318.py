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
    draft = tuple(getattr(state, "perplexity_draft_queries", ()) or ())
    kind = str(getattr(state, "perplexity_search_type", "web") or "web").strip().upper()
    requested = bool(requests)
    # Configuration viability and a billable request are separate dimensions.
    # Current session edits take priority over the loaded INI draft for display;
    # neither the draft nor SERP terms can create execution intent.
    configured_queries = requests if requested else draft
    configured_mode = (
        kind if requested else str(
            getattr(state, "perplexity_draft_search_type", "web") or "web"
        ).strip().upper()
    )
    configured_source = "SESSÃO" if requested else "INI/RASCUNHO" if draft else "NENHUMA"
    configured_valid = (
        1 <= len(configured_queries) <= 5
        and all(isinstance(q, str) and bool(q.strip()) for q in configured_queries)
        and configured_mode in {"WEB", "FAST"}
    )
    # Display readiness must never promise an executable Search API request
    # for a malformed/incomplete per-AUD query list. The runtime validates
    # the same 1..5 boundary; the console remains read-only here.
    valid_queries = (
        1 <= len(requests) <= 5
        and all(isinstance(q, str) and bool(q.strip()) for q in requests)
    )
    enabled = bool(active)
    filters = sum(bool(str(env.get(name) or "").strip()) for name in _FILTERS)
    configuration_ready = enabled and key_present and configured_valid
    skip_current = bool(getattr(state, "perplexity_skip_draft_this_aud", False))
    draft_awaits_run_confirmation = (
        configuration_ready and bool(draft) and not requested and not skip_current
    )
    if not enabled:
        configuration_status = "DESABILITADA"
    elif not key_present:
        configuration_status = "CREDENCIAL AUSENTE"
    elif not configured_queries:
        configuration_status = "SEM QUERIES CONFIGURADAS"
    elif not configured_valid:
        configuration_status = "QUERIES/MODO INVÁLIDOS"
    else:
        configuration_status = "APTA PARA SOLICITAÇÃO"
    if not enabled:
        status = "DESABILITADA - NENHUMA PESQUISA"
    elif not key_present:
        status = "CREDENCIAL AUSENTE - NENHUMA PESQUISA"
    elif not requested:
        status = (
            "PREPARADA - CONFIRMAR PERPLEXITY AO EXECUTAR AUD"
            if draft_awaits_run_confirmation
            else "NÃO SOLICITADA - EXCLUÍDA NESTA AUD"
            if skip_current else "NÃO SOLICITADA - DEFINIR QUERIES NO CAT-05"
        )
    elif not valid_queries:
        status = "QUERIES INVÁLIDAS - CORRIGIR NO CAT-05"
    elif kind not in {"WEB", "FAST"}:
        status = "TIPO INVÁLIDO - REVISAR CAT-05"
    else:
        status = "SOLICITADA - SUJEITA À CONFIRMAÇÃO DE EXECUÇÃO"
    return {
        "enabled": enabled,
        "credential_configured": key_present,
        "queries_requested": requested,
        "queries_valid": valid_queries,
        "query_count": len(requests),
        "mode": kind,
        "configured_queries": configured_queries,
        "configured_query_count": len(configured_queries),
        "configured_mode": configured_mode,
        "configured_source": configured_source,
        "configuration_ready": configuration_ready,
        "configuration_status": configuration_status,
        "draft_awaits_run_confirmation": draft_awaits_run_confirmation,
        "optional_filters_configured": filters,
        "query_persistence_scope": "SESSION_ONLY_REQUEST_WITH_REUSABLE_INI_DRAFT",
        "mode_persistence_scope": "SESSION_ONLY_REQUEST_WITH_REUSABLE_INI_DRAFT",
        "saved_draft_available": bool(draft),
        "saved_draft_query_count": len(draft),
        "saved_draft_mode": str(
            getattr(state, "perplexity_draft_search_type", "web") or "web"
        ).upper(),
        "global_filters_scope": "ENVIRONMENT_OR_INI_INDEPENDENT_OF_PER_AUD_OPT_IN",
        "persisted_configuration_loss_proven": False,
        "per_aud_paid_consent_restored": False,
        "status": status,
        "executable_request_pending": enabled and key_present and valid_queries and kind in {"WEB", "FAST"},
    }


def render_perplexity_readiness(state: Any, *, brief: bool = False) -> None:
    """A plain console-facing summary for both integration and AUD setup."""
    data = inspect_perplexity_readiness(state)
    print("\nPERPLEXITY - PREPARAÇÃO DA PESQUISA EXTERNA")
    print(f"  Integração           : {'HABILITADA' if data['enabled'] else 'DESABILITADA'}")
    print(f"  Credencial           : {'CONFIGURADA' if data['credential_configured'] else 'AUSENTE'}")
    print(
        f"  Pesquisa nesta AUD   : "
        f"{'SOLICITADA' if data['queries_requested'] else data['status']}"
    )
    print(f"  Queries / modo       : {data['query_count']} / {data['mode']} (solicitação)")
    print(
        f"  Configuração         : {data['configuration_status']} | "
        f"origem={data['configured_source']}"
    )
    print(
        f"  Termos disponíveis   : {data['configured_query_count']} | "
        f"{data['configured_mode']}"
    )
    for term in data["configured_queries"]:
        print(f"    - {term}")
    print(f"  Situação             : {data['status']}")
    if not brief:
        print(f"  Filtros adicionais   : {data['optional_filters_configured']} definido(s); opcionais")
    print("  Para solicitar: Preparar auditoria > CAT-05 > P. Perplexity >")
    if data["draft_awaits_run_confirmation"]:
        print("    R. Iniciar AUD: confirmar uso da Perplexity antes das chamadas externas.")
        print("    Ou 9. Solicitar explicitamente agora no CAT-05.")
    elif data["saved_draft_available"] and not data["queries_requested"]:
        print("    9. Reutilizar rascunho salvo, com confirmação explícita.")
    else:
        print("    1. Definir queries ou 6. Copiar termos SERP com autorização.")
    print(
        f"  Rascunho no INI     : {data['saved_draft_query_count']} query(s) | "
        f"{data['saved_draft_mode']} | não autorizado"
    )
    print("  Salvar INI preserva queries/modo; executar AUD confirma uso Perplexity por AUD.")
    print("  O rascunho é proposto na execução; CAT-05 > P > 9 é opcional.")
    print("  Filtros globais, credencial e ativação são independentes dessa solicitação.")
    print("  Habilitação e chave NÃO executam pesquisa. Queries SERP não são herdadas.")
    print("  Pesquisa Perplexity pode consumir quota/custo e depende de aceite explícito.")
