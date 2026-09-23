"""Measured interactive-console progress for Google Search Console finalization.

The GSC collector already runs as a bounded finalization step. This adapter adds
secret-safe operational milestones around its existing Sitemaps, URL Inspection and
Search Analytics calls, then projects those milestones into the console. It does not
add provider calls, target navigation or polling.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace


_INSTALLED = False
_ACTIVE: dict[str, dict[str, int]] = {}


def _workspace_from_root(value: Any) -> AuditWorkspace | None:
    if value is None:
        return None
    try:
        return AuditWorkspace(Path(value))
    except (TypeError, ValueError, OSError):
        return None


def _key(value: Any) -> str:
    try:
        return str(Path(value).resolve())
    except (TypeError, ValueError, OSError):
        return str(value)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_runtime
    from rasai import standards_gsc_observability_runtime as gsc

    if bool(getattr(gsc.collect_configured_search_console, "_rasai_console_progress", False)):
        _INSTALLED = True
        return

    original_collect = gsc.collect_configured_search_console
    original_sitemaps = gsc.collect_sitemaps
    original_inspection = gsc.collect_url_inspection
    original_analytics = gsc.collect_search_analytics

    def _emit(root: Any, event: str, **details: Any) -> None:
        workspace = _workspace_from_root(root)
        if workspace is not None:
            try_append_operational_event(workspace, event, **details)

    def _operation_started(root: Any, operation: str) -> tuple[int, int]:
        active = _ACTIVE.get(_key(root), {"index": 0, "total": 1})
        active["index"] = min(active.get("index", 0) + 1, max(active.get("total", 1), 1))
        _ACTIVE[_key(root)] = active
        index, total = active["index"], max(active.get("total", 1), 1)
        _emit(root, "GSC_OPERATION_STARTED", operation=operation, operation_index=index, operation_total=total)
        return index, total

    def _operation_finished(root: Any, operation: str, index: int, total: int, status: str) -> None:
        _emit(
            root,
            "GSC_OPERATION_FINISHED",
            operation=operation,
            operation_index=index,
            operation_total=total,
            status=status,
        )

    def collect_sitemaps(*args: Any, **kwargs: Any):
        root = kwargs.get("audit_workspace")
        index, total = _operation_started(root, "SITEMAPS")
        try:
            result = original_sitemaps(*args, **kwargs)
        except Exception:
            _operation_finished(root, "SITEMAPS", index, total, "ERROR")
            raise
        _operation_finished(root, "SITEMAPS", index, total, "SUCCESS")
        return result

    def collect_url_inspection(*args: Any, **kwargs: Any):
        root = kwargs.get("audit_workspace")
        index, total = _operation_started(root, "URL_INSPECTION")
        try:
            result = original_inspection(*args, **kwargs)
        except Exception:
            _operation_finished(root, "URL_INSPECTION", index, total, "ERROR")
            raise
        _operation_finished(root, "URL_INSPECTION", index, total, "SUCCESS")
        return result

    def collect_search_analytics(*args: Any, **kwargs: Any):
        root = kwargs.get("audit_workspace")
        index, total = _operation_started(root, "SEARCH_ANALYTICS")
        try:
            result = original_analytics(*args, **kwargs)
        except Exception:
            _operation_finished(root, "SEARCH_ANALYTICS", index, total, "ERROR")
            raise
        _operation_finished(root, "SEARCH_ANALYTICS", index, total, "SUCCESS")
        return result

    def collect_configured_search_console(*, audit_id: str, workspace: Any, env: Mapping[str, str] | None = None):
        environment = env if env is not None else gsc.os.environ
        state_info = gsc.service_state(gsc.service("google-search-console"), environment)
        if not bool(state_info["effective_enabled"]):
            return original_collect(audit_id=audit_id, workspace=workspace, env=env)

        max_urls = gsc._int_env(environment, gsc.STANDARDS_MAX_URLS_ENV, gsc.DEFAULT_STANDARDS_MAX_URLS)
        urls = gsc._bounded_urls(workspace, audit_id, max_urls)
        days = gsc.search_analytics_days(environment.get(gsc.GSC_SEARCH_ANALYTICS_DAYS_ENV))
        total = 1 + (1 if urls else 0) + (1 if days > 0 else 0)
        root = workspace.root
        _ACTIVE[_key(root)] = {"index": 0, "total": total}
        _emit(
            root,
            "GSC_COLLECTION_STARTED",
            audit_id=audit_id,
            operation_total=total,
            requested_url_inspections=len(urls),
            search_analytics_enabled=days > 0,
        )
        try:
            result = original_collect(audit_id=audit_id, workspace=workspace, env=env)
        finally:
            _ACTIVE.pop(_key(root), None)
        _emit(
            root,
            "GSC_COLLECTION_FINISHED",
            audit_id=audit_id,
            collection_state=str(result.get("collection_state") or result.get("service_state") or "UNKNOWN"),
            targets_attempted=int(result.get("targets_attempted") or 0),
            targets_succeeded=int(result.get("targets_succeeded") or 0),
        )
        return result

    collect_configured_search_console._rasai_console_progress = True  # type: ignore[attr-defined]
    gsc.collect_sitemaps = collect_sitemaps
    gsc.collect_url_inspection = collect_url_inspection
    gsc.collect_search_analytics = collect_search_analytics
    gsc.collect_configured_search_console = collect_configured_search_console

    original_observe = console_runtime.observe_workspace

    def observe_workspace(workspace: Any, state: Any) -> None:
        original_observe(workspace, state)
        event = console_runtime._last_log_event(workspace)
        if not isinstance(event, dict):
            return
        name = str(event.get("event") or "")
        if name not in {"GSC_COLLECTION_STARTED", "GSC_OPERATION_STARTED", "GSC_OPERATION_FINISHED", "GSC_COLLECTION_FINISHED"}:
            return
        state.status = "FINALIZING"
        state.operation = "API:GOOGLE_SEARCH_CONSOLE"
        progress_type = getattr(console_runtime, "_RunProgress", None)
        progress_store = getattr(console_runtime, "_RUN_PROGRESS", None)
        if progress_type is None or not isinstance(progress_store, dict):
            return

        if name == "GSC_COLLECTION_STARTED":
            total = max(int(event.get("operation_total") or 1), 1)
            stage = 0.0
            detail = f"Search Console iniciado; {total} suboperação(ões) planejada(s)"
        elif name in {"GSC_OPERATION_STARTED", "GSC_OPERATION_FINISHED"}:
            index = max(int(event.get("operation_index") or 1), 1)
            total = max(int(event.get("operation_total") or 1), 1)
            completed = index if name.endswith("FINISHED") else index - 1
            stage = min(max((completed / total) * 100.0, 0.0), 100.0)
            operation = str(event.get("operation") or "GSC")
            status = str(event.get("status") or "em execução")
            detail = f"Search Console {operation} · {index}/{total} · {status}"
        else:
            stage = 100.0
            detail = f"Search Console concluído: {event.get('collection_state') or 'UNKNOWN'}; consolidando relatórios"

        overall = 97.0 + (2.0 * stage / 100.0)
        progress_store[id(state)] = progress_type(
            label="Search Console e finalização",
            percent=stage,
            detail=detail,
            exact=True,
            stage_percent=stage,
            stage_exact=True,
            overall_percent=min(overall, 99.0),
            overall_exact=False,
        )

    observe_workspace._rasai_gsc_console_progress = True  # type: ignore[attr-defined]
    console_runtime.observe_workspace = observe_workspace
    _INSTALLED = True
