"""CLI for observed Search/AI data and derived diagnostics."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3

from .crux_history import collect_crux_history
from .google_genai import import_google_genai_performance_csv, persist_google_genai_control
from .google_search_console import collect_search_analytics, collect_url_inspection
from .importers import import_bing_search_performance_csv, import_observability_json
from .reporting import enrich_observability_report
from .store import ObservabilityStore

GSC_TOKEN_ENV = "GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN"
CRUX_KEY_ENV = "SEARCHGEO_CRUX_API_KEY"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai observe",
        description="Coleta/importa outcomes observados sem alterar SARI-001 nem audit.db.",
    )
    sub = parser.add_subparsers(dest="observe_command", required=True)

    report = sub.add_parser("report", help="gerar/atualizar report/observability.html")
    _audit(report)

    status = sub.add_parser("status", help="listar datasets persistidos no sidecar observability.db")
    _audit(status)

    imported = sub.add_parser("import", help="importar contrato RASAI-OBS-IMPORT-001")
    _audit(imported)
    imported.add_argument("--file", required=True)

    bing = sub.add_parser("bing-import", help="importar CSV exportado do Bing Search Performance")
    _audit(bing)
    bing.add_argument("--file", required=True)
    bing.add_argument("--surface", help="override opcional de surface/source do CSV")

    google_ai = sub.add_parser("google-ai-import", help="importar export do Google Generative AI Performance")
    _audit(google_ai)
    google_ai.add_argument("--file", required=True)
    google_ai.add_argument("--surface", choices=("search", "discover"), default="search")

    google_ai_control = sub.add_parser("google-ai-control", help="persistir estado observado INCLUDE/EXCLUDE/INHERIT do controle GenAI")
    _audit(google_ai_control)
    google_ai_control.add_argument("--state", choices=("INCLUDE", "EXCLUDE", "INHERIT"), required=True)
    google_ai_control.add_argument("--source-label", default="MANUAL_SEARCH_CONSOLE_OBSERVATION")
    google_ai_control.add_argument("--observed-at")

    gsc = sub.add_parser("gsc-search", help="coletar Search Analytics via API oficial do Search Console")
    _audit(gsc)
    gsc.add_argument("--site-url", required=True, help="propriedade do Search Console, incluindo sc-domain: quando aplicável")
    gsc.add_argument("--start-date", required=True)
    gsc.add_argument("--end-date", required=True)
    gsc.add_argument("--search-type", default="web")
    gsc.add_argument("--max-rows", type=int, default=100_000)
    gsc.add_argument("--token-env", default=GSC_TOKEN_ENV, help=f"env que contém OAuth bearer token; default {GSC_TOKEN_ENV}")

    inspect = sub.add_parser("gsc-inspect", help="consultar URL Inspection API para URLs persistidas no AUD")
    _audit(inspect)
    inspect.add_argument("--site-url", required=True)
    inspect.add_argument("--max-urls", type=int, default=25, help="proteção de quota; default 25 URLs")
    inspect.add_argument("--token-env", default=GSC_TOKEN_ENV)
    inspect.add_argument("--language-code", default="pt-BR")

    crux = sub.add_parser("crux-history", help="coletar histórico oficial CrUX para URL ou origin")
    _audit(crux)
    crux.add_argument("--target", required=True)
    crux.add_argument("--scope", choices=("url", "origin"), default="url")
    crux.add_argument("--form-factor", choices=("PHONE", "DESKTOP", "TABLET"))
    crux.add_argument("--periods", type=int, default=40)
    crux.add_argument("--key-env", default=CRUX_KEY_ENV)
    return parser


def _audit(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--audits-root", default="audits")
    parser.add_argument("--audit", required=True, help="AUD-* ou caminho do workspace")


def _workspace(root: str, value: str) -> Path:
    direct = Path(value)
    return direct if direct.is_dir() else Path(root) / value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workspace = _workspace(args.audits_root, args.audit)
    try:
        if args.observe_command == "report":
            path = enrich_observability_report(audit_workspace=workspace)
            print(f"Search & AI Observability report: {path}")
            return 0
        if args.observe_command == "status":
            if not (workspace / "observability.db").is_file():
                print("Observability: nenhum dataset persistido.")
                return 0
            with ObservabilityStore(workspace) as store:
                datasets = store.datasets()
                print(f"Observability datasets: {len(datasets)}")
                for item in datasets:
                    print(f"- {item['dataset_id']} | {item['source_type']} | {item['capture_method']} | {item['period_start'] or '-'} → {item['period_end'] or '-'}")
            return 0
        if args.observe_command == "import":
            dataset = import_observability_json(audit_workspace=workspace, path=args.file)
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"Dataset importado: {dataset}")
            print(f"Relatório: {report}")
            return 0
        if args.observe_command == "bing-import":
            dataset = import_bing_search_performance_csv(audit_workspace=workspace, path=args.file, surface=args.surface)
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"Bing Search Performance importado: {dataset}")
            print(f"Relatório: {report}")
            return 0
        if args.observe_command == "google-ai-import":
            dataset = import_google_genai_performance_csv(audit_workspace=workspace, path=args.file, surface=args.surface)
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"Google Generative AI Performance importado: {dataset}")
            print(f"Relatório: {report}")
            return 0
        if args.observe_command == "google-ai-control":
            dataset = persist_google_genai_control(
                audit_workspace=workspace,
                state=args.state,
                source_label=args.source_label,
                observed_at=args.observed_at,
            )
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"Google GenAI control observado: {dataset} | {args.state}")
            print(f"Relatório: {report}")
            return 0
        if args.observe_command == "gsc-search":
            token = _secret(args.token_env, "Google Search Console OAuth bearer token")
            dataset = collect_search_analytics(
                audit_workspace=workspace,
                site_url=args.site_url,
                access_token=token,
                start_date=args.start_date,
                end_date=args.end_date,
                search_type=args.search_type,
                max_rows=max(1, args.max_rows),
            )
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"Search Console Search Analytics: {dataset}")
            print(f"Relatório: {report}")
            return 0
        if args.observe_command == "gsc-inspect":
            token = _secret(args.token_env, "Google Search Console OAuth bearer token")
            urls = _audit_urls(workspace)[: max(1, args.max_urls)]
            dataset = collect_url_inspection(
                audit_workspace=workspace,
                site_url=args.site_url,
                access_token=token,
                urls=tuple(urls),
                language_code=args.language_code,
            )
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"Search Console URL Inspection: {dataset} ({len(urls)} URL(s))")
            print(f"Relatório: {report}")
            return 0
        if args.observe_command == "crux-history":
            key = _secret(args.key_env, "CrUX API key")
            dataset = collect_crux_history(
                audit_workspace=workspace,
                api_key=key,
                target=args.target,
                target_scope=args.scope,
                form_factor=args.form_factor,
                collection_period_count=args.periods,
            )
            report = enrich_observability_report(audit_workspace=workspace)
            print(f"CrUX History: {dataset}")
            print(f"Relatório: {report}")
            return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"RASAI observe error: {exc}")
        return 2
    parser.error(f"unsupported observe command: {args.observe_command}")
    return 2


def _secret(name: str, label: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{label} not configured; set environment variable {name}")
    return value


def _audit_urls(workspace: Path) -> list[str]:
    database = workspace / "audit.db"
    if not database.is_file():
        raise FileNotFoundError(database)
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        return [str(row[0]) for row in connection.execute("SELECT normalized_url FROM pages ORDER BY normalized_url")]
    finally:
        connection.close()
