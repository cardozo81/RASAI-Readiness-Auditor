"""Four offline regression tests for human-readable audit execution logs."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

from rasai.audit_resume_runtime import _log_continuation_summary
from rasai.audit_reprocess import _RPR_PROCESSED_ITEMS, _remember_rpr_item
from rasai.m23_lighthouse_traceability import _log_lighthouse_profile
from rasai.operational_log import append_operational_event, operational_log_path
from rasai.persistence import AuditWorkspace
from rasai import m23_apdex
from rasai.m23_apdex import SyntheticApdexConfig, execute_m23_apdex
from tests.test_m23_integration import _Gateway, _measurement, _workspace


def _events(workspace):
    return [json.loads(line) for line in operational_log_path(workspace).read_text(
        encoding="utf-8"
    ).splitlines() if line.strip()]


def test_1_terminal_stage_severity_matches_status(tmp_path: Path) -> None:
    workspace = AuditWorkspace(tmp_path / "AUD-LEVELS")
    append_operational_event(workspace, "M23_COMPLETED", status="PARTIAL")
    append_operational_event(workspace, "M23_COMPLETED", status="COMPLETED")
    partial, completed = _events(workspace)
    assert partial["status"] == "PARTIAL" and partial["level"] == "WARNING"
    assert completed["status"] == "COMPLETED" and completed["level"] == "INFO"


def test_2_apdex_reason_matches_persisted_value_or_explicit_absence(tmp_path: Path) -> None:
    for index, (state, reason) in enumerate((
        ("SUCCESS", None), ("PARTIAL", "SMALL_GROUP_BELOW_NORMAL_MINIMUM"),
    )):
        workspace = _workspace(str(tmp_path / f"case-{index}"))
        config = SyntheticApdexConfig(
            enabled=True, threshold_seconds=1.0, target_valid_samples=1,
            max_attempts_per_context=1, max_pages=1, timeout_seconds=5.0,
            delay_seconds=0.0, concurrency=1,
        )
        with patch.object(m23_apdex, "_run_status", return_value=(state, reason)):
            execute_m23_apdex(
                audit_id="AUD-M23", workspace=workspace, config=config,
                gateway=_Gateway([_measurement(500)]),
            )
        with sqlite3.connect(workspace.database) as connection:
            persisted = connection.execute(
                "SELECT reason FROM synthetic_apdex_runs WHERE audit_id='AUD-M23'"
            ).fetchone()[0]
        event = next(e for e in reversed(_events(workspace))
                     if e["event"] == "M23_COMPLETED")
        assert event["status"] == state
        assert persisted == reason
        assert event["motivo"] == (persisted if persisted else "não informado")


def test_3_continuation_summary_with_and_without_items(tmp_path: Path) -> None:
    workspace = AuditWorkspace(tmp_path / "AUD-CONTINUATION")
    none = SimpleNamespace(
        attempted_items=0, successful_items=0, remaining_items=0,
        processing_status="COMPLETE", reprocess_id=None,
    )
    _log_continuation_summary(workspace, "AUD-CONTINUATION", none, ())
    some = SimpleNamespace(
        attempted_items=2, successful_items=1, remaining_items=1,
        processing_status="PARTIAL_RETRYABLE", reprocess_id="RPR-TEST",
    )
    token = _RPR_PROCESSED_ITEMS.set(())
    try:
        _remember_rpr_item(SimpleNamespace(component="SEMANTIC_AI", scope_key="SNP-A1"))
        _remember_rpr_item(SimpleNamespace(component="SEMANTIC_AI", scope_key="SNP-B2"))
        names = _RPR_PROCESSED_ITEMS.get()
        _log_continuation_summary(workspace, "AUD-CONTINUATION", some, names)
    finally:
        _RPR_PROCESSED_ITEMS.reset(token)
    empty, processed = _events(workspace)
    assert empty["detail"] == "nenhum item pendente"
    assert empty["processed_items"] == 0 and empty["item_names"] == []
    assert empty["level"] == "INFO"
    assert (processed["processed_items"], processed["completed_items"],
            processed["pending_items"]) == (2, 1, 1)
    assert processed["item_names"] == list(names)
    assert len(processed["item_names"]) == 2
    assert all("SNP-" not in label for label in processed["item_names"])
    assert processed["level"] == "WARNING"


def test_4_lighthouse_missing_throttling_is_explicit(tmp_path: Path) -> None:
    workspace = AuditWorkspace(tmp_path / "AUD-LIGHTHOUSE")
    missing = SimpleNamespace(
        observation_id="OBS-1", device="MOBILE", url="https://example.test",
        form_factor=None, throttling_method=None, rtt_ms=None,
        throughput_kbps=None, request_latency_ms=None,
        download_throughput_kbps=None, upload_throughput_kbps=None,
        cpu_slowdown_multiplier=None, benchmark_index=None,
    )
    _log_lighthouse_profile(workspace, "AUD-LIGHTHOUSE", missing)
    recorded = _events(workspace)[0]
    keys = (
        "form_factor", "throttling_method", "rtt_ms", "throughput_kbps",
        "request_latency_ms", "download_throughput_kbps",
        "upload_throughput_kbps", "cpu_slowdown_multiplier", "benchmark_index",
    )
    assert all(recorded[key] == "não informado pela ferramenta" for key in keys)
    assert all(recorded[key] is not None and recorded[key] != 0 for key in keys)

    measured = SimpleNamespace(**{
        **vars(missing),
        "rtt_ms": 140.0, "cpu_slowdown_multiplier": 4.0,
        "throughput_kbps": 1600.0,
    })
    _log_lighthouse_profile(workspace, "AUD-LIGHTHOUSE", measured)
    effective = _events(workspace)[1]
    assert effective["rtt_ms"] == 140.0
    assert effective["cpu_slowdown_multiplier"] == 4.0
    assert effective["throughput_kbps"] == 1600.0
