"""CLI surface for provider-neutral SERP observation."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .config import SerpRuntimeConfig
from .models import DomainMatchStatus, QueryOrigin, SerpQueryRequest, new_identifier
from .runtime import execute_search, live_provider_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai search",
        description="Observe traditional Search SERPs without mixing AI-answer observation semantics.",
    )
    parser.add_argument("query", nargs="+", help="query/term to observe")
    parser.add_argument("--domain", required=True, help="customer domain/URL to locate within the observed depth")
    parser.add_argument("--engine", default="google", help="search engine identifier; live adapter support is provider-specific")
    parser.add_argument("--country", default="BR", help="country/market code")
    parser.add_argument("--region", help="optional locality/region passed when supported by the provider")
    parser.add_argument("--language", default="pt-BR", help="language context")
    parser.add_argument("--device", choices=("mobile", "desktop"), default="desktop")
    parser.add_argument("--depth", type=int, default=20, help="requested result depth; bounded by RASAI_SERP_MAX_DEPTH")
    parser.add_argument(
        "--mode",
        choices=("disabled", "live", "fixture"),
        default=None,
        help="override RASAI_SERP_MODE (default disabled)",
    )
    parser.add_argument(
        "--provider",
        choices=live_provider_ids(),
        default=None,
        help="live provider adapter; provider-specific details stay outside Search Intelligence core",
    )
    parser.add_argument("--fixture", type=Path, help="canonical fixture JSON; no network/quota is consumed")
    parser.add_argument("--audit-workspace", type=Path, help="existing audit workspace; persists into its audit.db and artifacts/")
    parser.add_argument(
        "--query-origin",
        choices=tuple(item.value for item in QueryOrigin),
        default=QueryOrigin.MANUAL.value,
        help="provenance of the query hypothesis/source",
    )
    parser.add_argument("--run-id", help="optional caller/session run identifier")
    parser.add_argument("--dry-run", action="store_true", help="validate limits and show projected request ceiling without calling a provider")
    return parser


def _render_result(result) -> None:
    request = result.request
    observation = result.observation
    print(f"Query: {request.query}")
    print(f"Engine/market/device: {request.engine} / {request.country} / {request.device}")
    print(f"Depth observada: {request.depth}")
    print(f"Domínio de interesse: {request.domain_of_interest}")
    print(f"Status: {result.domain_status.value}")
    if observation is None:
        print("SERP observation: desabilitada; nenhuma chamada externa e nenhum dado observado.")
        return
    print(f"Fonte/provider: {observation.provider}")
    print(f"Data mode: {observation.data_mode.value}")
    print(f"Coletado em: {observation.collected_at.isoformat()}")
    print(f"Resultados normalizados: {observation.result_count}")
    if observation.raw_evidence_ref:
        print(f"Evidência raw: {observation.raw_evidence_ref}")
    if result.domain_status is DomainMatchStatus.FOUND:
        print(f"Posição observada: {result.customer_position}")
        print(f"Resultados acima: {len(result.results_ahead)}")
        for item in result.results_ahead:
            print(f"  #{item.position} {item.domain} — {item.url}")
        if result.competitor_domains_ahead:
            print("Domínios Search acima: " + ", ".join(result.competitor_domains_ahead))
    elif result.domain_status is DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH:
        print(
            "Interpretação: domínio não encontrado dentro da depth observada; isso NÃO significa que o domínio não ranqueia."
        )
    elif result.error_message:
        print(f"Erro: {result.error_code}: {result.error_message}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        config = SerpRuntimeConfig.from_environment(validate=False)
        if args.mode is not None:
            config = replace(config, mode=args.mode)
        if args.provider is not None:
            config = replace(config, provider=args.provider)
        if args.fixture is not None:
            config = replace(config, fixture_path=args.fixture)
        config = config.validate()
        if args.depth <= 0:
            raise ValueError("--depth must be greater than zero")
        run_id = args.run_id or new_identifier("SERP-RUN")
        requests = tuple(
            SerpQueryRequest(
                query=query,
                engine=args.engine,
                country=args.country,
                region=args.region,
                language=args.language,
                device=args.device,
                depth=args.depth,
                domain_of_interest=args.domain,
                run_id=run_id,
                query_origin=QueryOrigin(args.query_origin),
                config_metadata={"surface": "cli"},
            )
            for query in args.query
        )
        if args.dry_run:
            projected = config.worst_case_http_requests(len(requests))
            if len(requests) > config.max_queries:
                raise ValueError(f"SERP query count {len(requests)} exceeds configured max_queries {config.max_queries}")
            if any(item.depth > config.max_depth for item in requests):
                raise ValueError(f"requested SERP depth exceeds configured max_depth {config.max_depth}")
            if projected > config.max_requests:
                raise ValueError(f"worst-case SERP HTTP requests {projected} exceed configured max_requests {config.max_requests}")
            print(f"SERP dry-run: mode={config.mode} provider={config.provider} queries={len(requests)} depth={args.depth}")
            print(f"HTTP request ceiling: {projected}/{config.max_requests}")
            print("No provider call executed.")
            return 0
        execution = execute_search(
            requests,
            config=config,
            workspace_root=args.audit_workspace,
            fixture_path=args.fixture,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(f"SERP mode: {execution.mode}")
    print(f"Provider: {execution.provider}")
    print(f"HTTP requests: {execution.actual_http_requests} (teto projetado {execution.projected_http_request_ceiling})")
    print(f"Persistência: {'audit.db + artifacts' if execution.persisted else 'não solicitada'}")
    for index, result in enumerate(execution.results, 1):
        if index > 1:
            print("-" * 72)
        _render_result(result)
    if any(
        result.domain_status in {DomainMatchStatus.ERROR, DomainMatchStatus.UNAVAILABLE}
        for result in execution.results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
