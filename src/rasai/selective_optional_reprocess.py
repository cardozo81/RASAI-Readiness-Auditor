"""Selective recovery for optional AUD components owned outside the core RPR loops.

Search Intelligence is a console-AUD observation and is replayed directly from its
persisted non-secret execution contract. Google Search Console and Improvement
Intelligence remain owned by their existing report-finalization runtimes. During an
RPR this adapter restores only non-secret original settings through a ContextVar,
reuses successful persisted results, and executes only work items that were unresolved
when the RPR started.

No pricing code lives here. AI/provider attempts and their observed costs remain owned
by the existing provider persistence/pricing path.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    REPLAY_SAFE,
    SUCCESS,
    list_work_items,
    register_work_item,
    set_work_item_status,
)
from rasai.execution_environment import override_environment, resolve_environment
from rasai.persistence import AuditWorkspace
from rasai.secret_safety import redact_text
from rasai.selective_reprocess_context import current, record_optional_evaluation, scope, should_execute

_INSTALLED = False
_OPTIONAL_COMPONENTS = frozenset({
    "SEARCH_INTELLIGENCE",
    "GOOGLE_SEARCH_CONSOLE",
    "IMPROVEMENT_INTELLIGENCE",
})


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def _item(workspace: Any, audit_id: str, component: str) -> Any | None:
    return next(
        (
            item
            for item in list_work_items(workspace, audit_id)
            if str(item.component) == component and str(item.scope_key) == "AUDIT"
        ),
        None,
    )


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _expired(item: Any | None) -> bool:
    if item is None or str(getattr(item, "temporal_mode", "")) != LIVE_RECOLLECTION:
        return False
    if str(getattr(item, "status", "")) == SUCCESS:
        return False
    deadline = _parse_time(getattr(item, "valid_until", None))
    return bool(deadline and datetime.now(timezone.utc) > deadline)


def _saved_console_configuration(workspace: Any, audit_id: str) -> dict[str, Any]:
    """Read the immutable non-secret execution snapshot when available."""
    connection = sqlite3.connect(workspace.database)
    try:
        if not _table_exists(connection, "audit_execution_configurations"):
            return {}
        row = connection.execute(
            "SELECT configuration_json FROM audit_execution_configurations WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    if not row or not row[0]:
        return {}
    try:
        value = json.loads(str(row[0]))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _saved_environment(workspace: Any, audit_id: str) -> dict[str, str]:
    payload = _saved_console_configuration(workspace, audit_id)
    settings = payload.get("settings")
    if not isinstance(settings, Mapping):
        return {}
    environment = settings.get("environment")
    if not isinstance(environment, Mapping):
        return {}
    return {
        str(key): str(value)
        for key, value in environment.items()
        if str(key) and value is not None and str(value).strip()
    }


def _backfill_console_search(workspace: Any, audit_id: str) -> None:
    """Index Search requested by the saved console contract when a work item is absent."""
    if _item(workspace, audit_id, "SEARCH_INTELLIGENCE") is not None:
        return
    payload = _saved_console_configuration(workspace, audit_id)
    search = payload.get("search_intelligence")
    if not isinstance(search, Mapping) or not bool(search.get("enabled")):
        return
    queries = [str(value).strip() for value in (search.get("queries") or []) if str(value).strip()]
    if not queries:
        return
    environment = _saved_environment(workspace, audit_id)
    config: dict[str, Any] = {
        "requested": True,
        "surface": "console-audit",
        "queries": queries,
        "depth": int(search.get("depth") or 20),
        "region": str(search.get("region") or ""),
        "device": str(search.get("device") or "mobile"),
        "competitive": bool(search.get("competitive", True)),
    }
    env_map = {
        "RASAI_SERP_MODE": "mode",
        "RASAI_SERP_PROVIDER": "provider",
        "RASAI_SERP_FIXTURE_PATH": "fixture_path",
        "RASAI_SERP_MAX_QUERIES": "max_queries",
        "RASAI_SERP_MAX_REQUESTS": "max_requests",
        "RASAI_SERP_MAX_DEPTH": "max_depth",
        "RASAI_SERP_MAX_COMPETITORS": "max_competitors",
        "RASAI_SERP_TIMEOUT_SECONDS": "timeout_seconds",
        "RASAI_SERP_RETRIES": "retries",
        "RASAI_SERP_MIN_INTERVAL_SECONDS": "min_interval_seconds",
    }
    for env_name, key in env_map.items():
        if environment.get(env_name):
            config[key] = environment[env_name]
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="SEARCH_INTELLIGENCE",
        required=True,
        temporal_mode=LIVE_RECOLLECTION,
        status="REQUESTED_NOT_EXECUTED",
        retryable=True,
        configuration=config,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="SEARCH_INTELLIGENCE",
        status="REQUESTED_NOT_EXECUTED",
        error_class="ORCHESTRATION",
        error_code="REQUESTED_NOT_EXECUTED",
        error_message="Search Intelligence consta da configuração original, mas não possui execução fulfillment indexada",
        retryable=True,
    )


def _improvement_run(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "improvement_intelligence_runs"):
            return None
        row = connection.execute(
            "SELECT * FROM improvement_intelligence_runs WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _gsc_service_run(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "standards_service_runs"):
            return None
        row = connection.execute(
            "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id='google-search-console'",
            (audit_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _reconcile_improvement_rpr(workspace: Any, audit_id: str) -> None:
    """Project the Improvement result using the original config plus current credential."""
    from rasai.fulfillment_execution_contract import NOT_CONFIGURED
    from rasai.improvement_intelligence import ImprovementConfig

    item = _item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
    if item is None:
        return
    try:
        cfg = ImprovementConfig.from_environment(resolve_environment())
    except Exception as exc:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=NOT_CONFIGURED,
            error_class="CONFIGURATION",
            error_code="IMPROVEMENT_CONFIGURATION_INVALID",
            error_message=redact_text(str(exc))[:1000],
            retryable=True,
        )
        return

    register_work_item(
        workspace,
        audit_id=audit_id,
        component="IMPROVEMENT_INTELLIGENCE",
        required=True,
        temporal_mode=REPLAY_SAFE,
        retryable=True,
        configuration={
            "requested": True,
            "provider": cfg.provider,
            "model": cfg.model,
            "reasoning": cfg.reasoning,
            "domains": list(cfg.domains),
            "max_recommendations": cfg.max_recommendations,
            "timeout_seconds": cfg.timeout_seconds,
            "language": cfg.language,
        },
    )
    run = _improvement_run(workspace, audit_id)
    if run is None:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=FAILED_RETRYABLE,
            error_class="ORCHESTRATION",
            error_code="IMPROVEMENT_RETRY_NOT_MATERIALIZED",
            error_message="Improvement Intelligence foi reavaliado, mas não materializou resultado persistido",
            retryable=True,
        )
        return
    status = str(run.get("status") or "").upper()
    if status == "COMPLETE":
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=SUCCESS,
            result_ref="improvement-intelligence:effective",
            retryable=False,
        )
        return
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="IMPROVEMENT_INTELLIGENCE",
        status=FAILED_RETRYABLE,
        error_class="AI_ANALYSIS",
        error_code=status or "IMPROVEMENT_INCOMPLETE",
        error_message=redact_text(str(run.get("reason") or "Improvement Intelligence não concluiu sem limitações"))[:1000],
        retryable=True,
    )


def _reconcile_gsc_rpr(workspace: Any, audit_id: str) -> None:
    """Project GSC using original non-secret settings and the current OAuth token."""
    from rasai.fulfillment_execution_contract import NOT_CONFIGURED
    from rasai.standards_service_registry import service, service_state

    item = _item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
    if item is None or _expired(item):
        return
    state_info = service_state(service("google-search-console"), resolve_environment())
    if not bool(state_info.get("configured")):
        missing = tuple(str(value) for value in state_info.get("missing_configuration", ()) if str(value))
        code = "SITE_URL_REQUIRED" if "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL" in missing else "CONFIGURATION_REQUIRED"
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="GOOGLE_SEARCH_CONSOLE",
            status=NOT_CONFIGURED,
            error_class="CONFIGURATION",
            error_code=code,
            error_message=("configuração ausente: " + ", ".join(missing)) if missing else "Google Search Console sem configuração completa",
            retryable=True,
        )
        return

    run = _gsc_service_run(workspace, audit_id)
    if run is None:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="GOOGLE_SEARCH_CONSOLE",
            status=FAILED_RETRYABLE,
            error_class="ORCHESTRATION",
            error_code="GSC_RETRY_NOT_MATERIALIZED",
            error_message="Google Search Console foi reavaliado, mas não materializou execução persistida",
            retryable=True,
        )
        return
    state = str(run.get("state") or "").upper()
    attempted = int(run.get("targets_attempted") or 0)
    succeeded = int(run.get("targets_succeeded") or 0)
    if state in {"SUCCESS", "READY"} and (attempted == 0 or succeeded == attempted):
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="GOOGLE_SEARCH_CONSOLE",
            status=SUCCESS,
            result_ref="standards-service:google-search-console:effective",
            retryable=False,
        )
        return
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="GOOGLE_SEARCH_CONSOLE",
        status=FAILED_RETRYABLE,
        error_class="EXTERNAL_SERVICE",
        error_code=state or "SERVICE_INCOMPLETE",
        error_message=f"Google Search Console terminou em {state or 'UNKNOWN'} ({succeeded}/{attempted} alvos com sucesso)",
        retryable=True,
    )


def _effective_improvement_configuration(
    item: Any,
    run: Mapping[str, Any] | None,
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve fulfillment metadata from the executed run before current environment."""
    from rasai.improvement_intelligence import (
        AI_ANALYSIS_LANGUAGE_ENV,
        DEFAULT_DOMAINS,
        DOMAINS_ENV,
        MAX_RECOMMENDATIONS_ENV,
        MODEL_ENV,
        PROVIDER_ENV,
        REASONING_ENV,
        TIMEOUT_ENV,
    )

    existing = dict(getattr(item, "configuration", {}) or {})
    values: dict[str, Any] = {
        "requested": True,
        "provider": existing.get("provider") or str(environment.get(PROVIDER_ENV) or ""),
        "model": existing.get("model") or str(environment.get(MODEL_ENV) or ""),
        "reasoning": existing.get("reasoning") or str(environment.get(REASONING_ENV) or ""),
        "domains": existing.get("domains") or [
            value.strip().upper()
            for value in str(environment.get(DOMAINS_ENV) or "").replace(";", ",").split(",")
            if value.strip()
        ] or list(DEFAULT_DOMAINS),
        "max_recommendations": existing.get("max_recommendations") or str(environment.get(MAX_RECOMMENDATIONS_ENV) or "30"),
        "timeout_seconds": existing.get("timeout_seconds") or str(environment.get(TIMEOUT_ENV) or "240"),
        "language": existing.get("language") or str(environment.get(AI_ANALYSIS_LANGUAGE_ENV) or "auto"),
    }
    if run is not None:
        domains = _safe_json(run.get("domains_json"), values["domains"])
        values.update({
            "provider": run.get("provider") or values["provider"],
            "model": run.get("model") or values["model"],
            "reasoning": run.get("reasoning") or values["reasoning"],
            "domains": domains if isinstance(domains, list) else values["domains"],
            "max_recommendations": run.get("max_recommendations") or values["max_recommendations"],
            "language": run.get("analysis_language") or values["language"],
        })
    return values


def _augment_reconciliation_configuration() -> None:
    """Persist complete non-secret optional-service configuration into each work item."""
    from rasai import fulfillment_execution_contract as contract

    improvement = contract._reconcile_requested_improvement
    if not bool(getattr(improvement, "_rasai_optional_config", False)):
        def reconcile_improvement(workspace: Any, audit_id: str) -> None:
            active_context = current()
            if active_context is not None and active_context.audit_id == audit_id:
                _reconcile_improvement_rpr(workspace, audit_id)
                return
            improvement(workspace, audit_id)
            item = _item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
            if item is None:
                return
            from rasai.improvement_intelligence import (
                AI_ANALYSIS_LANGUAGE_ENV,
                DEFAULT_DOMAINS,
                DOMAINS_ENV,
                MAX_RECOMMENDATIONS_ENV,
                MODEL_ENV,
                PROVIDER_ENV,
                REASONING_ENV,
                TIMEOUT_ENV,
                ImprovementConfig,
            )

            values = _effective_improvement_configuration(
                item,
                _improvement_run(workspace, audit_id),
                os.environ,
            )
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                required=True,
                temporal_mode=REPLAY_SAFE,
                retryable=bool(item.retryable),
                configuration=values,
            )

        reconcile_improvement._rasai_optional_config = True
        reconcile_improvement._rasai_original = improvement
        contract._reconcile_requested_improvement = reconcile_improvement

    services = contract._reconcile_explicit_services
    if not bool(getattr(services, "_rasai_optional_config", False)):
        def reconcile_services(workspace: Any, audit_id: str) -> None:
            active_context = current()
            if active_context is not None and active_context.audit_id == audit_id:
                _reconcile_gsc_rpr(workspace, audit_id)
                return
            services(workspace, audit_id)
            item = _item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
            if item is None:
                return
            from rasai.standards_gsc_policy import (
                GSC_FINAL_DATA_LAG_DAYS_ENV,
                GSC_SEARCH_ANALYTICS_DAYS_ENV,
                GSC_SEARCH_MAX_ROWS_ENV,
            )
            from rasai.standards_service_registry import (
                GSC_SITE_URL_ENV,
                STANDARDS_MAX_URLS_ENV,
                STANDARDS_TIMEOUT_ENV,
            )
            environment = os.environ
            values = {
                "requested": True,
                "service_id": "google-search-console",
                "site_url": str(environment.get(GSC_SITE_URL_ENV) or item.configuration.get("site_url") or ""),
                "max_urls": str(environment.get(STANDARDS_MAX_URLS_ENV) or item.configuration.get("max_urls") or ""),
                "timeout_seconds": str(environment.get(STANDARDS_TIMEOUT_ENV) or item.configuration.get("timeout_seconds") or ""),
                "search_analytics_days": str(environment.get(GSC_SEARCH_ANALYTICS_DAYS_ENV) or item.configuration.get("search_analytics_days") or ""),
                "search_max_rows": str(environment.get(GSC_SEARCH_MAX_ROWS_ENV) or item.configuration.get("search_max_rows") or ""),
                "final_data_lag_days": str(environment.get(GSC_FINAL_DATA_LAG_DAYS_ENV) or item.configuration.get("final_data_lag_days") or ""),
            }
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="GOOGLE_SEARCH_CONSOLE",
                required=True,
                temporal_mode=LIVE_RECOLLECTION,
                retryable=bool(item.retryable),
                configuration=values,
                valid_until=getattr(item, "valid_until", None),
            )

        reconcile_services._rasai_optional_config = True
        reconcile_services._rasai_original = services
        contract._reconcile_explicit_services = reconcile_services


def _validate_success_integrity(workspace: Any, audit_id: str) -> None:
    """A successful optional work item must still have the persisted evidence it claims."""
    gsc = _gsc_service_run(workspace, audit_id)
    improvement = _improvement_run(workspace, audit_id)
    connection = sqlite3.connect(workspace.database)
    try:
        search_count = None
        if _table_exists(connection, "serp_observations"):
            search_count = int(connection.execute(
                "SELECT COUNT(*) FROM serp_observations WHERE audit_id=?",
                (audit_id,),
            ).fetchone()[0])
    finally:
        connection.close()

    checks = (
        ("GOOGLE_SEARCH_CONSOLE", bool(gsc and str(gsc.get("state") or "").upper() in {"SUCCESS", "READY"} and gsc.get("details_json"))),
        ("IMPROVEMENT_INTELLIGENCE", bool(improvement and str(improvement.get("status") or "").upper() == "COMPLETE")),
        ("SEARCH_INTELLIGENCE", search_count is not None and search_count > 0),
    )
    for component, valid in checks:
        item = _item(workspace, audit_id, component)
        if item is None or str(item.status) != SUCCESS or valid:
            continue
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=component,
            status=FAILED_RETRYABLE,
            error_class="INTEGRITY",
            error_code="PERSISTED_EVIDENCE_MISSING",
            error_message=f"{component} estava marcado como SUCCESS, mas sua evidência persistida não está disponível",
            retryable=True,
        )


def _audit_domain(workspace: Any, audit_id: str) -> str:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid LIMIT 1",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    host = urlsplit(str(row[0]) if row else "").hostname
    if not host:
        raise ValueError("não foi possível derivar o domínio auditado para reprocessar Search Intelligence")
    return host


def _configured_value(values: Mapping[str, Any], name: str, default: Any) -> Any:
    raw = values.get(name)
    return default if raw is None or raw == "" else raw


def _search_runtime_config(item: Any):
    from rasai.search_intelligence.config import SerpRuntimeConfig

    values = dict(getattr(item, "configuration", {}) or {})
    fixture = str(_configured_value(values, "fixture_path", "")).strip()
    return SerpRuntimeConfig(
        mode=str(_configured_value(values, "mode", "disabled")),
        provider=str(_configured_value(values, "provider", "serpapi")),
        fixture_path=Path(fixture) if fixture else None,
        max_queries=int(_configured_value(values, "max_queries", 10)),
        max_requests=int(_configured_value(values, "max_requests", 10)),
        max_depth=int(_configured_value(values, "max_depth", 20)),
        max_competitors=int(_configured_value(values, "max_competitors", 10)),
        timeout_seconds=float(_configured_value(values, "timeout_seconds", 20.0)),
        retries=int(_configured_value(values, "retries", 1)),
        min_interval_seconds=float(_configured_value(values, "min_interval_seconds", 1.0)),
    ).validate()


def _recover_search(workspace: Any, audit_id: str, item: Any) -> bool:
    from rasai.search_intelligence.competitive_runtime import execute_competitive_intelligence
    from rasai.search_intelligence.models import DomainMatchStatus, QueryOrigin, SerpQueryRequest, new_identifier
    from rasai.search_intelligence.provider_catalog import serp_provider_registration
    from rasai.search_intelligence.runtime import execute_search

    values = dict(getattr(item, "configuration", {}) or {})
    queries = tuple(str(value).strip() for value in values.get("queries", ()) if str(value).strip())
    if not queries:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEARCH_INTELLIGENCE",
            status=FAILED_RETRYABLE,
            error_class="CONFIGURATION",
            error_code="SEARCH_QUERIES_REQUIRED",
            error_message="a configuração original de Search Intelligence não possui termos persistidos",
            retryable=True,
        )
        return False

    try:
        runtime = _search_runtime_config(item)
        domain = _audit_domain(workspace, audit_id)
        registration = serp_provider_registration(runtime.provider)
        engine = str(values.get("engine") or (registration.engine if registration is not None else "google"))
        run_id = new_identifier("SERP-RPR")
        requests = tuple(
            SerpQueryRequest(
                query=query,
                engine=engine,
                country=str(values.get("market") or "BR"),
                region=str(values.get("region") or "") or None,
                language=str(values.get("language") or "pt-BR"),
                device=str(values.get("device") or "mobile"),
                depth=int(values.get("depth") or 20),
                domain_of_interest=domain,
                run_id=run_id,
                query_origin=QueryOrigin.MANUAL,
                config_metadata={"surface": "audit-reprocess"},
            )
            for query in queries
        )
        execution = execute_search(
            requests,
            config=runtime,
            environment=os.environ,
            workspace_root=workspace.root,
            fixture_path=runtime.fixture_path,
        )
        if bool(values.get("competitive", True)):
            execute_competitive_intelligence(
                execution,
                content_enabled=False,
                max_competitor_pages=runtime.max_competitors,
                workspace_root=workspace.root,
            )
    except (OSError, TypeError, ValueError) as exc:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEARCH_INTELLIGENCE",
            status="NOT_CONFIGURED",
            error_class="CONFIGURATION",
            error_code="SEARCH_CONFIGURATION_INVALID",
            error_message=redact_text(str(exc))[:1000],
            retryable=True,
        )
        return False
    except Exception as exc:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEARCH_INTELLIGENCE",
            status=FAILED_RETRYABLE,
            error_class="SEARCH_PROVIDER",
            error_code="SEARCH_INTELLIGENCE_RUNTIME_ERROR",
            error_message=redact_text(f"{type(exc).__name__}: {exc}")[:1000],
            retryable=True,
        )
        return False

    failed = tuple(
        result
        for result in execution.results
        if result.domain_status in {DomainMatchStatus.ERROR, DomainMatchStatus.UNAVAILABLE, DomainMatchStatus.DISABLED}
    )
    if not failed and execution.results:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEARCH_INTELLIGENCE",
            status=SUCCESS,
            result_ref="search-intelligence:effective",
            retryable=False,
        )
        return True
    first = failed[0] if failed else None
    detail = (
        f"{getattr(first, 'error_code', None) or getattr(first, 'domain_status', 'UNKNOWN')}: "
        f"{getattr(first, 'error_message', None) or 'observação Search não concluída'}"
        if first is not None
        else "Search Intelligence não produziu observações"
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="SEARCH_INTELLIGENCE",
        status=FAILED_RETRYABLE,
        error_class="SEARCH_PROVIDER",
        error_code=str(getattr(first, "error_code", None) or "SEARCH_INTELLIGENCE_RETRY_INCOMPLETE"),
        error_message=redact_text(detail)[:1000],
        retryable=True,
    )
    return False


def _persisted_gsc_result(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    row = _gsc_service_run(workspace, audit_id)
    if row is None:
        return None
    try:
        details = json.loads(str(row.get("details_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        details = {}
    result = dict(details) if isinstance(details, dict) else {}
    result.update({
        "service_state": str(row.get("state") or result.get("service_state") or "SUCCESS"),
        "collection_state": str(row.get("state") or result.get("collection_state") or "SUCCESS"),
        "targets_attempted": int(row.get("targets_attempted") or result.get("targets_attempted") or 0),
        "targets_succeeded": int(row.get("targets_succeeded") or result.get("targets_succeeded") or 0),
        "requested": True,
        "configured": True,
        "effective_enabled": True,
    })
    result.setdefault("operations", [])
    result.setdefault("errors", [])
    return result


def _persisted_improvement_result(workspace: Any, audit_id: str) -> Any | None:
    from rasai.improvement_intelligence import ImprovementResult

    row = _improvement_run(workspace, audit_id)
    if row is None:
        return None
    return ImprovementResult(
        status=str(row.get("status") or "COMPLETE"),
        target_url=str(row["target_url"]) if row.get("target_url") else None,
        findings_count=int(row.get("findings_count") or 0),
        recommendations_count=int(row.get("recommendations_count") or 0),
        provider=str(row["provider"]) if row.get("provider") else None,
        model=str(row["model"]) if row.get("model") else None,
        reasoning=str(row["reasoning"]) if row.get("reasoning") else None,
        reason=str(row["reason"]) if row.get("reason") else None,
        reused=True,
    )


def _optional_environment_values(workspace: Any, audit_id: str) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    improvement = _item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
    if improvement is not None:
        from rasai.improvement_intelligence import (
            AI_ANALYSIS_LANGUAGE_ENV,
            DOMAINS_ENV,
            ENABLED_ENV,
            MAX_RECOMMENDATIONS_ENV,
            MODEL_ENV,
            PROVIDER_ENV,
            REASONING_ENV,
            TIMEOUT_ENV,
        )
        cfg = dict(improvement.configuration or {})
        overrides[ENABLED_ENV] = "true"
        for env_name, key in (
            (PROVIDER_ENV, "provider"),
            (MODEL_ENV, "model"),
            (REASONING_ENV, "reasoning"),
            (MAX_RECOMMENDATIONS_ENV, "max_recommendations"),
            (TIMEOUT_ENV, "timeout_seconds"),
            (AI_ANALYSIS_LANGUAGE_ENV, "language"),
        ):
            if cfg.get(key) not in (None, ""):
                overrides[env_name] = cfg[key]
        domains = cfg.get("domains")
        if isinstance(domains, (list, tuple)) and domains:
            overrides[DOMAINS_ENV] = ",".join(str(value) for value in domains)

    gsc = _item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
    if gsc is not None:
        from rasai.standards_gsc_policy import (
            GSC_FINAL_DATA_LAG_DAYS_ENV,
            GSC_SEARCH_ANALYTICS_DAYS_ENV,
            GSC_SEARCH_MAX_ROWS_ENV,
        )
        from rasai.standards_service_registry import (
            GSC_ENABLED_ENV,
            GSC_SITE_URL_ENV,
            STANDARDS_MAX_URLS_ENV,
            STANDARDS_TIMEOUT_ENV,
        )
        cfg = dict(gsc.configuration or {})
        overrides[GSC_ENABLED_ENV] = "true"
        for env_name, key in (
            (GSC_SITE_URL_ENV, "site_url"),
            (STANDARDS_MAX_URLS_ENV, "max_urls"),
            (STANDARDS_TIMEOUT_ENV, "timeout_seconds"),
            (GSC_SEARCH_ANALYTICS_DAYS_ENV, "search_analytics_days"),
            (GSC_SEARCH_MAX_ROWS_ENV, "search_max_rows"),
            (GSC_FINAL_DATA_LAG_DAYS_ENV, "final_data_lag_days"),
        ):
            if cfg.get(key) not in (None, ""):
                overrides[env_name] = cfg[key]
    return overrides


@contextmanager
def _original_optional_environment(workspace: Any, audit_id: str) -> Iterator[None]:
    """Restore original non-secret settings without mutating process-wide environment."""
    with override_environment(_optional_environment_values(workspace, audit_id)):
        yield


def _install_contextual_optional_hooks() -> None:
    """Install stable ContextVar-aware hooks; never swap functions per execution."""
    from rasai import improvement_intelligence_runtime as improvement_runtime
    from rasai import standards_gsc_observability_runtime as gsc_runtime

    original_config = improvement_runtime.ImprovementConfig
    if not bool(getattr(original_config, "_rasai_contextual_optional_config", False)):
        class ContextualImprovementConfig:
            _rasai_contextual_optional_config = True

            @classmethod
            def from_environment(cls, env: Mapping[str, str] | None = None):
                return original_config.from_environment(resolve_environment(env))

        improvement_runtime.ImprovementConfig = ContextualImprovementConfig

    original_execute = improvement_runtime.execute_improvement_intelligence
    if not bool(getattr(original_execute, "_rasai_contextual_optional_reuse", False)):
        def contextual_improvement_execute(*args: Any, **kwargs: Any):
            audit_id = str(kwargs.get("audit_id") or "")
            workspace = kwargs.get("workspace")
            active_context = current()
            if (
                active_context is not None
                and active_context.audit_id == audit_id
                and workspace is not None
                and not should_execute("IMPROVEMENT_INTELLIGENCE")
            ):
                item = _item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
                if item is not None and str(item.status) == SUCCESS:
                    persisted = _persisted_improvement_result(workspace, audit_id)
                    if persisted is not None:
                        return persisted
            return original_execute(*args, **kwargs)

        contextual_improvement_execute._rasai_contextual_optional_reuse = True
        contextual_improvement_execute._rasai_original = original_execute
        improvement_runtime.execute_improvement_intelligence = contextual_improvement_execute

    original_gsc = gsc_runtime.collect_configured_search_console
    if not bool(getattr(original_gsc, "_rasai_contextual_optional_reuse", False)):
        def contextual_gsc_collect(*, audit_id: str, workspace: Any, env: Mapping[str, str] | None = None):
            active_context = current()
            if active_context is not None and active_context.audit_id == audit_id:
                item = _item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
                if item is not None and (
                    (not should_execute("GOOGLE_SEARCH_CONSOLE") and str(item.status) == SUCCESS)
                    or _expired(item)
                ):
                    persisted = _persisted_gsc_result(workspace, audit_id)
                    if persisted is not None:
                        return persisted
                    return {
                        "service_state": "NO_PERSISTED_RESULT",
                        "requested": True,
                        "configured": False,
                        "effective_enabled": False,
                        "operations": [],
                        "errors": [],
                        "collection_state": "NO_DATA",
                        "targets_attempted": 0,
                        "targets_succeeded": 0,
                    }
                return original_gsc(
                    audit_id=audit_id,
                    workspace=workspace,
                    env=resolve_environment(env),
                )
            return original_gsc(audit_id=audit_id, workspace=workspace, env=env)

        contextual_gsc_collect._rasai_contextual_optional_reuse = True
        contextual_gsc_collect._rasai_original = original_gsc
        gsc_runtime.collect_configured_search_console = contextual_gsc_collect


def _current_reprocess_id(workspace: Any, audit_id: str) -> str | None:
    try:
        from rasai import reprocess_runtime_safety
        value = reprocess_runtime_safety._RPR_CONTEXT.get()
        if value is not None and value.audit_id == audit_id and value.reprocess_id:
            return str(value.reprocess_id)
    except Exception:
        pass
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT reprocess_id FROM audit_reprocess_runs WHERE audit_id=? AND completed_at IS NULL ORDER BY started_at DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    return str(row[0]) if row and row[0] else None


def _record_optional_attempts(workspace: Any, audit_id: str, components: set[str]) -> None:
    reprocess_id = _current_reprocess_id(workspace, audit_id)
    if not reprocess_id:
        return
    from rasai.reprocess_runtime_safety import record_reprocess_evaluation

    for component in sorted(components):
        item = _item(workspace, audit_id, component)
        if item is None:
            continue
        record_reprocess_evaluation(
            workspace,
            item=item,
            reprocess_id=reprocess_id,
            metadata={"component": component, "kind": "OPTIONAL_COMPONENT_REPROCESS_EVALUATION"},
        )
        record_optional_evaluation(success=str(item.status) == SUCCESS)


def _install_report_finalizer() -> None:
    from rasai import report_completion

    original = report_completion.finalize_audit_report_site
    if bool(getattr(original, "_rasai_selective_optional_reprocess", False)):
        return

    def finalize_selective_optional(*args: Any, **kwargs: Any):
        active_context = current()
        audit_id = str(kwargs.get("audit_id") or (args[0] if args else ""))
        workspace = kwargs.get("workspace")
        if active_context is None or not audit_id or workspace is None or active_context.audit_id != audit_id:
            return original(*args, **kwargs)

        evaluated: set[str] = set()
        search = _item(workspace, audit_id, "SEARCH_INTELLIGENCE")
        if (
            search is not None
            and should_execute("SEARCH_INTELLIGENCE")
            and str(search.status) != SUCCESS
            and not _expired(search)
        ):
            evaluated.add("SEARCH_INTELLIGENCE")
            try:
                _recover_search(workspace, audit_id, search)
            except Exception as exc:
                set_work_item_status(
                    workspace,
                    audit_id=audit_id,
                    component="SEARCH_INTELLIGENCE",
                    status=FAILED_RETRYABLE,
                    error_class="SEARCH_PROVIDER",
                    error_code="SEARCH_INTELLIGENCE_RUNTIME_ERROR",
                    error_message=redact_text(f"{type(exc).__name__}: {exc}")[:1000],
                    retryable=True,
                )

        for component in ("GOOGLE_SEARCH_CONSOLE", "IMPROVEMENT_INTELLIGENCE"):
            item = _item(workspace, audit_id, component)
            if item is None or not should_execute(component) or str(item.status) == SUCCESS:
                continue
            if component == "GOOGLE_SEARCH_CONSOLE" and _expired(item):
                continue
            evaluated.add(component)

        with _original_optional_environment(workspace, audit_id):
            try:
                return original(*args, **kwargs)
            finally:
                _record_optional_attempts(workspace, audit_id, evaluated)

    finalize_selective_optional._rasai_selective_optional_reprocess = True
    finalize_selective_optional._rasai_original = original
    report_completion.finalize_audit_report_site = finalize_selective_optional


def _update_reprocess_counts(workspace: Any, reprocess_id: str | None, attempted: int, successful: int) -> None:
    if not reprocess_id or (attempted == 0 and successful == 0):
        return
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """UPDATE audit_reprocess_runs
                   SET attempted_items=attempted_items+?,successful_items=successful_items+?
                   WHERE reprocess_id=?""",
                (int(attempted), int(successful), reprocess_id),
            )
    finally:
        connection.close()


def _install_reprocess_wrapper() -> None:
    from rasai import audit_reprocess

    original = audit_reprocess.reprocess_audit
    if bool(getattr(original, "_rasai_selective_optional_reprocess", False)):
        return

    def reprocess_with_optional_components(
        audit_id: str,
        *,
        audits_root: str | Path = "audits",
        source: str = "CLI",
    ):
        workspace = AuditWorkspace.open(Path(audits_root) / audit_id)
        audit_reprocess._backfill_contract(workspace, audit_id)
        _backfill_console_search(workspace, audit_id)
        _validate_success_integrity(workspace, audit_id)
        pending = {
            str(item.component)
            for item in list_work_items(workspace, audit_id, pending_only=True)
            if bool(item.required)
        }
        with scope(audit_id, pending, workspace=workspace) as state:
            result = original(audit_id, audits_root=audits_root, source=source)
            extra_attempted = int(state.extra_attempted)
            extra_successful = int(state.extra_successful)
        if extra_attempted or extra_successful:
            _update_reprocess_counts(
                workspace,
                getattr(result, "reprocess_id", None),
                extra_attempted,
                extra_successful,
            )
            result = replace(
                result,
                attempted_items=int(result.attempted_items) + extra_attempted,
                successful_items=int(result.successful_items) + extra_successful,
            )
        return result

    reprocess_with_optional_components._rasai_selective_optional_reprocess = True
    reprocess_with_optional_components._rasai_original = original
    audit_reprocess.reprocess_audit = reprocess_with_optional_components


def install() -> None:
    """Install after Improvement/GSC runtimes so the finalizer wrapper is outermost."""
    global _INSTALLED
    if _INSTALLED:
        return
    _augment_reconciliation_configuration()
    _install_contextual_optional_hooks()
    _install_reprocess_wrapper()
    _install_report_finalizer()
    _INSTALLED = True
