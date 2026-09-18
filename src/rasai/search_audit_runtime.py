"""Point-in-time Search Intelligence as an AUD collection phase.

Search Monitoring remains a separate SaaS job.  This module covers Search Intelligence
explicitly requested for one AUD execution.  The queries are execution input, not
persistent environment configuration, and are collected before evidence sealing so
later AI tasks may consume the persisted SERP/competitive observations.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    SUCCESS,
    list_work_items,
    register_work_item,
    set_work_item_status,
)
from rasai.audit_phase_runtime import register_ai_hook, register_collection_hook
from rasai.provider_runtime_policy import AI_TIMEOUT_ENV, DEFAULT_AI_TIMEOUT_SECONDS
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
        "search_compare_content",
        "search_max_content_pages",
        "search_content_timeout_seconds",
        "search_content_max_bytes",
        "search_content_max_redirects",
        "search_ai_competitive",
        "search_ymyl_mode",
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
            comparison = audit.add_mutually_exclusive_group()
            comparison.add_argument(
                "--search-compare-content",
                dest="search_compare_content",
                action="store_true",
            )
            comparison.add_argument(
                "--no-search-compare-content",
                dest="search_compare_content",
                action="store_false",
            )
            audit.set_defaults(search_compare_content=False)
            audit.add_argument("--search-max-content-pages", type=int, default=3)
            audit.add_argument("--search-content-timeout-seconds", type=float, default=10.0)
            audit.add_argument("--search-content-max-bytes", type=int, default=2_000_000)
            audit.add_argument("--search-content-max-redirects", type=int, default=5)
            competitive_ai = audit.add_mutually_exclusive_group()
            competitive_ai.add_argument(
                "--search-ai-competitive",
                dest="search_ai_competitive",
                action="store_true",
            )
            competitive_ai.add_argument(
                "--no-search-ai-competitive",
                dest="search_ai_competitive",
                action="store_false",
            )
            audit.set_defaults(search_ai_competitive=False)
            audit.add_argument(
                "--search-ymyl-mode",
                choices=("AUTO", "ON", "OFF"),
                default="AUTO",
            )
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
                contract.AuditJobOption("search_compare_content", False, "boolean"),
                contract.AuditJobOption("search_max_content_pages", 3, "integer"),
                contract.AuditJobOption("search_content_timeout_seconds", 10.0, "number"),
                contract.AuditJobOption("search_content_max_bytes", 2_000_000, "integer"),
                contract.AuditJobOption("search_content_max_redirects", 5, "integer"),
                contract.AuditJobOption("search_ai_competitive", False, "boolean"),
                contract.AuditJobOption(
                    "search_ymyl_mode",
                    "AUTO",
                    "enum",
                    ("AUTO", "ON", "OFF"),
                ),
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
            compare_content = payload.get("search_compare_content", normalized.get("search_compare_content", False))
            if not isinstance(compare_content, bool):
                raise ValueError("AUDIT payload search_compare_content must be boolean")
            max_content_pages = payload.get("search_max_content_pages", normalized.get("search_max_content_pages", 3))
            if isinstance(max_content_pages, bool) or not isinstance(max_content_pages, int) or not 0 <= max_content_pages <= 100:
                raise ValueError("AUDIT payload search_max_content_pages must be an integer between 0 and 100")
            content_timeout = payload.get("search_content_timeout_seconds", normalized.get("search_content_timeout_seconds", 10.0))
            if isinstance(content_timeout, bool) or not isinstance(content_timeout, (int, float)) or not math.isfinite(float(content_timeout)) or float(content_timeout) <= 0:
                raise ValueError("AUDIT payload search_content_timeout_seconds must be a finite number > 0")
            content_max_bytes = payload.get("search_content_max_bytes", normalized.get("search_content_max_bytes", 2_000_000))
            if isinstance(content_max_bytes, bool) or not isinstance(content_max_bytes, int) or content_max_bytes <= 0:
                raise ValueError("AUDIT payload search_content_max_bytes must be an integer > 0")
            content_max_redirects = payload.get("search_content_max_redirects", normalized.get("search_content_max_redirects", 5))
            if isinstance(content_max_redirects, bool) or not isinstance(content_max_redirects, int) or content_max_redirects < 0:
                raise ValueError("AUDIT payload search_content_max_redirects must be an integer >= 0")
            ai_competitive = payload.get("search_ai_competitive", normalized.get("search_ai_competitive", False))
            if not isinstance(ai_competitive, bool):
                raise ValueError("AUDIT payload search_ai_competitive must be boolean")
            if ai_competitive and not compare_content:
                raise ValueError("AUDIT payload search_ai_competitive requires search_compare_content=true")
            if ai_competitive and str(normalized.get("ai_provider") or "none").casefold() == "none":
                raise ValueError("AUDIT payload search_ai_competitive requires the main AI provider")
            ymyl_mode = payload.get("search_ymyl_mode", normalized.get("search_ymyl_mode", "AUTO"))
            if not isinstance(ymyl_mode, str) or ymyl_mode.strip().upper() not in {"AUTO", "ON", "OFF"}:
                raise ValueError("AUDIT payload search_ymyl_mode must be AUTO, ON or OFF")
            normalized.update(
                {
                    "search_queries": queries,
                    "search_depth": int(depth),
                    "search_region": region.strip(),
                    "search_device": device.strip().casefold(),
                    "search_competitive": competitive,
                    "search_compare_content": compare_content,
                    "search_max_content_pages": int(max_content_pages),
                    "search_content_timeout_seconds": float(content_timeout),
                    "search_content_max_bytes": int(content_max_bytes),
                    "search_content_max_redirects": int(content_max_redirects),
                    "search_ai_competitive": ai_competitive,
                    "search_ymyl_mode": ymyl_mode.strip().upper(),
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
        argv.append(
            "--search-compare-content"
            if bool(payload["search_compare_content"])
            else "--no-search-compare-content"
        )
        argv.extend(("--search-max-content-pages", str(int(payload["search_max_content_pages"]))))
        argv.extend(("--search-content-timeout-seconds", str(float(payload["search_content_timeout_seconds"]))))
        argv.extend(("--search-content-max-bytes", str(int(payload["search_content_max_bytes"]))))
        argv.extend(("--search-content-max-redirects", str(int(payload["search_content_max_redirects"]))))
        argv.append(
            "--search-ai-competitive"
            if bool(payload["search_ai_competitive"])
            else "--no-search-ai-competitive"
        )
        argv.extend(("--search-ymyl-mode", str(payload["search_ymyl_mode"]).upper()))
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

    try:
        runtime_snapshot = SerpRuntimeConfig.from_environment(validate=False)
        runtime_configuration = {
            "mode": str(runtime_snapshot.mode),
            "provider": str(runtime_snapshot.provider),
            "fixture_path": str(runtime_snapshot.fixture_path) if runtime_snapshot.fixture_path else "",
            "max_queries": int(runtime_snapshot.max_queries),
            "max_requests": int(runtime_snapshot.max_requests),
            "max_depth": int(runtime_snapshot.max_depth),
            "max_competitors": int(runtime_snapshot.max_competitors),
            "timeout_seconds": float(runtime_snapshot.timeout_seconds),
            "retries": int(runtime_snapshot.retries),
            "min_interval_seconds": float(runtime_snapshot.min_interval_seconds),
        }
    except (OSError, TypeError, ValueError):
        runtime_configuration = {}
    configuration = {
        "requested": True,
        "queries": list(queries),
        "depth": int(getattr(args, "search_depth", 20)),
        "region": str(getattr(args, "search_region", "") or ""),
        "device": str(getattr(args, "search_device", "mobile")),
        "competitive": bool(getattr(args, "search_competitive", True)),
        "compare_content": bool(getattr(args, "search_compare_content", False)),
        "max_content_pages": int(getattr(args, "search_max_content_pages", 3)),
        "content_timeout_seconds": float(getattr(args, "search_content_timeout_seconds", 10.0)),
        "content_max_bytes": int(getattr(args, "search_content_max_bytes", 2_000_000)),
        "content_max_redirects": int(getattr(args, "search_content_max_redirects", 5)),
        "ai_competitive": bool(getattr(args, "search_ai_competitive", False)),
        "ymyl_mode": str(getattr(args, "search_ymyl_mode", "AUTO") or "AUTO").upper(),
        "market": str(getattr(args, "market", "BR") or "BR"),
        "language": str(getattr(args, "language", "pt-BR") or "pt-BR"),
        "ai_provider": str(getattr(args, "ai_provider", "none") or "none"),
        "ai_model": str(getattr(args, "ai_model", "") or ""),
        "ai_timeout_seconds": float(
            os.environ.get(AI_TIMEOUT_ENV, str(DEFAULT_AI_TIMEOUT_SECONDS))
            or DEFAULT_AI_TIMEOUT_SECONDS
        ),
        **runtime_configuration,
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
    if bool(getattr(args, "search_compare_content", False)):
        max_content_pages = min(
            int(getattr(args, "search_max_content_pages", 3)),
            int(config.max_competitors),
        )
        command.extend(
            (
                "--compare-content",
                "--max-content-pages", str(max_content_pages),
                "--content-timeout", str(float(getattr(args, "search_content_timeout_seconds", 10.0))),
                "--content-max-bytes", str(int(getattr(args, "search_content_max_bytes", 2_000_000))),
                "--content-max-redirects", str(int(getattr(args, "search_content_max_redirects", 5))),
            )
        )
        if len(queries) == 1 and target:
            command.extend(("--customer-url", target))

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


def _persisted_search_configuration(workspace: Any, audit_id: str) -> dict[str, Any]:
    for item in list_work_items(workspace, audit_id):
        if str(getattr(item, "component", "")) == _COMPONENT and str(getattr(item, "scope_key", "AUDIT")) == "AUDIT":
            return dict(getattr(item, "configuration", {}) or {})
    return {}


def _competitive_ai_input_from_artifact(
    observation_id: str,
    payload: Mapping[str, Any],
    *,
    market: str,
    language: str,
    ymyl_mode: str,
    artifact_reference: str,
):
    from rasai.search_intelligence.competitive_ai import CompetitiveAiEvidence, CompetitiveAiInput

    if str(payload.get("comparison_status") or "") != "CONSOLIDATED":
        raise ValueError("competitive AI requires consolidated deterministic content")
    selection = payload.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("competitive evidence selection is missing")
    customer = payload.get("customer_page")
    if not isinstance(customer, Mapping) or str(customer.get("status") or "") != "OBSERVED":
        raise ValueError("competitive AI requires observed customer content")

    selected = selection.get("selected_candidates")
    selected_count = len(selected) if isinstance(selected, list) else 0
    customer_result = selection.get("customer_result")
    customer_position = customer_result.get("position") if isinstance(customer_result, Mapping) else None
    evidence = [
        CompetitiveAiEvidence(
            "CE-QUERY",
            "SEARCH_QUERY_CONTEXT",
            "SERP_OBSERVATION",
            {
                "query": str(selection.get("query") or ""),
                "customer_domain": str(selection.get("customer_domain") or ""),
                "customer_position": customer_position,
                "candidate_count": selected_count,
            },
            artifact_reference,
        ),
        CompetitiveAiEvidence(
            "CE-CUSTOMER",
            "CUSTOMER_PAGE_FEATURES",
            str(customer.get("final_url") or customer.get("requested_url") or "CUSTOMER"),
            dict(customer),
            artifact_reference,
        ),
    ]
    competitors = payload.get("competitor_pages")
    if isinstance(competitors, list):
        observed_index = 0
        for page in competitors:
            if not isinstance(page, Mapping) or str(page.get("status") or "") != "OBSERVED":
                continue
            observed_index += 1
            evidence.append(
                CompetitiveAiEvidence(
                    f"CE-COMP-{observed_index:03d}",
                    "OBSERVED_LEADER_PAGE_FEATURES",
                    str(page.get("final_url") or page.get("requested_url") or "COMPETITOR"),
                    dict(page),
                    artifact_reference,
                )
            )
    gaps = payload.get("gaps")
    if isinstance(gaps, list):
        gap_index = 0
        for gap in gaps:
            if not isinstance(gap, Mapping):
                continue
            gap_index += 1
            evidence.append(
                CompetitiveAiEvidence(
                    f"CE-GAP-{gap_index:03d}",
                    "DETERMINISTIC_CONTENT_DIFFERENCE",
                    "RASAI_DETERMINISTIC_COMPARISON",
                    dict(gap),
                    artifact_reference,
                )
            )
    return CompetitiveAiInput(
        observation_id=observation_id,
        query=str(selection.get("query") or ""),
        market=market,
        language=language,
        ymyl_mode=ymyl_mode,
        evidence=tuple(evidence),
    )


def _competitive_ai_rows(workspace: Any, audit_id: str) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='serp_competitive_analyses'"
        ).fetchone()
        if table is None:
            return ()
        rows = connection.execute(
            """SELECT a.observation_id,a.evidence_ref,a.evidence_sha256,
                      o.query,o.country,o.language
               FROM serp_competitive_analyses a
               JOIN serp_observations o ON o.observation_id=a.observation_id
               WHERE a.audit_id=? AND a.comparison_status='CONSOLIDATED'
               ORDER BY o.collected_at,a.observation_id""",
            (audit_id,),
        ).fetchall()
        return tuple(dict(row) for row in rows)
    finally:
        connection.close()


def _competitive_ai_hook(
    *,
    audit_id: str,
    workspace: Any,
    evidence_snapshot: Any = None,
    source_blocked: bool = False,
):
    configuration = _persisted_search_configuration(workspace, audit_id)
    if not configuration or not bool(configuration.get("ai_competitive", False)):
        return {"status": "DISABLED", "requested": False}
    if source_blocked:
        return {"status": "SKIPPED_SOURCE_BLOCKER", "requested": True}
    if not bool(configuration.get("compare_content", False)):
        return {
            "status": "NOT_ELIGIBLE",
            "requested": True,
            "reason": "CONTENT_COMPARISON_REQUIRED",
        }

    rows = _competitive_ai_rows(workspace, audit_id)
    if not rows:
        return {
            "status": "NOT_ELIGIBLE",
            "requested": True,
            "reason": "NO_CONSOLIDATED_COMPETITIVE_EVIDENCE",
        }

    from rasai.ai_governance import begin_round, complete_round, latest_evidence_snapshot, register_task
    from rasai.search_intelligence.competitive_ai import (
        COMPETITIVE_AI_CONTRACT_VERSION,
        COMPETITIVE_AI_PROMPT_ID,
        COMPETITIVE_AI_PROMPT_VERSION,
        CompetitiveAiResult,
        CompetitiveAiState,
        build_competitive_ai_provider,
    )
    from rasai.search_intelligence.competitive_ai_persistence import (
        CompetitiveAiRepository,
        FilesystemCompetitiveAiEvidenceSink,
        competitive_ai_result_payload,
    )

    snapshot = evidence_snapshot or latest_evidence_snapshot(workspace, audit_id)
    snapshot_id = str(getattr(snapshot, "evidence_snapshot_id", "") or "")
    if not snapshot_id:
        return {
            "status": "NOT_ELIGIBLE",
            "requested": True,
            "reason": "SEALED_EVIDENCE_REQUIRED",
        }

    provider_name = str(configuration.get("ai_provider") or "none").casefold()
    model = str(configuration.get("ai_model") or "").strip() or None
    timeout = float(configuration.get("ai_timeout_seconds") or DEFAULT_AI_TIMEOUT_SECONDS)
    provider = build_competitive_ai_provider(
        provider_name,
        model=(model if provider_name not in {"auto", "none"} else None),
        timeout=timeout,
    )
    repository = CompetitiveAiRepository.from_workspace(Path(workspace.root))
    sink = FilesystemCompetitiveAiEvidenceSink(Path(workspace.root))
    available = 0
    limitations = 0
    try:
        for row in rows:
            observation_id = str(row["observation_id"])
            evidence_ref = str(row.get("evidence_ref") or "")
            try:
                if not evidence_ref:
                    raise ValueError("competitive evidence artifact reference is missing")
                artifact = Path(workspace.root) / evidence_ref
                raw = artifact.read_bytes()
                expected = str(row.get("evidence_sha256") or "")
                if expected and sha256(raw).hexdigest() != expected:
                    raise ValueError("competitive evidence SHA-256 mismatch")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, Mapping):
                    raise ValueError("competitive evidence artifact must be an object")
                competitive_input = _competitive_ai_input_from_artifact(
                    observation_id,
                    payload,
                    market=str(configuration.get("market") or row.get("country") or "BR"),
                    language=str(configuration.get("language") or row.get("language") or "pt-BR"),
                    ymyl_mode=str(configuration.get("ymyl_mode") or "AUTO").upper(),
                    artifact_reference=evidence_ref,
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
                result = CompetitiveAiResult(
                    CompetitiveAiState.UNAVAILABLE,
                    reason=f"COMPETITIVE_EVIDENCE_INVALID:{type(exc).__name__}:{str(exc)[:240]}",
                )
                limitations += 1
                result_ref, result_sha = sink.write(observation_id, result)
                repository.save(
                    observation_id,
                    result,
                    evidence_ref=result_ref,
                    evidence_sha256=result_sha,
                )
                continue

            requirement = "competitive_semantic_opportunities"
            task_id = register_task(
                workspace=workspace,
                audit_id=audit_id,
                purpose="COMPETITIVE_INTELLIGENCE",
                scope_type="SERP_OBSERVATION",
                scope_key=observation_id,
                evidence_snapshot_id=snapshot_id,
                requirements=(requirement,),
                semantic_contract_version=COMPETITIVE_AI_CONTRACT_VERSION,
                prompt_id=COMPETITIVE_AI_PROMPT_ID,
                prompt_version=COMPETITIVE_AI_PROMPT_VERSION,
            )
            round_id = begin_round(
                workspace=workspace,
                ai_task_id=task_id,
                requested_requirements=(requirement,),
                input_payload=competitive_input.provider_payload(),
                input_summary={
                    "observation_id": observation_id,
                    "query": str(row.get("query") or ""),
                    "evidence_count": len(competitive_input.evidence),
                },
            )
            try:
                result = provider.analyze(competitive_input)
            except Exception as exc:
                result = CompetitiveAiResult(
                    CompetitiveAiState.UNAVAILABLE,
                    reason=f"COMPETITIVE_AI_RUNTIME_ERROR:{type(exc).__name__}:{str(exc)[:240]}",
                )
            result_payload = competitive_ai_result_payload(result)
            if result.state is CompetitiveAiState.AVAILABLE:
                available += 1
                complete_round(
                    workspace=workspace,
                    ai_round_id=round_id,
                    accepted={requirement: result_payload},
                    output_payload=result_payload,
                )
            else:
                limitations += 1
                complete_round(
                    workspace=workspace,
                    ai_round_id=round_id,
                    missing=(requirement,),
                    output_payload=result_payload,
                    failed=result.state is CompetitiveAiState.UNAVAILABLE,
                )
            result_ref, result_sha = sink.write(observation_id, result)
            repository.save(
                observation_id,
                result,
                evidence_ref=result_ref,
                evidence_sha256=result_sha,
            )
    finally:
        repository.close()

    try:
        from rasai.search_intelligence.runtime import _refresh_search_intelligence_report
        _refresh_search_intelligence_report(Path(workspace.root))
    except Exception:
        pass
    return {
        "status": "COMPLETE" if limitations == 0 else "COMPLETE_WITH_LIMITATIONS",
        "requested": True,
        "observations": len(rows),
        "available": available,
        "limitations": limitations,
        "provider": provider_name,
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_arguments()
    _install_saas_contract()
    register_collection_hook(_COMPONENT, _collector, order=35)
    register_ai_hook("COMPETITIVE_INTELLIGENCE", _competitive_ai_hook, order=35)
    _INSTALLED = True


__all__ = [
    "configure_audit_argv",
    "install",
    "install_worker_projection",
    "_competitive_ai_hook",
]
