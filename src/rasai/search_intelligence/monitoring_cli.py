"""CLI for registered and recurring Search Intelligence monitoring."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Sequence

from rasai.platform.automation import run_schedule
from rasai.platform.database import open_platform_store
from rasai.platform.store import utc_now

from .config import SerpRuntimeConfig
from .monitoring import execute_registered_query, new_query
from .monitoring_database import open_search_monitoring_repository
from .monitoring_reporting import write_search_monitoring_report
from .runtime import projected_http_request_ceiling, validate_live_provider_engine


def _repository(args):
    return open_search_monitoring_repository(
        audits_root=args.audits_root,
        platform_db=args.platform_db,
    )


def _store(args):
    return open_platform_store(
        audits_root=args.audits_root,
        platform_db=args.platform_db,
    )


def _initial_next_run(*, interval_minutes: int | None, daily_time: str | None) -> str | None:
    now = datetime.now().astimezone()
    if interval_minutes is not None:
        return (now + timedelta(minutes=interval_minutes)).isoformat()
    if daily_time:
        hour, minute = (int(item) for item in daily_time.split(":", 1))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.isoformat()
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rasai search-monitor",
        description="Register and execute recurring Search Intelligence without mutating immutable AUD evidence.",
    )
    parser.add_argument("--audits-root", type=Path, default=Path("audits"))
    parser.add_argument("--platform-db", type=Path, help="SQLite-only override for audits/.rasai/platform.db")
    sub = parser.add_subparsers(dest="command", required=True)

    query = sub.add_parser("query", help="manage registered query contexts")
    qsub = query.add_subparsers(dest="query_command", required=True)
    add = qsub.add_parser("add")
    add.add_argument("--project", required=True, help="project_id from Product Platform")
    add.add_argument("--property", required=True, help="property_id from Product Platform")
    add.add_argument("--environment", required=True, help="environment_id from Product Platform")
    add.add_argument("--query", required=True)
    add.add_argument("--domain", required=True)
    add.add_argument("--engine", default="google")
    add.add_argument("--country", default="BR")
    add.add_argument("--region")
    add.add_argument("--language", default="pt-BR")
    add.add_argument("--device", choices=("mobile", "desktop"), default="desktop")
    add.add_argument("--depth", type=int, default=20)
    add.add_argument("--mode", choices=("disabled", "live", "fixture"), default="live")
    add.add_argument("--provider", default="serpapi")
    add.add_argument("--no-competitive", action="store_true")
    add.add_argument("--compare-content", action="store_true")
    add.add_argument("--max-content-pages", type=int, default=3)
    add.add_argument("--ai-competitive", action="store_true")
    add.add_argument("--ai-provider", choices=("none", "openai", "fixture"), default="none")
    add.add_argument("--ai-model")
    add.add_argument("--ymyl-mode", choices=("AUTO", "ON", "OFF"), default="AUTO")
    cadence = add.add_mutually_exclusive_group()
    cadence.add_argument("--interval-minutes", type=int)
    cadence.add_argument("--daily-time", help="HH:MM local time")

    qsub.add_parser("list")
    enable = qsub.add_parser("enable")
    enable.add_argument("--query-id", required=True)
    disable = qsub.add_parser("disable")
    disable.add_argument("--query-id", required=True)

    run = sub.add_parser("run", help="execute one registered query now")
    run.add_argument("--query-id", required=True)
    run.add_argument("--fixture", type=Path, help="SERP fixture override; no Search network call")
    run.add_argument("--ai-fixture", type=Path, help="Competitive AI fixture override; no AI network call")
    run.add_argument("--dry-run", action="store_true", help="show request ceilings without execution")

    history = sub.add_parser("history", help="show persisted longitudinal runs")
    history.add_argument("--query-id", required=True)
    history.add_argument("--limit", type=int, default=20)

    report = sub.add_parser("report", help="generate audits/platform-report/search-intelligence.html")
    report.add_argument("--property")
    report.add_argument("--environment")
    report.add_argument("--output", type=Path)

    due = sub.add_parser("run-due", help="execute only due Search-monitor schedules")
    due.add_argument("--timeout-seconds", type=int, default=3600)
    return parser


def _validate_schedule_args(args) -> None:
    if args.interval_minutes is not None and args.interval_minutes < 60:
        raise ValueError("recurring Search monitoring interval must be >= 60 minutes")
    if args.daily_time:
        try:
            hour, minute = (int(item) for item in args.daily_time.split(":", 1))
        except (TypeError, ValueError):
            raise ValueError("--daily-time must use HH:MM") from None
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("--daily-time must use HH:MM in 00:00-23:59")
    if (args.interval_minutes is not None or args.daily_time) and args.mode != "live":
        raise ValueError("scheduled Search monitoring requires --mode live; fixture/disabled remain manual")
    if args.mode == "live":
        validate_live_provider_engine(args.provider, args.engine)
    if args.ai_competitive and not args.compare_content:
        raise ValueError("--ai-competitive requires --compare-content")
    if args.ai_provider == "fixture" and (args.interval_minutes is not None or args.daily_time):
        raise ValueError("fixture AI provider cannot be used by a recurring schedule")


def _add_query(args) -> int:
    _validate_schedule_args(args)
    with _repository(args) as repository:
        item = repository.register_query(
            new_query(
                project_id=args.project,
                property_id=args.property,
                environment_id=args.environment,
                query=args.query.strip(),
                domain_of_interest=args.domain.strip().casefold(),
                engine=args.engine.strip().casefold(),
                country=args.country.strip().upper(),
                region=args.region.strip() if args.region else None,
                language=args.language.strip(),
                device=args.device,
                requested_depth=args.depth,
                mode=args.mode,
                provider=args.provider.strip().casefold(),
                competitive=not args.no_competitive,
                compare_content=args.compare_content,
                max_content_pages=args.max_content_pages,
                ai_competitive=args.ai_competitive,
                ai_provider=args.ai_provider,
                ai_model=args.ai_model,
                ymyl_mode=args.ymyl_mode,
            )
        )
        schedule_id = None
        if args.interval_minutes is not None or args.daily_time:
            kind = "INTERVAL" if args.interval_minutes is not None else "DAILY"
            next_run = _initial_next_run(
                interval_minutes=args.interval_minutes,
                daily_time=args.daily_time,
            )
            audits_root = Path(args.audits_root).resolve()
            command = [
                "search-monitor", "--audits-root", str(audits_root),
            ]
            if args.platform_db:
                command.extend(("--platform-db", str(Path(args.platform_db).resolve())))
            command.extend(("run", "--query-id", item.query_id))
            with _store(args) as store:
                schedule = store.add_schedule(
                    project_id=item.project_id,
                    property_id=item.property_id,
                    environment_id=item.environment_id,
                    name=f"search-monitor:{item.query_id}",
                    kind=kind,
                    command_argv=command,
                    interval_minutes=args.interval_minutes,
                    daily_time=args.daily_time,
                    next_run_at=next_run,
                    enabled=True,
                )
            schedule_id = schedule.schedule_id
            repository.attach_schedule(item.query_id, schedule_id)
        print(f"query_id={item.query_id}")
        print(f"schedule_id={schedule_id or 'manual'}")
        print(f"context={item.query} | {item.engine}/{item.country}/{item.language}/{item.device}/depth={item.requested_depth}")
        return 0


def _list_queries(args) -> int:
    with _repository(args) as repository:
        for item in repository.list_queries():
            print(
                f"{item.query_id}\t{'ENABLED' if item.enabled else 'DISABLED'}\t"
                f"{item.query}\t{item.domain_of_interest}\t{item.engine}/{item.country}/{item.device}/depth={item.requested_depth}\t"
                f"schedule={item.schedule_id or 'manual'}"
            )
    return 0


def _set_enabled(args, enabled: bool) -> int:
    with _repository(args) as repository:
        repository.set_query_enabled(args.query_id, enabled)
        item = repository.get_query(args.query_id)
        if item and item.schedule_id:
            with _store(args) as store:
                with store.transaction() as connection:
                    connection.execute(
                        "UPDATE schedules SET enabled=? WHERE schedule_id=?",
                        (int(enabled), item.schedule_id),
                    )
        print(f"{args.query_id}: {'ENABLED' if enabled else 'DISABLED'}")
    return 0


def _estimate(item) -> tuple[int, int, int]:
    config = replace(
        SerpRuntimeConfig.from_environment(validate=False),
        mode=item.mode,
        provider=item.provider,
    ).validate()
    if item.mode == "live":
        validate_live_provider_engine(item.provider, item.engine)
    serp = projected_http_request_ceiling(
        config, depths=(item.requested_depth,)
    )
    content = (1 + item.max_content_pages) * 6 if item.compare_content else 0
    ai = 1 if item.ai_competitive else 0
    return serp, content, ai


def _run_query(args) -> int:
    with _repository(args) as repository:
        item = repository.get_query(args.query_id)
        if item is None:
            raise KeyError(f"Search monitor query not found: {args.query_id}")
        if args.dry_run:
            serp, content, ai = _estimate(item)
            print(f"query_id={item.query_id}")
            print(f"SERP HTTP request ceiling={serp}")
            print(f"content HTTP attempt ceiling={content}")
            print(f"AI provider call ceiling={ai}")
            return 0
        run = execute_registered_query(
            repository,
            item,
            audits_root=args.audits_root,
            fixture_path=args.fixture,
            ai_fixture_path=args.ai_fixture,
        )
        report = write_search_monitoring_report(
            repository,
            Path(args.audits_root) / "platform-report",
            property_id=item.property_id,
            environment_id=item.environment_id,
        )
        print(f"monitor_run_id={run.monitor_run_id}")
        print(f"status={run.status}")
        print(f"position={run.snapshot.customer_position if run.snapshot.customer_position is not None else run.snapshot.domain_status}")
        print(f"changes={','.join(change.status for change in run.changes) or '-'}")
        print(f"requests=serp:{run.serp_http_requests},content:{run.content_http_requests},ai:{run.ai_provider_calls}")
        print(f"manifest={run.manifest_ref or '-'}")
        print(f"report={report}")
        if run.error_code:
            print(f"error={run.error_code}:{run.error_message or ''}")
        return 0 if run.status in {"SUCCESS", "PARTIAL"} else 1


def _history(args) -> int:
    with _repository(args) as repository:
        item = repository.get_query(args.query_id)
        if item is None:
            raise KeyError(f"Search monitor query not found: {args.query_id}")
        print(f"Query: {item.query} ({item.query_id})")
        for run in repository.list_runs(item.query_id, limit=args.limit):
            position = run.snapshot.customer_position if run.snapshot.customer_position is not None else run.snapshot.domain_status
            changes = ",".join(change.status for change in run.changes) or "-"
            print(f"{run.completed_at}\t{position}\t{run.snapshot.provider}/{run.snapshot.data_mode or '-'}\t{changes}")
    return 0


def _report(args) -> int:
    with _repository(args) as repository:
        target = args.output or Path(args.audits_root) / "platform-report"
        print(write_search_monitoring_report(
            repository,
            target,
            property_id=args.property,
            environment_id=args.environment,
        ))
    return 0


def _run_due(args) -> int:
    results = []
    with _store(args) as store:
        schedules = [
            item for item in store.list_schedules(due_before=utc_now(), enabled_only=True)
            if len(item.command_argv) >= 2 and item.command_argv[0] == "search-monitor" and item.command_argv[-2] == "--query-id"
        ]
        for schedule in schedules:
            results.append(run_schedule(store, schedule, timeout_seconds=args.timeout_seconds))
    for result in results:
        print(f"{result.schedule_id}\t{result.status}\treturn_code={result.return_code}\tnext={result.next_run_at or '-'}")
    return 0 if all(item.return_code == 0 for item in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "query":
            if args.query_command == "add":
                return _add_query(args)
            if args.query_command == "list":
                return _list_queries(args)
            if args.query_command == "enable":
                return _set_enabled(args, True)
            if args.query_command == "disable":
                return _set_enabled(args, False)
        if args.command == "run":
            return _run_query(args)
        if args.command == "history":
            return _history(args)
        if args.command == "report":
            return _report(args)
        if args.command == "run-due":
            return _run_due(args)
        parser.error("unsupported search-monitor command")
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
