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
