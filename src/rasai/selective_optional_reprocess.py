"""Selective recovery for optional AUD components owned outside the core RPR loops.

Search Intelligence is a console-AUD observation and is replayed directly from its
persisted non-secret execution contract. Google Search Console and Improvement
Intelligence remain owned by their existing report-finalization runtimes; during an
RPR this adapter supplies the original non-secret configuration, reuses successful
persisted results, and lets those owners execute only when their work item is pending.

No pricing code lives here. AI/provider attempts and their observed costs remain owned
by the existing provider persistence/pricing path.
"""
from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any, Iterator, Mapping
from urllib.parse import urlsplit

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    NOT_APPLICABLE,
    REPLAY_SAFE,
    SUCCESS,
    list_work_items,
    register_work_item,
    set_work_item_status,
)
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


def _augment_reconciliation_configuration() -> None:
    """Persist complete non-secret optional-service configuration into each work item."""
    from rasai import fulfillment_execution_contract as contract

    improvement = contract._reconcile_requested_improvement
    if not bool(getattr(improvement, "_rasai_optional_config", False)):
        def reconcile_improvement(workspace: Any, audit_id: str) -> None:
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

            environment = os.environ
            values: dict[str, Any] = {
                "requested": True,
                "provider": str(environment.get(PROVIDER_ENV) or item.configuration.get("provider") or ""),
                "model": str(environment.get(MODEL_ENV) or item.configuration.get("model") or ""),
                "reasoning": str(environment.get(REASONING_ENV) or item.configuration.get("reasoning") or ""),
                "domains": [value.strip().upper() for value in str(environment.get(DOMAINS_ENV) or "").replace(";", ",").split(",") if value.strip()] or list(DEFAULT_DOMAINS),
                "max_recommendations": str(environment.get(MAX_RECOMMENDATIONS_ENV) or "30"),
                "timeout_seconds": str(environment.get(TIMEOUT_ENV) or "240"),
                "language": str(environment.get(AI_ANALYSIS_LANGUAGE_ENV) or "auto"),
            }
            try:
                cfg = ImprovementConfig.from_environment()
            except Exception:
                pass
            else:
                values.update({
                    "provider": cfg.provider,
                    "model": cfg.model,
                    "reasoning": cfg.reasoning,
                    "domains": list(cfg.domains),
                    "max_recommendations": cfg.max_recommendations,
                    "timeout_seconds": cfg.timeout_seconds,
                    "language": cfg.language,
                })
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
    connection = sqlite3.connect(workspace.database)
    try:
        gsc_row = None
        if _table_exists(connection, "standards_service_runs"):
            gsc_row = connection.execute(
                "SELECT details_json FROM standards_service_runs WHERE audit_id=? AND service_id='google-search-console'",
                (audit_id,),
            ).fetchone()
        improvement_row = None
        if _table_exists(connection, "improvement_intelligence_runs"):
            improvement_row = connection.execute(
                "SELECT status FROM improvement_intelligence_runs WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
        search_count = None
        if _table_exists(connection, "serp_observations"):
            search_count = int(connection.execute(
                "SELECT COUNT(*) FROM serp_observations WHERE audit_id=?",
                (audit_id,),
            ).fetchone()[0])
    finally:
        connection.close()

    checks = (
        ("GOOGLE_SEARCH_CONSOLE", bool(gsc_row and gsc_row[0])),
        ("IMPROVEMENT_INTELLIGENCE", bool(improvement_row and str(improvement_row[0]).upper() == "COMPLETE")),
        ("SEARCH_INTELLIGENCE", search_count is None or search_count > 0),
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


@contextmanager
def _temporary_environment(values: Mapping[str, Any]) -> Iterator[None]:
    previous: dict[str, str | None] = {}
    for name, value in values.items():
        text = str(value or "").strip()
        if not name or not text:
            continue
        previous[name] = os.environ.get(name)
        os.environ[name] = text
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _search_environment(item: Any) -> dict[str, Any]:
    config = dict(getattr(item, "configuration", {}) or {})
    mapping = {
        "mode": "RASAI_SERP_MODE",
        "provider": "RASAI_SERP_PROVIDER",
        "max_queries": "RASAI_SERP_MAX_QUERIES",
        "max_requests": "RASAI_SERP_MAX_REQUESTS",
        "max_depth": "RASAI_SERP_MAX_DEPTH",
        "max_competitors": "RASAI_SERP_MAX_COMPETITORS",
        "timeout_seconds": "RASAI_SERP_TIMEOUT_SECONDS",
        "retries": "RASAI_SERP_RETRIES",
        "min_interval_seconds": "RASAI_SERP_MIN_INTERVAL_SECONDS",
    }
    return {env_name: config.get(key) for key, env_name in mapping.items() if config.get(key) not in (None, "")}


def _recover_search(workspace: Any, audit_id: str, item: Any) -> bool:
    config = dict(getattr(item, "configuration", {}) or {})
    queries = tuple(str(value).strip() for value in config.get("queries", ()) if str(value).strip())
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

    from rasai.console_search_intelligence import _configured_search, _engine_for_provider
    from rasai.search_intelligence.cli import main as search_main

    state = SimpleNamespace(
        search_queries=queries,
        search_depth=int(config.get("depth") or 20),
        search_device=str(config.get("device") or "mobile"),
    )
    environment = dict(os.environ)
    environment.update({name: str(value) for name, value in _search_environment(item).items()})
    try:
        runtime = _configured_search(state, environment)
        domain = _audit_domain(workspace, audit_id)
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

    argv = [
        *queries,
        "--domain", domain,
        "--engine", str(config.get("engine") or _engine_for_provider(runtime.provider)),
        "--country", str(config.get("market") or "BR"),
        "--language", str(config.get("language") or "pt-BR"),
        "--device", str(config.get("device") or "mobile"),
        "--depth", str(int(config.get("depth") or 20)),
        "--audit-workspace", str(workspace.root),
        "--mode", runtime.mode,
        "--provider", runtime.provider,
    ]
    region = str(config.get("region") or "").strip()
    if region:
        argv.extend(["--region", region])
    if bool(config.get("competitive", True)):
        argv.append("--competitive")

    output = io.StringIO()
    code = 2
    try:
        with _temporary_environment(_search_environment(item)):
            with redirect_stdout(output), redirect_stderr(output):
                try:
                    code = int(search_main(argv) or 0)
                except SystemExit as exc:
                    code = int(exc.code) if isinstance(exc.code, int) else 2
    except Exception as exc:
        output.write(f"{type(exc).__name__}: {redact_text(str(exc))}")
        code = 2

    detail_lines = [line.strip() for line in output.getvalue().splitlines() if line.strip()]
    detail = redact_text(detail_lines[-1] if detail_lines else f"Search Intelligence retornou código {code}")[:1000]
    if code == 0:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEARCH_INTELLIGENCE",
            status=SUCCESS,
            result_ref="search-intelligence:effective",
            retryable=False,
        )
        return True
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="SEARCH_INTELLIGENCE",
        status=FAILED_RETRYABLE,
        error_class="SEARCH_PROVIDER",
        error_code="SEARCH_INTELLIGENCE_RETRY_INCOMPLETE",
        error_message=detail,
        retryable=True,
    )
    return False


def _persisted_gsc_result(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "standards_service_runs"):
            return None
        row = connection.execute(
            "SELECT * FROM standards_service_runs WHERE audit_id=? AND service_id='google-search-console'",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    try:
        details = json.loads(str(row["details_json"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        details = {}
    result = dict(details) if isinstance(details, dict) else {}
    result.update({
        "service_state": str(row["state"] or result.get("service_state") or "SUCCESS"),
        "collection_state": str(row["state"] or result.get("collection_state") or "SUCCESS"),
        "targets_attempted": int(row["targets_attempted"] or result.get("targets_attempted") or 0),
        "targets_succeeded": int(row["targets_succeeded"] or result.get("targets_succeeded") or 0),
        "requested": True,
        "configured": True,
        "effective_enabled": True,
    })
    result.setdefault("operations", [])
    result.setdefault("errors", [])
    return result


def _persisted_improvement_result(workspace: Any, audit_id: str) -> Any | None:
    from rasai.improvement_intelligence import ImprovementResult

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if not _table_exists(connection, "improvement_intelligence_runs"):
            return None
        row = connection.execute(
            "SELECT * FROM improvement_intelligence_runs WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return ImprovementResult(
        status=str(row["status"] or "COMPLETE"),
        target_url=str(row["target_url"]) if row["target_url"] else None,
        findings_count=int(row["findings_count"] or 0),
        recommendations_count=int(row["recommendations_count"] or 0),
        provider=str(row["provider"]) if row["provider"] else None,
        model=str(row["model"]) if row["model"] else None,
        reasoning=str(row["reasoning"]) if row["reasoning"] else None,
        reason=str(row["reason"]) if row["reason"] else None,
        reused=True,
    )


@contextmanager
def _original_optional_environment(workspace: Any, audit_id: str) -> Iterator[None]:
    """Restore original non-secret settings; missing prerequisites may use current values."""
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

    with _temporary_environment(overrides):
        yield


@contextmanager
def _reuse_successful_optional_calls(workspace: Any, audit_id: str) -> Iterator[None]:
    """Prevent external re-execution of optional work items already satisfied."""
    from rasai import improvement_intelligence_runtime as improvement_runtime
    from rasai import standards_gsc_observability_runtime as gsc_runtime

    original_improvement = improvement_runtime.execute_improvement_intelligence
    original_gsc = gsc_runtime.collect_configured_search_console
    patched_improvement = False
    patched_gsc = False

    improvement = _item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
    if improvement is not None and not should_execute("IMPROVEMENT_INTELLIGENCE") and str(improvement.status) == SUCCESS:
        reused = _persisted_improvement_result(workspace, audit_id)
        if reused is not None:
            def reuse_improvement(*args: Any, **kwargs: Any):
                return reused
            improvement_runtime.execute_improvement_intelligence = reuse_improvement
            patched_improvement = True

    gsc = _item(workspace, audit_id, "GOOGLE_SEARCH_CONSOLE")
    reuse_gsc = gsc is not None and (
        (not should_execute("GOOGLE_SEARCH_CONSOLE") and str(gsc.status) == SUCCESS)
        or _expired(gsc)
    )
    if reuse_gsc:
        persisted = _persisted_gsc_result(workspace, audit_id)
        if persisted is not None:
            def reuse_search_console(*args: Any, **kwargs: Any):
                return dict(persisted)
            gsc_runtime.collect_configured_search_console = reuse_search_console
            patched_gsc = True

    try:
        yield
    finally:
        if patched_improvement:
            improvement_runtime.execute_improvement_intelligence = original_improvement
        if patched_gsc:
            gsc_runtime.collect_configured_search_console = original_gsc


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
            _recover_search(workspace, audit_id, search)
            evaluated.add("SEARCH_INTELLIGENCE")

        for component in ("GOOGLE_SEARCH_CONSOLE", "IMPROVEMENT_INTELLIGENCE"):
            item = _item(workspace, audit_id, component)
            if item is None or not should_execute(component) or str(item.status) == SUCCESS:
                continue
            if component == "GOOGLE_SEARCH_CONSOLE" and _expired(item):
                continue
            evaluated.add(component)

        with _original_optional_environment(workspace, audit_id):
            with _reuse_successful_optional_calls(workspace, audit_id):
                result = original(*args, **kwargs)

        _record_optional_attempts(workspace, audit_id, evaluated)
        return result

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
        # Index the current contract first. This is idempotent and also lets an AUD
        # created before the Search fulfillment adapter recover from its saved console
        # configuration rather than silently shrinking the denominator.
        audit_reprocess._backfill_contract(workspace, audit_id)
        _backfill_console_search(workspace, audit_id)
        _validate_success_integrity(workspace, audit_id)
        pending = {
            str(item.component)
            for item in list_work_items(workspace, audit_id, pending_only=True)
            if bool(item.required)
        }
        with scope(audit_id, pending) as state:
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
    _install_reprocess_wrapper()
    _install_report_finalizer()
    _INSTALLED = True
