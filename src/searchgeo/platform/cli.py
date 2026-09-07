"""CLI for the RASAi product-platform control plane.

The command surface is additive and preserves every existing audit/monitor/
quality/observability command. Windows-local operation remains first-class.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any

from .alerts import evaluate_and_deliver
from .automation import run_due_schedules
from .ci_outputs import write_gate_json, write_gate_junit, write_gate_sarif
from .deployment import compare_deployment_pair, resolve_deployment_pair
from .indexing import index_audit_workspace, index_audits
from .integrations import (
    collect_ga4,
    crawler_summary,
    import_cloudflare_logpush,
    import_combined_access_log,
    import_ga4_csv,
)
from .page_compare import compare_pages, write_page_compare_report
from .reporting import write_deployment_report, write_platform_site
from .store import PlatformStore, default_platform_database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai platform",
        description="RASAi product platform: portfolio, milestones, deploy compare, schedules and external outcomes.",
    )
    parser.add_argument("--audits-root", default="audits", help="root contendo AUD-* e .searchgeo/platform.db")
    parser.add_argument("--platform-db", help="override opcional para platform.db")
    sub = parser.add_subparsers(dest="platform_command", required=True)

    sub.add_parser("init", help="inicializar/validar platform.db")

    index = sub.add_parser("index", help="indexar AUDs imutáveis no catálogo central")
    index.add_argument("--audit", help="AUD específico (ID ou caminho); sem argumento indexa todos")
    index.add_argument("--environment-name", default="Production")
    index.add_argument("--environment-kind", default="PRODUCTION")
    index.add_argument("--strict", action="store_true")

    sub.add_parser("status", help="mostrar contagens e caminho do banco central")

    site = sub.add_parser("site", help="gerar Portfolio/Timeline/Deployments/Pages/Usage HTML")
    site.add_argument("--output", help="diretório de saída; padrão audits/platform-report")

    org = sub.add_parser("org", help="gerenciar organização local/SaaS-ready")
    org_sub = org.add_subparsers(dest="org_command", required=True)
    org_add = org_sub.add_parser("add")
    org_add.add_argument("--name", required=True)
    org_add.add_argument("--slug")
    org_sub.add_parser("list")

    workspace = sub.add_parser("workspace", help="gerenciar workspaces/clientes")
    ws_sub = workspace.add_subparsers(dest="workspace_command", required=True)
    ws_add = ws_sub.add_parser("add")
    ws_add.add_argument("--organization", required=True)
    ws_add.add_argument("--name", required=True)
    ws_add.add_argument("--slug")
    ws_list = ws_sub.add_parser("list")
    ws_list.add_argument("--organization")

    project = sub.add_parser("project", help="gerenciar projetos")
    prj_sub = project.add_subparsers(dest="project_command", required=True)
    prj_add = prj_sub.add_parser("add")
    prj_add.add_argument("--workspace", required=True)
    prj_add.add_argument("--name", required=True)
    prj_add.add_argument("--slug")
    prj_list = prj_sub.add_parser("list")
    prj_list.add_argument("--workspace")

    prop = sub.add_parser("property", help="gerenciar propriedades/domínios")
    prop_sub = prop.add_subparsers(dest="property_command", required=True)
    prop_add = prop_sub.add_parser("add")
    prop_add.add_argument("--project", required=True)
    prop_add.add_argument("--name", required=True)
    prop_add.add_argument("--origin", required=True)
    prop_add.add_argument("--competitor", action="store_true")
    prop_list = prop_sub.add_parser("list")
    prop_list.add_argument("--project")

    env = sub.add_parser("environment", help="gerenciar production/staging/QA/preview")
    env_sub = env.add_subparsers(dest="environment_command", required=True)
    env_add = env_sub.add_parser("add")
    env_add.add_argument("--property", required=True)
    env_add.add_argument("--name", required=True)
    env_add.add_argument("--kind", default="PRODUCTION")
    env_add.add_argument("--origin", required=True)
    env_list = env_sub.add_parser("list")
    env_list.add_argument("--property")

    milestone = sub.add_parser("milestone", help="registrar marcos/deploys sem alterar AUDs")
    milestone_sub = milestone.add_subparsers(dest="milestone_command", required=True)
    milestone_add = milestone_sub.add_parser("add")
    milestone_add.add_argument("--project", required=True)
    milestone_add.add_argument("--property", required=True)
    milestone_add.add_argument("--environment", required=True)
    milestone_add.add_argument("--kind", default="DEPLOYMENT")
    milestone_add.add_argument("--at", required=True, help="ISO-8601; ex. 2026-09-07T14:35:00-03:00")
    milestone_add.add_argument("--title", required=True)
    milestone_add.add_argument("--description")
    milestone_add.add_argument("--release")
    milestone_add.add_argument("--commit")
    milestone_add.add_argument("--branch")
    milestone_add.add_argument("--source", default="MANUAL")
    milestone_add.add_argument("--tag", action="append", default=[])
    milestone_list = milestone_sub.add_parser("list")
    milestone_list.add_argument("--project")
    milestone_list.add_argument("--property")
    milestone_list.add_argument("--environment")

    baseline = sub.add_parser("baseline", help="golden baseline por property/environment")
    baseline_sub = baseline.add_subparsers(dest="baseline_command", required=True)
    baseline_set = baseline_sub.add_parser("set")
    baseline_set.add_argument("--property", required=True)
    baseline_set.add_argument("--environment", required=True)
    baseline_set.add_argument("--audit", required=True)
    baseline_set.add_argument("--label")
    baseline_get = baseline_sub.add_parser("get")
    baseline_get.add_argument("--property", required=True)
    baseline_get.add_argument("--environment", required=True)

    deploy = sub.add_parser("deploy", help="resolver e comparar before/after de milestone")
    deploy_sub = deploy.add_subparsers(dest="deploy_command", required=True)
    deploy_pair = deploy_sub.add_parser("pair")
    _deployment_args(deploy_pair)
    deploy_compare = deploy_sub.add_parser("compare")
    _deployment_args(deploy_compare)
    deploy_compare.add_argument("--output", help="pasta para Deployment Impact")
    deploy_compare.add_argument("--json")
    deploy_compare.add_argument("--junit")
    deploy_compare.add_argument("--sarif")
    deploy_compare.add_argument("--notify", action="store_true", help="avaliar alert rules após comparação")

    page = sub.add_parser("page", help="PageIdentity e Page Compare")
    page_sub = page.add_subparsers(dest="page_command", required=True)
    page_create = page_sub.add_parser("identity-add")
    page_create.add_argument("--property", required=True)
    page_create.add_argument("--name", required=True)
    page_link = page_sub.add_parser("identity-link")
    page_link.add_argument("--identity", required=True)
    page_link.add_argument("--environment", required=True)
    page_link.add_argument("--url", required=True)
    page_link.add_argument("--valid-from")
    page_link.add_argument("--valid-to")
    page_list = page_sub.add_parser("identity-list")
    page_list.add_argument("--property")
    page_compare = page_sub.add_parser("compare")
    page_compare.add_argument("--baseline", required=True)
    page_compare.add_argument("--current", required=True)
    page_compare.add_argument("--baseline-url", required=True)
    page_compare.add_argument("--current-url")
    page_compare.add_argument("--output", default="page-compare.html")

    schedule = sub.add_parser("schedule", help="schedules locais seguros")
    sch_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    sch_add = sch_sub.add_parser("add")
    sch_add.add_argument("--project", required=True)
    sch_add.add_argument("--property", required=True)
    sch_add.add_argument("--environment", required=True)
    sch_add.add_argument("--name", required=True)
    sch_add.add_argument("--kind", choices=["INTERVAL", "DAILY", "MANUAL", "DEPLOYMENT_TRIGGERED", "API_TRIGGERED"], required=True)
    sch_add.add_argument("--interval-minutes", type=int)
    sch_add.add_argument("--daily-time")
    sch_add.add_argument("--next-run-at")
    sch_add.add_argument("command", nargs=argparse.REMAINDER, help="argumentos RASAi, ex: audit https://example.com --max-pages 10")
    sch_sub.add_parser("list")
    sch_run = sch_sub.add_parser("run-due")
    sch_run.add_argument("--now")
    sch_run.add_argument("--timeout-seconds", type=int, default=3600)

    alert = sub.add_parser("alert", help="regras de alerta determinísticas")
    alert_sub = alert.add_subparsers(dest="alert_command", required=True)
    alert_add = alert_sub.add_parser("add")
    alert_add.add_argument("--project", required=True)
    alert_add.add_argument("--property", required=True)
    alert_add.add_argument("--environment", required=True)
    alert_add.add_argument("--name", required=True)
    alert_add.add_argument(
        "--status",
        action="append",
        default=None,
        help="status material a observar; repetível. Default: REGRESSED + NEW",
    )
    alert_add.add_argument("--min-severity", default="HIGH")
    alert_add.add_argument("--destination", choices=["NONE", "JSON", "WEBHOOK"], default="NONE")
    alert_add.add_argument("--destination-env", help="nome da env var contendo URL; a URL não é persistida")
    alert_list = alert_sub.add_parser("list")
    alert_list.add_argument("--property")

    integ = sub.add_parser("integration", help="registrar conectores BYOK sem persistir segredo")
    integ_sub = integ.add_subparsers(dest="integration_command", required=True)
    integ_add = integ_sub.add_parser("add")
    integ_add.add_argument("--organization", required=True)
    integ_add.add_argument("--provider", required=True)
    integ_add.add_argument("--name", required=True)
    integ_add.add_argument("--secret-env")
    integ_add.add_argument("--workspace")
    integ_add.add_argument("--project")
    integ_add.add_argument("--property")
    integ_add.add_argument("--config-json")
    integ_list = integ_sub.add_parser("list")
    integ_list.add_argument("--organization")
    integ_list.add_argument("--property")

    collect = sub.add_parser("collect", help="coletar/importar outcomes externos non-scoring")
    collect_sub = collect.add_subparsers(dest="collect_command", required=True)
    ga4 = collect_sub.add_parser("ga4")
    ga4.add_argument("--property", required=True)
    ga4.add_argument("--environment", required=True)
    ga4.add_argument("--ga4-property", required=True)
    ga4.add_argument("--start-date", required=True)
    ga4.add_argument("--end-date", required=True)
    ga4.add_argument("--token-env", default="GOOGLE_ANALYTICS_ACCESS_TOKEN")
    ga4_csv = collect_sub.add_parser("ga4-csv")
    ga4_csv.add_argument("--property", required=True)
    ga4_csv.add_argument("--environment", required=True)
    ga4_csv.add_argument("--file", required=True)
    ga4_csv.add_argument("--start-date")
    ga4_csv.add_argument("--end-date")
    cf = collect_sub.add_parser("cloudflare-logpush")
    cf.add_argument("--property", required=True)
    cf.add_argument("--environment", required=True)
    cf.add_argument("--file", required=True)
    access = collect_sub.add_parser("access-log")
    access.add_argument("--property", required=True)
    access.add_argument("--environment", required=True)
    access.add_argument("--file", required=True)
    crawler = collect_sub.add_parser("crawler-summary")
    crawler.add_argument("--dataset", required=True)

    usage = sub.add_parser("usage", help="usage ledger para custos/consumo")
    usage_sub = usage.add_subparsers(dest="usage_command", required=True)
    usage_add = usage_sub.add_parser("add")
    usage_add.add_argument("--organization", required=True)
    usage_add.add_argument("--category", required=True)
    usage_add.add_argument("--quantity", required=True, type=float)
    usage_add.add_argument("--unit", required=True)
    usage_add.add_argument("--project")
    usage_add.add_argument("--property")
    usage_add.add_argument("--audit")
    usage_add.add_argument("--cost", type=float)
    usage_add.add_argument("--currency")
    usage_add.add_argument("--provider")
    usage_list = usage_sub.add_parser("summary")
    usage_list.add_argument("--organization")

    immutable = sub.add_parser("immutability", help="verificar SHA-256 de audit.db indexado")
    imm_sub = immutable.add_subparsers(dest="immutability_command", required=True)
    imm_verify = imm_sub.add_parser("verify")
    imm_verify.add_argument("--audit", required=True)
    return parser


def _deployment_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--milestone", required=True)
    parser.add_argument("--baseline-mode", choices=["AUTO", "GOLDEN", "EXPLICIT"], default="AUTO")
    parser.add_argument("--baseline")
    parser.add_argument("--current")


def _audit_workspace(audits_root: str, value: str) -> Path:
    path = Path(value)
    return path if path.is_dir() else Path(audits_root) / value


def _print(items: Any) -> None:
    print(json.dumps(items, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = Path(args.platform_db) if args.platform_db else default_platform_database(args.audits_root)
    try:
        with PlatformStore(db) as store:
            command = args.platform_command
            if command == "init":
                print(f"RASAi platform database: {store.database}")
                print("Schema: OK")
                return 0
            if command == "index":
                if args.audit:
                    record, unchanged = index_audit_workspace(
                        store,
                        _audit_workspace(args.audits_root, args.audit),
                        environment_name=args.environment_name,
                        environment_kind=args.environment_kind,
                    )
                    _print({"audit_id": record.audit_id, "unchanged": unchanged, "property_id": record.property_id, "environment_id": record.environment_id})
                else:
                    summary = index_audits(
                        store,
                        args.audits_root,
                        strict=args.strict,
                        environment_name=args.environment_name,
                        environment_kind=args.environment_kind,
                    )
                    _print(asdict(summary))
                return 0
            if command == "status":
                _print({"database": str(store.database), "counts": store.counts()})
                return 0
            if command == "site":
                target = Path(args.output) if args.output else Path(args.audits_root) / "platform-report"
                print(write_platform_site(store, target))
                return 0
            if command == "org":
                if args.org_command == "add":
                    _print(asdict(store.get_or_create_organization(args.name, slug=args.slug)))
                else:
                    _print([asdict(x) for x in store.list_organizations()])
                return 0
            if command == "workspace":
                if args.workspace_command == "add":
                    _print(asdict(store.get_or_create_workspace(args.organization, args.name, slug=args.slug)))
                else:
                    _print([asdict(x) for x in store.list_workspaces(args.organization)])
                return 0
            if command == "project":
                if args.project_command == "add":
                    _print(asdict(store.get_or_create_project(args.workspace, args.name, slug=args.slug)))
                else:
                    _print([asdict(x) for x in store.list_projects(args.workspace)])
                return 0
            if command == "property":
                if args.property_command == "add":
                    _print(asdict(store.get_or_create_property(args.project, args.name, args.origin, is_competitor=args.competitor)))
                else:
                    _print([asdict(x) for x in store.list_properties(args.project)])
                return 0
            if command == "environment":
                if args.environment_command == "add":
                    _print(asdict(store.get_or_create_environment(args.property, args.name, args.kind, args.origin)))
                else:
                    _print([asdict(x) for x in store.list_environments(args.property)])
                return 0
            if command == "milestone":
                if args.milestone_command == "add":
                    item = store.add_milestone(
                        project_id=args.project,
                        property_id=args.property,
                        environment_id=args.environment,
                        kind=args.kind,
                        occurred_at=args.at,
                        title=args.title,
                        description=args.description,
                        release=args.release,
                        commit_sha=args.commit,
                        branch=args.branch,
                        source=args.source,
                        tags=args.tag,
                    )
                    _print(asdict(item))
                else:
                    _print([asdict(x) for x in store.list_milestones(project_id=args.project, property_id=args.property, environment_id=args.environment)])
                return 0
            if command == "baseline":
                if args.baseline_command == "set":
                    store.set_golden_baseline(args.property, args.environment, args.audit, label=args.label)
                    print(f"Golden baseline: {args.audit}")
                else:
                    print(store.get_golden_baseline(args.property, args.environment) or "NOT_SET")
                return 0
            if command == "deploy":
                pair = resolve_deployment_pair(
                    store,
                    args.milestone,
                    baseline_mode=args.baseline_mode,
                    baseline_audit_id=args.baseline,
                    current_audit_id=args.current,
                )
                if args.deploy_command == "pair":
                    _print(asdict(pair))
                    return 0
                result, gate = compare_deployment_pair(store, pair)
                output = Path(args.output) if args.output else Path(args.audits_root) / "deployments" / pair.milestone.milestone_id
                report, manifest = write_deployment_report(store, pair, result, gate, output)
                comparison_id = store.record_comparison(
                    baseline_audit_id=result.baseline.audit_id,
                    current_audit_id=result.current.audit_id,
                    comparison_type="DEPLOYMENT",
                    comparable=result.comparable,
                    material_regressions=len(result.regressions),
                    material_improvements=len(result.improvements),
                    milestone_id=pair.milestone.milestone_id,
                    gate_status="PASS" if gate.passed else "FAIL",
                    report_path=str(report),
                    manifest={"deployment_manifest": str(manifest)},
                )
                if args.json:
                    write_gate_json(args.json, result, gate)
                if args.junit:
                    write_gate_junit(args.junit, result, gate)
                if args.sarif:
                    write_gate_sarif(args.sarif, result, gate)
                deliveries = ()
                if args.notify:
                    baseline = store.get_audit(result.baseline.audit_id)
                    if baseline is None:
                        raise KeyError("baseline missing after comparison")
                    deliveries = evaluate_and_deliver(
                        store,
                        result,
                        property_id=baseline.property_id,
                        comparison_id=comparison_id,
                        milestone_id=pair.milestone.milestone_id,
                    )
                _print({
                    "comparison_id": comparison_id,
                    "report": str(report),
                    "manifest": str(manifest),
                    "gate": "PASS" if gate.passed else "FAIL",
                    "regressions": len(result.regressions),
                    "improvements": len(result.improvements),
                    "notifications": [asdict(x) for x in deliveries],
                })
                return 0 if gate.passed else 1
            if command == "page":
                if args.page_command == "identity-add":
                    _print(asdict(store.create_page_identity(args.property, args.name)))
                    return 0
                if args.page_command == "identity-link":
                    store.link_page_url(args.identity, args.environment, args.url, valid_from=args.valid_from, valid_to=args.valid_to)
                    print("PageIdentity URL linked")
                    return 0
                if args.page_command == "identity-list":
                    _print([asdict(x) for x in store.list_page_identities(args.property)])
                    return 0
                comparison = compare_pages(
                    _audit_workspace(args.audits_root, args.baseline),
                    _audit_workspace(args.audits_root, args.current),
                    baseline_url=args.baseline_url,
                    current_url=args.current_url,
                )
                path = write_page_compare_report(comparison, args.output)
                _print({"report": str(path), "material_changes": sum(x.material for x in comparison.changes), "notes": comparison.notes})
                return 0
            if command == "schedule":
                if args.schedule_command == "add":
                    command_argv = list(args.command)
                    if command_argv and command_argv[0] == "--":
                        command_argv = command_argv[1:]
                    item = store.add_schedule(
                        project_id=args.project,
                        property_id=args.property,
                        environment_id=args.environment,
                        name=args.name,
                        kind=args.kind,
                        command_argv=command_argv,
                        interval_minutes=args.interval_minutes,
                        daily_time=args.daily_time,
                        next_run_at=args.next_run_at,
                    )
                    _print(asdict(item))
                elif args.schedule_command == "list":
                    _print([asdict(x) for x in store.list_schedules()])
                else:
                    _print([asdict(x) for x in run_due_schedules(store, now=args.now, timeout_seconds=args.timeout_seconds)])
                return 0
            if command == "alert":
                if args.alert_command == "add":
                    statuses = args.status or ["REGRESSED", "NEW"]
                    _print(asdict(store.add_alert_rule(
                        project_id=args.project,
                        property_id=args.property,
                        environment_id=args.environment,
                        name=args.name,
                        event_statuses=statuses,
                        min_severity=args.min_severity,
                        destination=args.destination,
                        destination_env=args.destination_env,
                    )))
                else:
                    _print([asdict(x) for x in store.list_alert_rules(property_id=args.property)])
                return 0
            if command == "integration":
                if args.integration_command == "add":
                    config = json.loads(args.config_json) if args.config_json else {}
                    _print(asdict(store.add_integration(
                        organization_id=args.organization,
                        provider=args.provider,
                        name=args.name,
                        secret_env=args.secret_env,
                        workspace_id=args.workspace,
                        project_id=args.project,
                        property_id=args.property,
                        configuration=config,
                    )))
                else:
                    _print([asdict(x) for x in store.list_integrations(organization_id=args.organization, property_id=args.property)])
                return 0
            if command == "collect":
                if args.collect_command == "ga4":
                    dataset = collect_ga4(store, property_id=args.property, environment_id=args.environment, ga4_property_id=args.ga4_property, start_date=args.start_date, end_date=args.end_date, access_token_env=args.token_env)
                    _print(asdict(dataset))
                elif args.collect_command == "ga4-csv":
                    _print(asdict(import_ga4_csv(store, property_id=args.property, environment_id=args.environment, path=args.file, period_start=args.start_date, period_end=args.end_date)))
                elif args.collect_command == "cloudflare-logpush":
                    _print(asdict(import_cloudflare_logpush(store, property_id=args.property, environment_id=args.environment, path=args.file)))
                elif args.collect_command == "access-log":
                    _print(asdict(import_combined_access_log(store, property_id=args.property, environment_id=args.environment, path=args.file)))
                else:
                    _print(crawler_summary(store, args.dataset))
                return 0
            if command == "usage":
                if args.usage_command == "add":
                    _print(asdict(store.add_usage_event(
                        organization_id=args.organization,
                        category=args.category,
                        quantity=args.quantity,
                        unit=args.unit,
                        project_id=args.project,
                        property_id=args.property,
                        audit_id=args.audit,
                        cost_estimate=args.cost,
                        currency=args.currency,
                        provider=args.provider,
                    )))
                else:
                    _print(store.usage_summary(args.organization))
                return 0
            if command == "immutability":
                valid, expected, actual = store.validate_audit_immutability(args.audit)
                _print({"audit_id": args.audit, "valid": valid, "indexed_sha256": expected, "current_sha256": actual})
                return 0 if valid else 1
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"RASAi platform error: {exc}", file=sys.stderr)
        return 2
    return 2
