"""Point-in-time Search Intelligence as an AUD collection phase.

Search Monitoring remains a separate SaaS job.  This module covers Search Intelligence
explicitly requested for one AUD execution.  The queries are execution input, not
persistent environment configuration, and are collected before evidence sealing so
later AI tasks may consume the persisted SERP/competitive observations.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    SUCCESS,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_phase_runtime import register_collection_hook
from rasai.search_intelligence.config import SerpRuntimeConfig
from rasai.search_intelligence.provider_catalog import serp_provider_registration


_INSTALLED = False
_WORKER_INSTALLED = False
_CURRENT_ARGV: tuple[str, ...] = ()
_COMPONENT = "SEARCH_INTELLIGENCE"
_SEARCH_JOB_FIELDS = frozenset(
    {
        "search_queries",
        "search_depth",
        "search_region",
        "search_device",
        "search_competitive",
    }
)


def configure_audit_argv(argv: Sequence[str]) -> None:
    global _CURRENT_ARGV
    _CURRENT_ARGV = tuple(str(item) for item in argv)


def _install_arguments() -> None:
    from rasai import cli_extensions

    current = cli_extensions.build_parser
    if getattr(current, "_rasai_search_audit_args", False):
        return

    def build_parser():
        parser = current()
        subparsers = next(
            action
            for action in parser._actions
            if getattr(action, "choices", None) and "audit" in action.choices
        )
        audit = subparsers.choices["audit"]
        if not any(action.dest == "search_queries" for action in audit._actions):
            audit.add_argument(
                "--search-query",
                dest="search_queries",
                action="append",
                default=[],
                help="point-in-time SERP query bound to this AUD; repeat for multiple queries",
            )
            audit.add_argument("--search-depth", type=int, default=20)
            audit.add_argument("--search-region", default="")
            audit.add_argument(
                "--search-device",
                choices=("mobile", "desktop"),
                default="mobile",
            )
            competitive = audit.add_mutually_exclusive_group()
            competitive.add_argument(
                "--search-competitive",
                dest="search_competitive",
                action="store_true",
            )
            competitive.add_argument(
                "--no-search-competitive",
                dest="search_competitive",
                action="store_false",
            )
            audit.set_defaults(search_competitive=True)
        return parser

    build_parser._rasai_search_audit_args = True
    build_parser._rasai_original = current
    cli_extensions.build_parser = build_parser


def _normalize_search_queries(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        raw = value.replace("\r", "\n").replace("\n", ";").split(";")
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):
        raw = value
    else:
        raise ValueError("AUDIT payload search_queries must be an array of strings or semicolon-separated text")
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = " ".join(str(item).split())
        key = text.casefold()
        if not text or key in seen:
            continue
        seen.add(key)
        values.append(text)
    if len(values) > 50:
        raise ValueError("AUDIT payload search_queries supports at most 50 unique terms")
    return values


def _install_saas_contract() -> None:
    """Extend the durable AUDIT payload without merging it with SEARCH_MONITOR."""
    from rasai import audit_execution_contract as contract

    contract.AUDIT_JOB_FIELDS = frozenset((*contract.AUDIT_JOB_FIELDS, *_SEARCH_JOB_FIELDS))

    current_options = contract.audit_job_options
    if not bool(getattr(current_options, "_rasai_search_audit", False)):
        def audit_job_options():
            options = list(current_options())
            existing = {item.name for item in options}
            additions = (
                contract.AuditJobOption(
                    "search_queries",
                    "",
                    "text",
                    description=(
                        "Termos SERP point-in-time deste AUD; informe texto separado por ';' "
                        "ou array no payload da API. Não configura SEARCH_MONITOR."
                    ),
                ),
                contract.AuditJobOption("search_depth", 20, "integer"),
                contract.AuditJobOption("search_region", "", "text"),
                contract.AuditJobOption(
                    "search_device",
                    "mobile",
                    "enum",
                    ("mobile", "desktop"),
                ),
                contract.AuditJobOption("search_competitive", True, "boolean"),
            )
            options.extend(item for item in additions if item.name not in existing)
            return tuple(options)

        audit_job_options._rasai_search_audit = True
        audit_job_options._rasai_original = current_options
        contract.audit_job_options = audit_job_options

    current_normalize = contract.normalize_audit_job_payload
    if not bool(getattr(current_normalize, "_rasai_search_audit", False)):
        def normalize_audit_job_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
            normalized = current_normalize(payload)
            queries = _normalize_search_queries(payload.get("search_queries", normalized.get("search_queries", "")))
            depth = payload.get("search_depth", normalized.get("search_depth", 20))
            if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 100:
                raise ValueError("AUDIT payload search_depth must be an integer between 1 and 100")
            region = payload.get("search_region", normalized.get("search_region", ""))
            if not isinstance(region, str):
                raise ValueError("AUDIT payload search_region must be text")
            device = payload.get("search_device", normalized.get("search_device", "mobile"))
            if not isinstance(device, str) or device.strip().casefold() not in {"mobile", "desktop"}:
                raise ValueError("AUDIT payload search_device must be mobile or desktop")
            competitive = payload.get("search_competitive", normalized.get("search_competitive", True))
            if not isinstance(competitive, bool):
                raise ValueError("AUDIT payload search_competitive must be boolean")
            normalized.update(
                {
                    "search_queries": queries,
                    "search_depth": int(depth),
                    "search_region": region.strip(),
                    "search_device": device.strip().casefold(),
                    "search_competitive": competitive,
                }
            )
            return normalized

        normalize_audit_job_payload._rasai_search_audit = True
        normalize_audit_job_payload._rasai_original = current_normalize
        contract.normalize_audit_job_payload = normalize_audit_job_payload

        # Modules that may already have imported the callable by value are repaired;
        # future imports naturally receive the extended contract.
        assignments = {
            "rasai.execution_contract": "normalize_audit_job_payload",
            "rasai.saas_context_integration": "normalize_audit_job_payload",
            "rasai.worker": "normalize_audit_job_payload",
        }
        for module_name, attribute in assignments.items():
            module = sys.modules.get(module_name)
            if module is not None:
                setattr(module, attribute, normalize_audit_job_payload)

    web_module = sys.modules.get("rasai.web.saas_management_routes")
    if web_module is not None:
        web_module.audit_job_options = contract.audit_job_options


def install_worker_projection() -> None:
    """Append in-AUD Search arguments to the canonical SaaS AUDIT worker argv."""
    global _WORKER_INSTALLED
    if _WORKER_INSTALLED:
        return
    from rasai import worker

    current = worker._audit_arguments
    if bool(getattr(current, "_rasai_search_audit", False)):
        _WORKER_INSTALLED = True
        return

    def audit_arguments(store: Any, job: Any, audits_root: Path) -> list[str]:
        argv = list(current(store, job, audits_root))
        payload = worker.normalize_audit_job_payload(job.payload)
        queries = tuple(payload.get("search_queries") or ())
        if not queries:
            return argv
        for query in queries:
            argv.extend(("--search-query", str(query)))
        argv.extend(("--search-depth", str(int(payload["search_depth"]))))
        if str(payload.get("search_region") or "").strip():
            argv.extend(("--search-region", str(payload["search_region"])))
        argv.extend(("--search-device", str(payload["search_device"])))
        argv.append(
            "--search-competitive"
            if bool(payload["search_competitive"])
            else "--no-search-competitive"
        )
        return argv

    audit_arguments._rasai_search_audit = True
    audit_arguments._rasai_original = current
    worker._audit_arguments = audit_arguments
    _WORKER_INSTALLED = True


def _parsed_args():
    if not _CURRENT_ARGV or "audit" not in _CURRENT_ARGV:
        return None
    from rasai import cli_extensions

    parser = cli_extensions.build_parser()
    return parser.parse_args(list(_CURRENT_ARGV))


def _target_url(workspace: Any, audit_id: str) -> str | None:
    connection = sqlite3.connect(workspace.database)
    try:
        for sql in (
            "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid LIMIT 1",
            "SELECT input_url FROM audit_targets WHERE audit_id=? ORDER BY rowid LIMIT 1",
            "SELECT input_url FROM targets WHERE audit_id=? ORDER BY rowid LIMIT 1",
        ):
            try:
                row = connection.execute(sql, (audit_id,)).fetchone()
            except sqlite3.OperationalError:
                continue
            if row and str(row[0] or "").strip():
                return str(row[0]).strip()
    finally:
        connection.close()
    return None


def _collector(*, audit_id: str, workspace: Any, source_blocked: bool = False):
    args = _parsed_args()
    queries = tuple(
        dict.fromkeys(
            " ".join(str(item).split())
            for item in (getattr(args, "search_queries", ()) if args is not None else ())
            if str(item).strip()
        )
    )
    if not queries:
        return {"collection_state": "DISABLED", "requested": False, "queries": 0}

    configuration = {
        "requested": True,
        "queries": list(queries),
        "depth": int(getattr(args, "search_depth", 20)),
        "region": str(getattr(args, "search_region", "") or ""),
        "device": str(getattr(args, "search_device", "mobile")),
        "competitive": bool(getattr(args, "search_competitive", True)),
    }
    register_work_item(
        workspace,
        audit_id=audit_id,
        component=_COMPONENT,
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        retryable=True,
        configuration=configuration,
    )

    if source_blocked:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=FAILED_RETRYABLE,
            error_class="SOURCE_BLOCKED",
            error_code="SEARCH_SKIPPED_SOURCE_BLOCKER",
            error_message="Search Intelligence não executada porque a origem permaneceu tecnicamente bloqueada",
            retryable=True,
        )
        return {
            "collection_state": "BLOCKED",
            "requested": True,
            "queries": len(queries),
            "reason": "SOURCE_BLOCKED",
        }

    config = SerpRuntimeConfig.from_environment()
    if config.mode == "disabled":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=FAILED_RETRYABLE,
            error_class="CONFIGURATION",
            error_code="SERP_DISABLED",
            error_message="Search Intelligence solicitada, mas RASAI_SERP_MODE está disabled",
            retryable=True,
        )
        return {
            "collection_state": "NOT_CONFIGURED",
            "requested": True,
            "queries": len(queries),
            "reason": "SERP_DISABLED",
        }

    registration = serp_provider_registration(config.provider)
    engine = registration.engine if registration is not None else str(config.provider)
    target = _target_url(workspace, audit_id)
    host = urlsplit(target or "").hostname
    if not host:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=FAILED_RETRYABLE,
            error_class="CONTEXT",
            error_code="SEARCH_TARGET_UNAVAILABLE",
            error_message="não foi possível derivar o domínio alvo do AUD",
            retryable=True,
        )
        return {
            "collection_state": "ERROR",
            "requested": True,
            "queries": len(queries),
            "reason": "SEARCH_TARGET_UNAVAILABLE",
        }

    from rasai.search_intelligence.cli import main as search_main

    command = [
        *queries,
        "--domain", host,
        "--engine", engine,
        "--country", str(getattr(args, "market", "BR")),
        "--language", str(getattr(args, "language", "pt-BR")),
        "--device", str(getattr(args, "search_device", "mobile")),
        "--depth", str(int(getattr(args, "search_depth", 20))),
        "--audit-workspace", str(workspace.root),
    ]
    region = str(getattr(args, "search_region", "") or "").strip()
    if region:
        command.extend(("--region", region))
    if bool(getattr(args, "search_competitive", True)):
        command.append("--competitive")

    output = io.StringIO()
    try:
        with redirect_stdout(output), redirect_stderr(output):
            code = int(search_main(command) or 0)
    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 2
    except Exception as exc:
        code = 2
        output.write(f"{type(exc).__name__}: {exc}")

    report = Path(workspace.root) / "report" / "search-intelligence.html"
    detail_lines = [line.strip() for line in output.getvalue().splitlines() if line.strip()]
    detail = detail_lines[-1][:512] if detail_lines else ""
    if code == 0:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=_COMPONENT,
            status=SUCCESS,
            result_ref=(
                str(report.relative_to(workspace.root))
                if report.is_file()
                else "search-intelligence:observations"
            ),
            retryable=False,
        )
        return {
            "collection_state": "SUCCESS",
            "requested": True,
            "queries": len(queries),
            "engine": engine,
            "report_materialized": report.is_file(),
        }

    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component=_COMPONENT,
        status=FAILED_RETRYABLE,
        error_class="EXTERNAL_API",
        error_code=f"SEARCH_EXIT_{code}",
        error_message=detail or f"Search Intelligence retornou código {code}",
        retryable=True,
    )
    return {
        "collection_state": "ERROR",
        "requested": True,
        "queries": len(queries),
        "engine": engine,
        "exit_code": code,
        "detail": detail,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_arguments()
    _install_saas_contract()
    register_collection_hook(_COMPONENT, _collector, order=35)
    _INSTALLED = True


__all__ = ["configure_audit_argv", "install", "install_worker_projection"]
