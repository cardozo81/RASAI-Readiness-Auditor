"""Progress milestones and evidence gate for pre-seal external observability.

The wrapper adds no requests. It only verifies that core browser evidence already
exists before CrUX History, Clarity or Common Crawl are allowed to execute, then
records secret-safe start/finish milestones for the interactive console. External
observability is a collector phase and must not depend on the audit already being
COMPLETED.
"""
from __future__ import annotations

from functools import wraps
from pathlib import Path
import sqlite3
import time
from typing import Any, Mapping

from rasai.operational_log import try_append_operational_event

_INSTALLED = False
_ACTIVE: dict[str, dict[str, Any]] = {}


def _key(value: Any) -> str:
    try:
        root = getattr(value, "root", value)
        return str(Path(root).resolve())
    except (OSError, TypeError, ValueError):
        return str(value)


def _evidence_ready(*, workspace: Any, audit_id: str) -> tuple[bool, str]:
    try:
        connection = sqlite3.connect(workspace.database, timeout=0.5)
        try:
            audit = connection.execute(
                "SELECT 1 FROM audits WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
            if audit is None:
                return False, "AUDIT_NOT_FOUND"
            page_count = int(
                connection.execute("SELECT COUNT(*) FROM pages WHERE audit_id=?", (audit_id,)).fetchone()[0]
            )
            snapshot_count = int(
                connection.execute(
                    """SELECT COUNT(*) FROM page_snapshots ps
                       JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=?""",
                    (audit_id,),
                ).fetchone()[0]
            )
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return False, f"SQLITE_{type(exc).__name__.upper()}"
    if page_count <= 0:
        return False, "NO_PERSISTED_PAGE"
    if snapshot_count <= 0:
        return False, "NO_PERSISTED_BROWSER_SNAPSHOT"
    return True, "READY"


def _planned_operations(runtime: Any, *, audit_id: str, workspace: Any, env: Mapping[str, str]) -> int:
    total = 0
    crux_state = runtime.service_state(runtime.service("crux-history"), env)
    if bool(crux_state["effective_enabled"]):
        total += len(runtime._origin_form_factors(workspace, audit_id))
    clarity_state = runtime.service_state(runtime.service("microsoft-clarity"), env)
    if bool(clarity_state["effective_enabled"]):
        total += 1
    # Common Crawl is already owned by the bounded SARI corroboration path and is
    # deliberately suppressed from this second collector surface.
    return total


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import external_observability_runtime as runtime

    if getattr(runtime, "_rasai_external_observability_progress", False):
        _INSTALLED = True
        return

    original_collect = runtime.collect_configured_external_observability
    original_crux = runtime.collect_crux_history
    original_clarity = runtime.collect_clarity_insights
    original_common = runtime.collect_common_crawl_history

    def _begin(root: Any, service: str, scope: str) -> tuple[dict[str, Any] | None, int, int]:
        active = _ACTIVE.get(_key(root))
        if active is None:
            return None, 1, 1
        active["index"] = min(int(active.get("index", 0)) + 1, max(int(active.get("total", 1)), 1))
        index = int(active["index"])
        total = max(int(active.get("total", 1)), 1)
        workspace = active["workspace"]
        try_append_operational_event(
            workspace,
            "EXTERNAL_OBSERVABILITY_OPERATION_STARTED",
            audit_id=str(active.get("audit_id") or ""),
            service=service,
            scope=scope,
            operation_index=index,
            operation_total=total,
            timeout_seconds=float(active.get("timeout", 0.0)),
            policy="PRE_SEAL_CORE_EVIDENCE",
        )
        return active, index, total

    def _finish(active: dict[str, Any] | None, service: str, index: int, total: int, status: str, duration_ms: int) -> None:
        if active is None:
            return
        try_append_operational_event(
            active["workspace"],
            "EXTERNAL_OBSERVABILITY_OPERATION_FINISHED",
            audit_id=str(active.get("audit_id") or ""),
            service=service,
            operation_index=index,
            operation_total=total,
            status=status,
            duration_ms=duration_ms,
        )

    @wraps(original_crux)
    def crux(*args: Any, **kwargs: Any) -> Any:
        root = kwargs.get("audit_workspace")
        active, index, total = _begin(root, "CRUX_HISTORY", "ORIGIN+FORM_FACTOR")
        started = time.monotonic()
        try:
            result = original_crux(*args, **kwargs)
        except Exception:
            _finish(active, "CRUX_HISTORY", index, total, "ERROR", int((time.monotonic() - started) * 1000))
            raise
        _finish(active, "CRUX_HISTORY", index, total, "SUCCESS", int((time.monotonic() - started) * 1000))
        return result

    @wraps(original_clarity)
    def clarity(*args: Any, **kwargs: Any) -> Any:
        root = kwargs.get("audit_workspace")
        active, index, total = _begin(root, "MICROSOFT_CLARITY", "URL/ORIGIN+DEVICE")
        started = time.monotonic()
        try:
            result = original_clarity(*args, **kwargs)
        except Exception:
            _finish(active, "MICROSOFT_CLARITY", index, total, "ERROR", int((time.monotonic() - started) * 1000))
            raise
        _finish(active, "MICROSOFT_CLARITY", index, total, "SUCCESS", int((time.monotonic() - started) * 1000))
        return result

    @wraps(original_common)
    def common(*args: Any, **kwargs: Any) -> Any:
        root = kwargs.get("audit_workspace")
        active, index, total = _begin(root, "COMMON_CRAWL", "URL")
        started = time.monotonic()
        try:
            result = original_common(*args, **kwargs)
        except Exception:
            _finish(active, "COMMON_CRAWL", index, total, "ERROR", int((time.monotonic() - started) * 1000))
            raise
        _finish(active, "COMMON_CRAWL", index, total, "SUCCESS", int((time.monotonic() - started) * 1000))
        return result

    @wraps(original_collect)
    def collect_configured_external_observability(
        *,
        audit_id: str,
        workspace: Any,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        environment = env if env is not None else runtime.os.environ
        ready, reason = _evidence_ready(workspace=workspace, audit_id=audit_id)
        if not ready:
            try_append_operational_event(
                workspace,
                "EXTERNAL_OBSERVABILITY_EVIDENCE_GATE_BLOCKED",
                level="WARNING",
                audit_id=audit_id,
                reason=reason,
                policy="NO_EXTERNAL_OBSERVABILITY_BEFORE_CORE_EVIDENCE",
            )
            return {
                service_id: {
                    "service_state": "BLOCKED",
                    "requested": False,
                    "configured": False,
                    "effective_enabled": False,
                    "configuration_source": "EVIDENCE_GATE",
                    "missing_configuration": [],
                    "targets_attempted": 0,
                    "targets_succeeded": 0,
                    "datasets": [],
                    "errors": [],
                    "collection_state": "NO_DATA",
                    "reason": reason,
                }
                for service_id in runtime._SERVICE_IDS
            }

        timeout = runtime._positive_float(
            environment.get(runtime.STANDARDS_TIMEOUT_ENV),
            runtime.DEFAULT_STANDARDS_TIMEOUT_SECONDS,
        )
        total = _planned_operations(runtime, audit_id=audit_id, workspace=workspace, env=environment)
        root_key = _key(workspace.root)
        _ACTIVE[root_key] = {
            "workspace": workspace,
            "audit_id": audit_id,
            "index": 0,
            "total": max(total, 1),
            "timeout": timeout,
        }
        try_append_operational_event(
            workspace,
            "EXTERNAL_OBSERVABILITY_COLLECTION_STARTED",
            audit_id=audit_id,
            operation_total=total,
            policy="PRE_SEAL_CORE_EVIDENCE",
            core_evidence_state="READY",
        )
        try:
            result = original_collect(audit_id=audit_id, workspace=workspace, env=environment)
        except Exception:
            active = _ACTIVE.pop(root_key, None)
            try_append_operational_event(
                workspace,
                "EXTERNAL_OBSERVABILITY_COLLECTION_FINISHED",
                level="WARNING",
                audit_id=audit_id,
                operation_total=total,
                operation_completed=int((active or {}).get("index", 0)),
                collection_state="ERROR",
            )
            raise
        active = _ACTIVE.pop(root_key, None)
        states = [str(item.get("collection_state") or "") for item in result.values()]
        if any(state == "ERROR" for state in states):
            collection_state = "PARTIAL"
        elif any(state == "PARTIAL" for state in states):
            collection_state = "PARTIAL"
        elif total <= 0:
            collection_state = "NO_DATA"
        else:
            collection_state = "SUCCESS"
        try_append_operational_event(
            workspace,
            "EXTERNAL_OBSERVABILITY_COLLECTION_FINISHED",
            audit_id=audit_id,
            operation_total=total,
            operation_completed=int((active or {}).get("index", 0)),
            collection_state=collection_state,
        )
        return result

    runtime.collect_crux_history = crux
    runtime.collect_clarity_insights = clarity
    runtime.collect_common_crawl_history = common
    runtime.collect_configured_external_observability = collect_configured_external_observability
    runtime._rasai_external_observability_progress = True
    _INSTALLED = True
