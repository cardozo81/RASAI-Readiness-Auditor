"""Process-local handoff for M25 execution.

The handoff is intentionally one-shot. It keeps M25 execution separate from M23 while
preserving persisted measurements for downstream consumers, including report-catalog.
HTML projection is not owned by this runtime module.
"""
from __future__ import annotations

from threading import Lock

from rasai.m25_apdex_experience import ExperienceApdexConfig, M25ExecutionResult, execute_m25_experience
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace

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


