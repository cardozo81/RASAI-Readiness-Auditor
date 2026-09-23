from __future__ import annotations

from pathlib import Path

import pytest

from rasai.consolidation.selection import resolve_selection, validate_selection_mode
from rasai.execution_contract import validate_execution_job_payload


class _FakeIndex:
    audits_root = Path(".")

    def __init__(self) -> None:
        self.rows = (
            {
                "audit_id": "AUD-001",
                "event_time": "2026-09-01T10:00:00+00:00",
                "status": "COMPLETED",
                "completion_status": "COMPLETE",
                "url_count": 1,
                "devices_json": '["MOBILE"]',
            },
            {
                "audit_id": "AUD-002",
                "event_time": "2026-09-05T10:00:00+00:00",
                "status": "COMPLETED",
                "completion_status": "COMPLETE",
                "url_count": 1,
                "devices_json": '["MOBILE"]',
            },
            {
                "audit_id": "AUD-003",
                "event_time": "2026-09-10T10:00:00+00:00",
                "status": "COMPLETED",
                "completion_status": "COMPLETE",
                "url_count": 1,
                "devices_json": '["MOBILE"]',
            },
            {
                "audit_id": "AUD-OTHER",
                "event_time": "2026-09-06T10:00:00+00:00",
                "status": "COMPLETED",
                "completion_status": "COMPLETE",
                "url_count": 1,
                "devices_json": '["DESKTOP"]',
            },
        )
        self.urls = {
            "AUD-001": "https://example.test/page",
            "AUD-002": "https://example.test/page",
            "AUD-003": "https://example.test/page",
            "AUD-OTHER": "https://example.test/page",
        }

    def candidate_audits(self, filters):
        ids = set(filters.audit_ids)
        return tuple(
            row for row in self.rows
            if not ids or row["audit_id"] in ids
        )

    def available_urls(self, filters):
        ids = tuple(filters.audit_ids)
        if len(ids) != 1:
            return ()
        value = self.urls.get(ids[0])
        return (value,) if value else ()


def test_selection_modes_are_explicit() -> None:
    assert validate_selection_mode("all") == "ALL"
    assert validate_selection_mode("success_only") == "SUCCESS_ONLY"
    assert validate_selection_mode("manual") == "MANUAL"
    with pytest.raises(ValueError, match="selection_mode"):
        validate_selection_mode("interval")


def test_all_selection_orders_base_current_and_includes_intermediate() -> None:
    selected = resolve_selection(
        _FakeIndex(),
        "AUD-003",
        "AUD-001",
        selection_mode="ALL",
    )
    assert selected.baseline_audit_id == "AUD-001"
    assert selected.current_audit_id == "AUD-003"
    assert selected.audit_ids == ("AUD-001", "AUD-002", "AUD-003")
    assert selected.intermediate_count == 1
    assert selected.url == "https://example.test/page"
    assert selected.device == "MOBILE"


def test_base_and_current_follow_actual_timestamp_not_selection_order_or_offset_text() -> None:
    index = _FakeIndex()
    index.rows = (
        {
            "audit_id": "AUD-LATER-INSTANT",
            "event_time": "2026-09-23T08:30:00-03:00",
            "status": "COMPLETED",
            "completion_status": "COMPLETE",
            "url_count": 1,
            "devices_json": '["MOBILE"]',
        },
        {
            "audit_id": "AUD-EARLIER-INSTANT",
            "event_time": "2026-09-23T11:00:00+00:00",
            "status": "COMPLETED",
            "completion_status": "COMPLETE",
            "url_count": 1,
            "devices_json": '["MOBILE"]',
        },
    )
    index.urls = {
        "AUD-LATER-INSTANT": "https://example.test/page",
        "AUD-EARLIER-INSTANT": "https://example.test/page",
    }

    selected = resolve_selection(
        index,
        "AUD-LATER-INSTANT",
        "AUD-EARLIER-INSTANT",
        selection_mode="ALL",
    )

    assert selected.baseline_audit_id == "AUD-EARLIER-INSTANT"
    assert selected.current_audit_id == "AUD-LATER-INSTANT"
    assert selected.audit_ids == ("AUD-EARLIER-INSTANT", "AUD-LATER-INSTANT")
    assert selected.period_start == "2026-09-23T11:00:00+00:00"
    assert selected.period_end == "2026-09-23T08:30:00-03:00"


def test_manual_selection_keeps_markers_and_only_requested_intermediate() -> None:
    selected = resolve_selection(
        _FakeIndex(),
        "AUD-001",
        "AUD-003",
        selection_mode="MANUAL",
        manual_audit_ids=(),
    )
    assert selected.audit_ids == ("AUD-001", "AUD-003")
    assert selected.excluded_audit_ids == ("AUD-002",)


def test_selection_rejects_incompatible_device() -> None:
    with pytest.raises(ValueError, match="mesmo dispositivo"):
        resolve_selection(
            _FakeIndex(),
            "AUD-001",
            "AUD-OTHER",
            selection_mode="ALL",
        )


def test_success_only_uses_source_governance(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_governance(_root, _rows):
        return {
            "audits": [
                {"audit_id": "AUD-001", "source_state": "SUCCESS"},
                {"audit_id": "AUD-002", "source_state": "REPROCESS_REQUIRED"},
                {"audit_id": "AUD-003", "source_state": "SUCCESS_WITH_LIMITATIONS"},
            ]
        }

    monkeypatch.setattr(
        "rasai.consolidation.selection.build_source_governance",
        fake_governance,
    )
    selected = resolve_selection(
        _FakeIndex(),
        "AUD-001",
        "AUD-003",
        selection_mode="SUCCESS_ONLY",
    )
    assert selected.audit_ids == ("AUD-001", "AUD-003")
    assert selected.excluded_audit_ids == ("AUD-002",)


def test_execution_contract_accepts_deterministic_consolidated_job() -> None:
    validate_execution_job_payload(
        "REPORT_REFRESH",
        {
            "surface": "consolidated",
            "baseline_audit_id": "AUD-001",
            "current_audit_id": "AUD-003",
            "selection_mode": "ALL",
            "use_ai": False,
            "ai_timeout_seconds": 180.0,
        },
    )


def test_execution_contract_allows_requested_ai_without_ready_provider() -> None:
    validate_execution_job_payload(
        "REPORT_REFRESH",
        {
            "surface": "consolidated",
            "baseline_audit_id": "AUD-001",
            "current_audit_id": "AUD-003",
            "selection_mode": "ALL",
            "use_ai": True,
        },
    )

    validate_execution_job_payload(
        "REPORT_REFRESH",
        {
            "surface": "consolidated",
            "baseline_audit_id": "AUD-001",
            "current_audit_id": "AUD-003",
            "selection_mode": "MANUAL",
            "audit_ids": ["AUD-002"],
            "use_ai": True,
            "ai_provider": "auto",
            "ai_timeout_seconds": 180.0,
        },
    )
