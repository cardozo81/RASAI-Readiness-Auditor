"""Process-local handoff and finalization hooks for M25.

The handoff is intentionally one-shot. It avoids changing the persisted/public
M23 configuration contract while M25 remains an additive domain executed
immediately before M23's standard navigation samples.

M25's first report projection happens after its own collection. A lightweight
report hook refreshes that page after M23 reporting so the optional Standard M23
comparison is populated from final persisted data without changing either score.
"""
from __future__ import annotations

import sqlite3
from threading import Lock
from typing import Any

from searchgeo.m25_apdex_experience import ExperienceApdexConfig, M25ExecutionResult, execute_m25_experience
from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditWorkspace

_lock = Lock()
_pending = ExperienceApdexConfig(enabled=False)


def set_pending_config(config: ExperienceApdexConfig) -> None:
    global _pending
    with _lock:
        _pending = config.validate() if config.enabled else ExperienceApdexConfig(enabled=False)


def peek_pending_config() -> ExperienceApdexConfig:
    with _lock:
        return _pending


def consume_pending_config() -> ExperienceApdexConfig:
    global _pending
    with _lock:
        value = _pending
        _pending = ExperienceApdexConfig(enabled=False)
        return value


def execute_pending_m25(*, audit_id: str, workspace: AuditWorkspace) -> M25ExecutionResult | None:
    config = consume_pending_config()
    if not config.enabled:
        return None
    try:
        return execute_m25_experience(audit_id=audit_id, workspace=workspace, config=config)
    except Exception as exc:
        try_append_operational_event(
            workspace,
            "M25_UX_RUNTIME_FAILURE",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
            scoring_impact="NONE",
        )
        return M25ExecutionResult(
            enabled=True,
            status="UNAVAILABLE",
            pages_considered=0,
            attempted_samples=0,
            valid_samples=0,
            invalid_samples=0,
            final_population_groups=0,
            report_path=None,
        )


def refresh_m25_report_after_m23(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Refresh M25 only when that audit actually persisted an M25 run."""
    if not _has_m25_run(audit_id=audit_id, workspace=workspace):
        return
    try:
        from searchgeo.m25_reporting import enrich_m25_report_site

        path = enrich_m25_report_site(audit_id=audit_id, workspace=workspace)
        try_append_operational_event(
            workspace,
            "M25_UX_REPORT_FINALIZED_AFTER_M23",
            audit_id=audit_id,
            report_path=str(path.relative_to(workspace.root)),
            scoring_impact="NONE",
        )
    except Exception as exc:
        try_append_operational_event(
            workspace,
            "M25_UX_REPORT_FINALIZATION_FAILURE",
            level="WARNING",
            audit_id=audit_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:512],
            scoring_impact="NONE",
        )


def _has_m25_run(*, audit_id: str, workspace: AuditWorkspace) -> bool:
    connection = sqlite3.connect(workspace.database)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='synthetic_ux_apdex_runs'"
        ).fetchone()
        if table is None:
            return False
        return connection.execute(
            "SELECT 1 FROM synthetic_ux_apdex_runs WHERE audit_id=? LIMIT 1",
            (audit_id,),
        ).fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def _install_m23_report_finalizer() -> None:
    """Wrap M23 reporting before cli_extensions binds its imported callable.

    cli_extensions imports m23_cli (and therefore this module) before importing
    enrich_m23_report_site. Installing the wrapper here keeps the change additive
    and avoids modifying M23's implementation or formula.
    """
    try:
        from searchgeo import m23_reporting
    except Exception:
        return

    original = m23_reporting.enrich_m23_report_site
    if bool(getattr(original, "_searchgeo_m25_finalizer", False)):
        return

    def wrapped(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        audit_id = kwargs.get("audit_id")
        workspace = kwargs.get("workspace")
        if isinstance(audit_id, str) and isinstance(workspace, AuditWorkspace):
            refresh_m25_report_after_m23(audit_id=audit_id, workspace=workspace)
        return result

    setattr(wrapped, "_searchgeo_m25_finalizer", True)
    m23_reporting.enrich_m23_report_site = wrapped


_install_m23_report_finalizer()
