"""Offline preparation-only comparison of SERP and Search API query intent.

No network, billing, provider authorization, or use of current INI settings.
Query identity is only one prerequisite; do not declare two providers equivalent.
"""
from __future__ import annotations

from typing import Any, Sequence


def geo_query_alignment(
    serp_queries: Sequence[Any] | None,
    perplexity_queries: Sequence[Any] | None,
) -> dict[str, str]:
    def normalized(value: Sequence[Any] | None) -> tuple[str, ...]:
        return tuple(str(s).strip().casefold() for s in (value or ()) if str(s).strip())

    serp = normalized(serp_queries)
    external = normalized(perplexity_queries)
    if not serp or not external:
        return {
            "status": "NOT_REQUESTED",
            "label": "N/D — falta consulta em uma das fontes",
        }
    if len(serp) == 1 and len(external) == 1 and serp[0] == external[0]:
        return {
            "status": "QUERY_MATCH",
            "label": "Termo idêntico; demais condições ainda não comprovadas",
        }
    if len(serp) == len(external) and sorted(serp) == sorted(external):
        return {
            "status": "QUERY_SET_MATCH",
            "label": "Conjunto de termos alinhado; atribuição por consulta ainda necessária",
        }
    return {
        "status": "DIVERGENT",
        "label": "DIVERGENTE — consultas distintas; comparação GEO pode ser N/D",
    }


def geo_configuration_view(state: Any) -> dict[str, Any]:
    """One advisory projection reused by CAT-05, launch gate and plan.

    Query-text alignment is NOT proof of topical fitness or equivalent provider
    language, geography, device, chronology or answer citation.
    """
    serp = tuple(getattr(state, "search_queries", ()) or ())
    active = tuple(getattr(state, "perplexity_queries", ()) or ())
    draft = tuple(getattr(state, "perplexity_draft_queries", ()) or ())
    px = active or draft
    alignment = geo_query_alignment(serp, px)
    source = "SOLICITADA" if active else "RASCUNHO (SEM AUTORIZAÇÃO)" if draft else "NÃO CONFIGURADA"
    condition = alignment["status"]
    if condition == "DIVERGENT":
        verdict = "REVISÃO RECOMENDADA: CONSULTAS DIFERENTES; COMPARAÇÃO N/D"
    elif condition == "QUERY_SET_MATCH":
        verdict = "NÃO COMPARÁVEL POR REQUEST MULTI-QUERY SEM ATRIBUIÇÃO DE FONTES"
    elif condition == "QUERY_MATCH":
        verdict = "MESMO TEXTO; EQUIVALÊNCIA DE CONTEXTO NÃO COMPROVADA"
    else:
        verdict = "N/D: UMA DAS FONTES SEM CONSULTA"
    return {
        "serp_queries": serp,
        "perplexity_queries": px,
        "perplexity_source": source,
        "alignment_status": condition,
        "alignment_label": alignment["label"],
        "comparability": verdict,
        "topical_fitness": "NÃO VERIFICADA",
        "provider_context_equivalence": "NÃO COMPROVADA",
        "review_recommended": condition in {"DIVERGENT", "QUERY_SET_MATCH"},
    }
