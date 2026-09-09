"""CLI surface for provider-neutral Search Intelligence."""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .competitive_runtime import execute_competitive_intelligence
from .config import SerpRuntimeConfig
from .content import ContentFetchStatus, PublicWebFetcher
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
    parser.add_argument(
        "--competitive",
        action="store_true",
        help="classify observed results ahead of the customer and select bounded Search competitor candidates; no extra network",
    )
    parser.add_argument(
        "--compare-content",
        action="store_true",
        help="explicitly fetch selected public pages and produce deterministic customer-vs-leaders content context",
    )
    parser.add_argument(
        "--customer-url",
        help="explicit customer page for content comparison; useful when the customer is not found within observed SERP depth",
    )
    parser.add_argument(
        "--max-content-pages",
        type=int,
        default=3,
        help="maximum unique competitor candidate pages per query to inspect (default 3)",
    )
    parser.add_argument(
        "--content-timeout",
        type=float,
        default=10.0,
        help="timeout per public content HTTP attempt in seconds (default 10)",
    )
    parser.add_argument(
        "--content-max-bytes",
        type=int,
        default=2_000_000,
        help="maximum HTML response bytes per content page (default 2000000)",
    )
    parser.add_argument(
        "--content-max-redirects",
        type=int,
        default=5,
        help="maximum redirects for explicit content inspection (default 5)",
    )
    return parser


def _render_result(result) -> None:
    request = result.request
    observation = result.observation
    print(f"Query: {request.query}")
    print(f"Engine/market/device: {request.engine} / {request.country} / {request.device}")
    print(f"Depth solicitada: {request.depth}")
    print(f"Domínio de interesse: {request.domain_of_interest}")
    print(f"Status: {result.domain_status.value}")
    if observation is None:
        print("SERP observation: desabilitada; nenhuma chamada externa e nenhum dado observado.")
        return
    print(f"Fonte/provider: {observation.provider}")
    print(f"Data mode: {observation.data_mode.value}")
    print(f"Coletado em: {observation.collected_at.isoformat()}")
    print(f"Resultados normalizados: {observation.result_count}")
    quality = observation.quality_metadata
    if quality.get("pages_collected") is not None:
        print(
            "Páginas provider coletadas: "
            f"{quality.get('pages_collected')}/{quality.get('pages_requested_ceiling')}"
        )
    if quality.get("pagination_ended_before_requested_depth"):
        print("Observação: o provider encerrou a paginação antes da depth solicitada.")
    if observation.raw_evidence_ref:
        print(f"Evidência raw: {observation.raw_evidence_ref}")
    if result.domain_status is DomainMatchStatus.FOUND:
        print(f"Posição observada: {result.customer_position}")
        print(f"Resultados acima: {len(result.results_ahead)}")
        for item in result.results_ahead:
            print(f"  #{item.position} {item.domain} - {item.url}")
        if result.competitor_domains_ahead:
            print("Domínios Search acima: " + ", ".join(result.competitor_domains_ahead))
    elif result.domain_status is DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH:
        print(
            "Interpretação: domínio não encontrado nos resultados coletados dentro da depth solicitada; "
            "isso NÃO significa que o domínio não ranqueia."
        )
    elif result.error_message:
        print(f"Erro: {result.error_code}: {result.error_message}")


def _format_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _render_competitive(analysis) -> None:
    selection = analysis.selection
    print("Competitive Search Intelligence:")
    if not selection.classified_results:
        print("  Nenhum resultado elegível para classificação no conjunto observado.")
    else:
        for item in selection.classified_results:
            marker = " [selecionado]" if item in selection.selected_candidates else ""
            print(
                f"  #{item.result.position} {item.result.domain}: "
                f"{item.classification.value}{marker}"
            )
        print(
            f"  Candidatos selecionados para conteúdo: {len(selection.selected_candidates)}"
        )

    print(f"  Comparação de conteúdo: {analysis.comparison_status}")
    if analysis.comparison_status == "CONTENT_COMPARISON_DISABLED":
        print("  Coleta adicional de páginas: não solicitada.")
        return
    if analysis.comparison_status == "CUSTOMER_URL_REQUIRED":
        print(
            "  Para comparar conteúdo quando o domínio não aparece na depth observada, "
            "informe --customer-url para esta query."
        )
        return
    pages = tuple(
        page
        for page in ((analysis.customer_page,) + analysis.competitor_pages)
        if page is not None
    )
    for page in pages:
        print(
            f"  Página {page.role}: {page.domain} status={page.status.value} "
            f"http={page.http_status if page.http_status is not None else 'n/a'}"
        )
        if page.status is ContentFetchStatus.OBSERVED:
            print(
                "    "
                f"words={page.word_count} "
                f"query_body={_format_ratio(page.query_body_coverage)} "
                f"title_terms={len(page.query_terms_in_title)} "
                f"heading_terms={len(page.query_terms_in_headings)} "
                f"jsonld_types={len(page.jsonld_types)}"
            )
            if page.content_sha256:
                print(f"    content_sha256={page.content_sha256}")
        elif page.error_code:
            print(f"    {page.error_code}: {page.error_message}")

    if analysis.gaps:
        print("  Diferenças observadas contra páginas à frente:")
        for gap in analysis.gaps:
            print(f"    - {gap.code}: {gap.message}")
    elif analysis.comparison_status == "CONSOLIDATED":
        print("  Nenhuma diferença determinística configurada foi sinalizada.")
    if analysis.comparison_status == "CONSOLIDATED":
        print(
            "  Política de interpretação: diferenças são contexto correlacional; "
            "não são apresentadas como causa do ranking."
        )


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
        if args.max_content_pages < 0:
            raise ValueError("--max-content-pages must be >= 0")
        if args.max_content_pages > config.max_competitors:
            raise ValueError(
                f"--max-content-pages {args.max_content_pages} exceeds configured "
                f"max_competitors {config.max_competitors}"
            )
        if args.customer_url and not args.compare_content:
            raise ValueError("--customer-url requires --compare-content")
        if args.compare_content and len(args.query) > 1 and args.customer_url:
            raise ValueError(
                "--customer-url with --compare-content is supported for one query at a time"
            )

        content_fetcher = PublicWebFetcher(
            timeout_seconds=args.content_timeout,
            max_redirects=args.content_max_redirects,
            max_bytes=args.content_max_bytes,
        )

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
            projected = sum(
                config.worst_case_http_requests(1, depth=item.depth)
                for item in requests
            )
            if len(requests) > config.max_queries:
                raise ValueError(f"SERP query count {len(requests)} exceeds configured max_queries {config.max_queries}")
            if any(item.depth > config.max_depth for item in requests):
                raise ValueError(f"requested SERP depth exceeds configured max_depth {config.max_depth}")
            if projected > config.max_requests:
                raise ValueError(f"worst-case SERP HTTP requests {projected} exceed configured max_requests {config.max_requests}")
            print(f"SERP dry-run: mode={config.mode} provider={config.provider} queries={len(requests)} depth={args.depth}")
            print(f"SERP HTTP request ceiling: {projected}/{config.max_requests}")
            if args.compare_content:
                documents = len(requests) * (1 + args.max_content_pages)
                attempts = documents * (1 + args.content_max_redirects)
                print(
                    "Content HTTP attempt ceiling: "
                    f"{attempts} ({documents} documents x "
                    f"{1 + args.content_max_redirects} attempts including redirects)"
                )
                print(
                    "Content comparison is direct public-web acquisition; "
                    "it consumes no SERP provider quota."
                )
            print("No provider or content call executed.")
            return 0
        execution = execute_search(
            requests,
            config=config,
            workspace_root=args.audit_workspace,
            fixture_path=args.fixture,
        )
        competitive_execution = None
        if args.competitive or args.compare_content:
            competitive_execution = execute_competitive_intelligence(
                execution,
                content_enabled=args.compare_content,
                customer_url=args.customer_url,
                max_competitor_pages=args.max_content_pages,
                workspace_root=args.audit_workspace,
                fetcher=content_fetcher if args.compare_content else None,
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
        if competitive_execution is not None:
            _render_competitive(competitive_execution.analyses[index - 1])
    if competitive_execution is not None and competitive_execution.content_enabled:
        print(
            "Content HTTP requests: "
            f"{competitive_execution.content_http_requests}"
        )
    if any(
        result.domain_status in {DomainMatchStatus.ERROR, DomainMatchStatus.UNAVAILABLE}
        for result in execution.results
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
