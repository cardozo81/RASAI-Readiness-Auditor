"""Contextual help for Search Intelligence inputs in the interactive console.

This module is intentionally presentation-only. It does not change SERP execution,
provider selection, request budgets, scoring, persistence or report contracts.
"""
from __future__ import annotations

import builtins
from types import ModuleType
from typing import Any

from rasai.search_intelligence.config import SerpRuntimeConfig
from rasai.search_intelligence.runtime import projected_http_request_ceiling


def _query_count(state: Any) -> int:
    return len(tuple(getattr(state, "search_queries", ()) or ()))


def _safe_google_depth(config: SerpRuntimeConfig, query_count: int) -> int:
    """Largest Google depth compatible with the configured worst-case request budget."""
    if query_count <= 0 or config.mode != "live" or config.provider != "serpapi":
        return config.max_depth
    attempts_per_page = query_count * (config.retries + 1)
    if attempts_per_page <= 0:
        return config.max_depth
    affordable_pages = config.max_requests // attempts_per_page
    if affordable_pages <= 0:
        return 0
    return min(config.max_depth, affordable_pages * 10)


def depth_guidance(state: Any, config: SerpRuntimeConfig) -> tuple[str, ...]:
    """Human-readable explanation of depth and its concrete quota impact."""
    query_count = _query_count(state)
    lines = [
        "Profundidade define até qual posição orgânica será observada para cada termo.",
        "Ex.: depth=1 olha somente a posição 1; 10 observa o Top 10; 20 observa o Top 20.",
        "Se o domínio não aparecer, a conclusão é somente 'não observado dentro do Top N consultado'; não significa que ele não ranqueia além dessa profundidade.",
    ]

    if config.provider == "serpapi":
        lines.append(
            "No Google/SerpApi, posições 1-10 usam a primeira página de resultados; "
            "11-20 exigem uma segunda página. A quota cresce por blocos de até 10 posições."
        )
        if query_count and config.mode == "live":
            requested_depth = min(
                max(int(getattr(state, "search_depth", config.max_depth)), 1),
                config.max_depth,
            )
            projected = projected_http_request_ceiling(
                config, depths=(requested_depth for _ in range(query_count))
            )
            safe_depth = _safe_google_depth(config, query_count)
            if projected > config.max_requests:
                if safe_depth > 0:
                    lines.append(
                        f"ATENÇÃO: com {query_count} termo(s), depth={requested_depth} e "
                        f"retries={config.retries}, o teto é {projected} requests, acima do "
                        f"limite atual {config.max_requests}. Use depth <= {safe_depth}, reduza "
                        "os termos ou aumente RASAI_SERP_MAX_REQUESTS."
                    )
                else:
                    lines.append(
                        f"ATENÇÃO: o limite atual de {config.max_requests} requests não comporta "
                        f"{query_count} termo(s) nem com depth=1 no pior caso. Reduza os termos "
                        "ou aumente RASAI_SERP_MAX_REQUESTS."
                    )
            else:
                lines.append(
                    f"Com {query_count} termo(s) e retries={config.retries}, depth={requested_depth} "
                    f"tem teto de {projected}/{config.max_requests} requests do provider."
                )
    elif config.provider == "serpapi-bing":
        lines.append(
            "No Bing a paginação é controlada pelo provider; a profundidade continua sendo o "
            "número máximo de posições observadas, enquanto RASAI_SERP_MAX_REQUESTS é o limite rígido."
        )

    lines.append(
        "Quanto maior a profundidade, maior a chance de localizar o domínio auditado e mapear "
        "concorrentes abaixo do Top 10, mas maior pode ser o consumo de quota e o tempo de execução."
    )
    return tuple(lines)


def device_guidance() -> tuple[str, ...]:
    return (
        "Mobile e desktop podem apresentar ordens de resultados diferentes.",
        "Escolha o contexto de busca que deseja medir; isso não muda o dispositivo usado nas outras etapas da auditoria.",
    )


def region_guidance() -> tuple[str, ...]:
    return (
        "Use uma localidade quando o ranking tiver componente geográfico, por exemplo 'Porto Alegre, RS, Brazil'.",
        "Deixe vazio quando quiser apenas o contexto de país/mercado já configurado, sem localização mais específica.",
    )


def competitive_guidance() -> tuple[str, ...]:
    return (
        "Classifica, entre os resultados já observados, quais domínios aparecem à frente do domínio auditado.",
        "Essa classificação não adiciona requests SERP e não afirma que as diferenças encontradas causaram o ranking.",
    )


def _print_guidance(lines: tuple[str, ...]) -> None:
    print()
    for index, line in enumerate(lines):
        print(f"  Para que serve: {line}" if index == 0 else f"                  {line}")


def install(search_module: ModuleType) -> None:
    """Wrap only the Search Intelligence prompt function with contextual help."""
    if getattr(search_module, "_search_input_guidance_installed", False):
        return

    original_configure = search_module.configure_search_intelligence

    def configure_with_guidance(state: Any) -> None:
        original_input = builtins.input

        def guided_input(prompt: str = "") -> str:
            normalized = prompt.strip().casefold()
            try:
                if normalized.startswith("profundidade serp"):
                    _print_guidance(depth_guidance(state, SerpRuntimeConfig.from_environment()))
                elif normalized.startswith("dispositivo serp"):
                    _print_guidance(device_guidance())
                elif normalized.startswith("região/localidade") or normalized.startswith("regiao/localidade"):
                    _print_guidance(region_guidance())
                elif normalized.startswith("classificar deterministicamente"):
                    _print_guidance(competitive_guidance())
            except (TypeError, ValueError):
                # Guidance must never become a new failure path for the console.
                pass
            return original_input(prompt)

        builtins.input = guided_input
        try:
            original_configure(state)
        finally:
            builtins.input = original_input

    search_module.configure_search_intelligence = configure_with_guidance
    search_module._search_input_guidance_installed = True
