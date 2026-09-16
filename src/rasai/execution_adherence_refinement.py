"""Execution-boundary corrections for the pre-production report contract.

Two late-write gaps are closed here without changing audit/scoring semantics:

* M25 records the timestamp of each individual sample when that measurement finishes,
  instead of assigning the same later batch-persistence timestamp to every sample.
* the catalog report is rebuilt only after the complete console wrapper chain returns,
  so late fulfillment/cost persistence is already committed before a report is marked
  FINAL.
"""
from __future__ import annotations

from dataclasses import replace
from functools import wraps
from pathlib import Path
import threading
from typing import Any

_LOCK = threading.RLock()
_SAMPLE_TIMESTAMPS: dict[tuple[str, str, str, int], str] = {}


def _sample_key(audit_id: Any, url: Any, device: Any, run_index: Any) -> tuple[str, str, str, int]:
    try:
        index = int(run_index)
    except (TypeError, ValueError):
        index = 0
    return (str(audit_id or ""), str(url or ""), str(device or "").upper(), index)


def _remember_sample_timestamp(audit_id: Any, url: Any, device: Any, run_index: Any, timestamp: str) -> None:
    with _LOCK:
        _SAMPLE_TIMESTAMPS[_sample_key(audit_id, url, device, run_index)] = str(timestamp)


def _take_sample_timestamp(audit_id: Any, url: Any, device: Any, run_index: Any) -> str | None:
    with _LOCK:
        return _SAMPLE_TIMESTAMPS.pop(_sample_key(audit_id, url, device, run_index), None)


def _discard_audit_timestamps(audit_id: Any) -> None:
    prefix = str(audit_id or "")
    with _LOCK:
        for key in [key for key in _SAMPLE_TIMESTAMPS if key[0] == prefix]:
            _SAMPLE_TIMESTAMPS.pop(key, None)


def install_individual_m25_timestamps() -> None:
    """Bind M25 sample time to each completed measurement, not to the later batch insert."""
    from rasai import m25_apdex_experience as m25

    if getattr(m25, "_rasai_individual_sample_timestamp", False):
        return

    original_log = m25._log_progress
    original_persisted_sample = m25._persisted_sample

    @wraps(original_log)
    def log_progress(
        workspace: Any,
        audit_id: str,
        url: str,
        device: str,
        page_index: int,
        page_total: int,
        target: int,
        max_attempts: int,
        item: Any,
    ) -> None:
        # _log_progress is called immediately after measure/classify.  Recording here
        # gives each sample its own real collection timestamp even when persistence is
        # intentionally deferred until all samples for the device have finished.
        _remember_sample_timestamp(audit_id, url, device, item.run_index, m25._utc_now())
        original_log(
            workspace,
            audit_id,
            url,
            device,
            page_index,
            page_total,
            target,
            max_attempts,
            item,
        )

    @wraps(original_persisted_sample)
    def persisted_sample(
        audit_id: str,
        page_id: str,
        url: str,
        profile: Any,
        config: Any,
        calibration: Any,
        item: Any,
    ) -> Any:
        sample = original_persisted_sample(
            audit_id,
            page_id,
            url,
            profile,
            config,
            calibration,
            item,
        )
        timestamp = _take_sample_timestamp(audit_id, url, item.device, item.run_index)
        return replace(sample, captured_at=timestamp) if timestamp else sample

    log_progress._rasai_individual_sample_timestamp = True  # type: ignore[attr-defined]
    persisted_sample._rasai_individual_sample_timestamp = True  # type: ignore[attr-defined]
    m25._log_progress = log_progress
    m25._persisted_sample = persisted_sample
    m25._rasai_individual_sample_timestamp = True


def finalize_catalog_projection(state: Any) -> Path | None:
    """Rebuild report-catalog after every late persistence owner has returned."""
    audit_id = str(getattr(state, "audit_id", "") or "").strip()
    if not audit_id:
        return None
    if str(getattr(state, "operation", "") or "").upper() in {
        "LOCAL:COST_DECLINED",
        "LOCAL:AI_CONFIGURATION",
    }:
        return None

    from rasai.catalog_report_site import catalog_report_is_fresh, materialize_catalog_report_site
    from rasai.console_artifacts import artifact_status
    from rasai.persistence import AuditWorkspace

    root, _artifact = artifact_status(state)
    if root is None:
        return None
    workspace = AuditWorkspace(Path(root))
    if not workspace.database.is_file():
        return None

    path = materialize_catalog_report_site(audit_id=audit_id, workspace=workspace)
    if not catalog_report_is_fresh(audit_id=audit_id, workspace=workspace):
        raise RuntimeError(
            "report-catalog não permaneceu aderente ao audit.db após a finalização da execução"
        )
    return path


def finalize_after_console_run(state: Any, code: int) -> int:
    """Final execution boundary used by the outermost AI configuration wrapper."""
    audit_id = str(getattr(state, "audit_id", "") or "").strip()
    try:
        finalize_catalog_projection(state)
        return int(code)
    finally:
        if audit_id:
            _discard_audit_timestamps(audit_id)


__all__ = [
    "finalize_after_console_run",
    "finalize_catalog_projection",
    "install_individual_m25_timestamps",
]
