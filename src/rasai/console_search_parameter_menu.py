"""Menu-driven editor for SERP inputs of the next audit execution.

This module changes only the interactive Search Intelligence configuration surface. It
keeps the runtime/provider contract owned by ``console_search_intelligence`` and the
reusable provider/governance settings in the canonical configuration catalog.
"""
from __future__ import annotations

import os
from types import ModuleType
from typing import Any

from rasai.console_search_guidance import (
    competitive_guidance,
    depth_guidance,
    device_guidance,
    region_guidance,
)
from rasai.search_intelligence.config import SerpRuntimeConfig
from rasai.search_intelligence.runtime import projected_http_request_ceiling

_INSTALLED = False


def _provider_registration(search_module: ModuleType, config: SerpRuntimeConfig):
    return search_module._provider_registration(config.provider)


def _credential_state(search_module: ModuleType, config: SerpRuntimeConfig) -> str:
    registration = _provider_registration(search_module, config)
    if registration is None:
        return "N/A"
    return "CONFIGURADA" if (os.environ.get(registration.key_env) or "").strip() else "NÃO CONFIGURADA"


def _provider_name(search_module: ModuleType, config: SerpRuntimeConfig) -> str:
    registration = _provider_registration(search_module, config)
    if registration is None:
        return config.provider
    return registration.display_name


def _print_guidance(lines: tuple[str, ...]) -> None:
    for index, line in enumerate(lines):
        prefix = "  Uso: " if index == 0 else "       "
        print(prefix + line)


def _projected(config: SerpRuntimeConfig, *, query_count: int, depth: int) -> int:
    return projected_http_request_ceiling(
        config,
        depths=(depth for _ in range(max(query_count, 0))),
    )


def _max_query_count(config: SerpRuntimeConfig, *, depth: int) -> int:
    """Return the largest query count allowed by hard limits at the selected depth."""
    if config.mode != "live":
        return config.max_queries
    low, high, accepted = 0, config.max_queries, 0
    while low <= high:
        middle = (low + high) // 2
        projected = _projected(config, query_count=middle, depth=depth)
        if projected <= config.max_requests:
            accepted = middle
            low = middle + 1
        else:
            high = middle - 1
    return accepted


def _max_depth(config: SerpRuntimeConfig, *, query_count: int) -> int:
    """Return the largest depth compatible with provider/governance request limits."""
    if query_count <= 0 or config.mode != "live":
        return config.max_depth
    low, high, accepted = 1, config.max_depth, 0
    while low <= high:
        middle = (low + high) // 2
        projected = _projected(config, query_count=query_count, depth=middle)
        if projected <= config.max_requests:
            accepted = middle
            low = middle + 1
        else:
            high = middle - 1
    return accepted


def _render_provider_context(search_module: ModuleType, config: SerpRuntimeConfig) -> None:
    registration = _provider_registration(search_module, config)
    engine = registration.engine if registration is not None else "unknown"
    print("\n[ PROVIDER / LIMITES APLICADOS ]")
    print(f"Modo                 : {config.mode}")
    print(f"Provider             : {_provider_name(search_module, config)} ({config.provider})")
    print(f"Engine               : {engine}")
    print(f"Credencial           : {_credential_state(search_module, config)}")
    print(f"Máximo de termos     : {config.max_queries}")
    print(f"Máximo de requests   : {config.max_requests}")
    print(f"Profundidade máxima  : Top {config.max_depth}")
    print(f"Máx. concorrentes    : {config.max_competitors}")
    print(f"Retries              : {config.retries}")
    print(f"Timeout              : {config.timeout_seconds:g} s")
    print(f"Intervalo mínimo     : {config.min_interval_seconds:g} s")
    print(
        "  Estes valores são limites/configurações reutilizáveis do provider. "
        "A tela abaixo altera somente o pedido da próxima execução."
    )


def _render_execution_menu(state: Any, config: SerpRuntimeConfig) -> None:
    queries = tuple(getattr(state, "search_queries", ()) or ())
    depth = int(getattr(state, "search_depth", 20) or 20)
    region = str(getattr(state, "search_region", "") or "").strip()
    device = str(getattr(state, "search_device", "mobile") or "mobile").casefold()
    competitive = bool(getattr(state, "search_competitive", True))
    projected = _projected(config, query_count=len(queries), depth=max(depth, 1))

    print("\n[ O QUE PESQUISAR - PRÓXIMA EXECUÇÃO ]")
    print(f"1. Termos de busca          : {'; '.join(queries) if queries else '<não configurados>'}")
    print(f"2. Localidade               : {region or '<usa apenas país/mercado da auditoria>'}")
    print(f"3. Profundidade desejada    : Top {depth}")
    print(f"4. Dispositivo da busca     : {'Desktop' if device == 'desktop' else 'Mobile'}")
    print(f"5. Análise de concorrentes  : {'Ativada' if competitive else 'Desativada'}")
    if queries:
        print(f"   Impacto projetado         : {projected}/{config.max_requests} requests no teto conservador")
    else:
        print("   Solicitação               : NÃO SOLICITADA enquanto não houver termos")
    print("\nD. Não solicitar SERP nesta execução (limpa os termos)")
    print("V. Voltar")


def _edit_terms(search_module: ModuleType, state: Any, config: SerpRuntimeConfig) -> None:
    current_depth = max(int(getattr(state, "search_depth", 20) or 20), 1)
    allowed = _max_query_count(config, depth=current_depth)
    print("\nTERMOS DE BUSCA")
    print("  Informe um ou mais termos separados por ';'. Duplicados são removidos preservando a ordem.")
    print(f"  Limite configurado: {config.max_queries} termo(s).")
    if allowed < config.max_queries:
        print(
            f"  Com Top {current_depth}, retries={config.retries} e teto de {config.max_requests} requests, "
            f"esta execução aceita no máximo {allowed} termo(s)."
        )
    else:
        print(f"  Faixa efetiva nesta execução: 1..{allowed} termo(s).")
    if allowed <= 0:
        print("  Nenhum termo cabe no orçamento atual. Reduza a profundidade ou aumente o limite de requests.")
        return
    raw = input("Novos termos [V=voltar]: ").strip()
    if raw.upper() == "V":
        return
    queries = search_module.parse_search_terms(raw)
    if not queries:
        print("  Valor inválido: informe pelo menos um termo.")
        return
    if len(queries) > allowed:
        print(f"  Valor inválido: use de 1 a {allowed} termo(s) nas condições atuais.")
        return
    state.search_queries = queries


def _edit_region(state: Any) -> None:
    print("\nLOCALIDADE")
    _print_guidance(region_guidance())
    print("  Formato: texto livre aceito pelo provider. Não existe enumeração canônica no runtime atual.")
    print("  Use LIMPAR para remover a localidade e voltar a usar apenas país/mercado da auditoria.")
    current = str(getattr(state, "search_region", "") or "").strip()
    raw = input(f"Nova localidade [{current or 'vazio'}] [V=voltar]: ").strip()
    if raw.upper() == "V":
        return
    if raw.upper() == "LIMPAR":
        state.search_region = ""
        return
    if not raw:
        return
    state.search_region = raw


def _edit_depth(state: Any, config: SerpRuntimeConfig) -> None:
    query_count = len(tuple(getattr(state, "search_queries", ()) or ()))
    allowed = _max_depth(config, query_count=query_count)
    print("\nPROFUNDIDADE SERP")
    _print_guidance(depth_guidance(state, config))
    if allowed <= 0:
        print(
            f"  Nenhuma profundidade é válida com {query_count} termo(s) e o teto atual de "
            f"{config.max_requests} requests. Reduza a quantidade de termos primeiro."
        )
        return
    print(f"  Faixa aceita nesta execução: 1..{allowed}.")
    if allowed < config.max_depth:
        print(
            f"  O limite técnico é Top {config.max_depth}, mas o orçamento atual reduz o máximo "
            f"efetivo para Top {allowed}."
        )
    raw = input(f"Nova profundidade [1-{allowed}] [V=voltar]: ").strip()
    if raw.upper() == "V":
        return
    try:
        value = int(raw)
    except ValueError:
        print(f"  Valor inválido: informe um inteiro entre 1 e {allowed}.")
        return
    if value < 1 or value > allowed:
        print(f"  Valor inválido: informe um inteiro entre 1 e {allowed}.")
        return
    state.search_depth = value


def _edit_device(state: Any) -> None:
    print("\nDISPOSITIVO DA BUSCA")
    _print_guidance(device_guidance())
    print("  1. Mobile")
    print("  2. Desktop")
    print("  V. Voltar")
    raw = input("Escolha [1-2/V]: ").strip().upper()
    if raw == "1":
        state.search_device = "mobile"
    elif raw == "2":
        state.search_device = "desktop"
    elif raw != "V":
        print("  Opção inválida: use 1, 2 ou V.")


def _edit_competitive(state: Any, config: SerpRuntimeConfig) -> None:
    print("\nANÁLISE DE CONCORRENTES")
    _print_guidance(competitive_guidance())
    print(f"  Limite reutilizável atual: até {config.max_competitors} concorrente(s) observados.")
    if config.max_competitors == 0:
        print("  Atenção: o limite atual é 0; ativar a classificação não materializará concorrentes.")
    print("  1. Ativada")
    print("  2. Desativada")
    print("  V. Voltar")
    raw = input("Escolha [1-2/V]: ").strip().upper()
    if raw == "1":
        state.search_competitive = True
    elif raw == "2":
        state.search_competitive = False
    elif raw != "V":
        print("  Opção inválida: use 1, 2 ou V.")


def _mark_pending(search_module: ModuleType, state: Any, config: SerpRuntimeConfig) -> None:
    queries = tuple(getattr(state, "search_queries", ()) or ())
    if not queries:
        state.search_last_status = "NOT_REQUESTED"
        state.search_last_detail = ""
        state.search_last_report = ""
        state.search_last_duration_seconds = None
        state.error = ""
        return
    state.search_last_status = "PENDING"
    state.search_last_detail = (
        f"{len(queries)} termo(s); "
        f"{search_module._engine_for_provider(config.provider)}/{state.search_device}; "
        f"depth={state.search_depth}"
    )
    state.error = ""


def configure_search_parameters(search_module: ModuleType, state: Any) -> None:
    """Edit one SERP execution input at a time through a bounded operator menu."""
    try:
        config = SerpRuntimeConfig.from_environment()
    except ValueError as exc:
        state.error = f"configuração SERP inválida: {exc}"
        print(f"\nConfiguração SERP inválida: {exc}")
        return

    while True:
        _render_provider_context(search_module, config)
        _render_execution_menu(state, config)
        raw = input("Opção a modificar: ").strip().upper()
        if raw == "V":
            _mark_pending(search_module, state, config)
            return
        if raw == "D":
            state.search_queries = ()
            _mark_pending(search_module, state, config)
            continue
        if raw == "1":
            _edit_terms(search_module, state, config)
        elif raw == "2":
            _edit_region(state)
        elif raw == "3":
            _edit_depth(state, config)
        elif raw == "4":
            _edit_device(state)
        elif raw == "5":
            _edit_competitive(state, config)
        else:
            print("  Opção inválida: use 1-5, D ou V.")


def install(search_module: ModuleType) -> None:
    """Replace only the sequential SERP execution wizard with the bounded menu editor."""
    global _INSTALLED
    if _INSTALLED or getattr(search_module, "_rasai_search_parameter_menu", False):
        return

    original = search_module.configure_search_intelligence

    def configure_search_intelligence(state: Any) -> None:
        return configure_search_parameters(search_module, state)

    configure_search_intelligence._rasai_original = original  # type: ignore[attr-defined]
    search_module.configure_search_intelligence = configure_search_intelligence
    search_module._rasai_search_parameter_menu = True
    _INSTALLED = True
