from __future__ import annotations

from pathlib import Path
import os
import sqlite3
from types import SimpleNamespace

from rasai import audit_phase_runtime as phase
from rasai import final_smoke_closure as closure


def test_cat08_final_binding_projects_frozen_feature_settings(monkeypatch) -> None:
    from rasai import improvement_intelligence as improvement
    from rasai import post_smoke_alignment as alignment

    observed: dict[str, str | None] = {}

    def current(*, audit_id, workspace, evidence_snapshot):
        del audit_id, workspace, evidence_snapshot
        observed["enabled"] = os.environ.get(improvement.ENABLED_ENV)
        observed["domains"] = os.environ.get(improvement.DOMAINS_ENV)
        observed["max"] = os.environ.get(improvement.MAX_RECOMMENDATIONS_ENV)
        observed["timeout"] = os.environ.get(improvement.TIMEOUT_ENV)
        return {"status": "SUCCESS"}

    monkeypatch.setattr(
        phase,
        "_AI_HOOKS",
        {"IMPROVEMENT_INTELLIGENCE": phase._Hook("IMPROVEMENT_INTELLIGENCE", current, 100)},
    )
    monkeypatch.setattr(alignment, "_install_improvement_governed_hook", lambda: None)
    monkeypatch.setattr(alignment, "_cat08_required", lambda workspace, audit_id: True)
    monkeypatch.setattr(
        closure,
        "_saved_improvement_feature",
        lambda workspace, audit_id: {
            "domains": "SEO_TECHNICAL,CONTENT_QUALITY",
            "max_recommendations": "30",
            "timeout_seconds": "240",
        },
    )
    for name in (
        improvement.ENABLED_ENV,
        improvement.DOMAINS_ENV,
        improvement.MAX_RECOMMENDATIONS_ENV,
        improvement.TIMEOUT_ENV,
    ):
        monkeypatch.delenv(name, raising=False)

    closure._install_improvement_final_binding()
    result = phase._AI_HOOKS["IMPROVEMENT_INTELLIGENCE"].callback(
        audit_id="AUD-X",
        workspace=SimpleNamespace(),
        evidence_snapshot=SimpleNamespace(),
    )

    assert result["status"] == "SUCCESS"
    assert observed == {
        "enabled": "true",
        "domains": "SEO_TECHNICAL,CONTENT_QUALITY",
        "max": "30",
        "timeout": "240",
    }
    assert os.environ.get(improvement.ENABLED_ENV) is None
    assert os.environ.get(improvement.MAX_RECOMMENDATIONS_ENV) is None


def test_common_crawl_deterministic_hook_accepts_canonical_signature(monkeypatch) -> None:
    from rasai import external_sari

    def base(*, audit_id, workspace, source_blocked=False):
        del audit_id, workspace, source_blocked
        return {"collection_state": "SUCCESS", "services": {}}

    monkeypatch.setattr(
        phase,
        "_COLLECTION_HOOKS",
        {"EXTERNAL_OBSERVABILITY": phase._Hook("EXTERNAL_OBSERVABILITY", base, 50)},
    )
    monkeypatch.setattr(phase, "_DETERMINISTIC_HOOKS", {})
    monkeypatch.setattr(
        external_sari,
        "collect_common_crawl_history",
        external_sari.collect_common_crawl_history,
    )

    closure._install_common_crawl_final_binding()
    hook = phase._DETERMINISTIC_HOOKS["COMMON_CRAWL_CORROBORATION"].callback

    assert hook(
        audit_id="AUD-X",
        workspace=SimpleNamespace(),
        source_blocked=True,
    ) == {"status": "SKIPPED", "reason": "SOURCE_BLOCKED"}


def test_request_remediation_deduplicates_cors_request_symptom() -> None:
    url = "https://cdn.example.test/font.woff2"
    events = [
        {
            "sample_key": "CAT-07:S1",
            "normalized_url": url,
            "source_url": url,
            "family": "CORS",
            "error_type": "CONSOLE_ERROR",
        },
        {
            "sample_key": "CAT-07:S1",
            "normalized_url": url,
            "source_url": url,
            "family": "REQUEST_OTHER",
            "error_type": "REQUEST_FAILED",
        },
        {
            "sample_key": "CAT-07:S2",
            "normalized_url": url,
            "source_url": url,
            "family": "REQUEST_OTHER",
            "error_type": "REQUEST_FAILED",
        },
    ]

    filtered = closure._deduplicate_request_remediation_events(events)

    assert len(filtered) == 2
    assert filtered[0]["family"] == "CORS"
    assert filtered[1]["sample_key"] == "CAT-07:S2"


def test_cost_is_not_comparable_with_required_incomplete_item(monkeypatch, tmp_path: Path) -> None:
    from rasai import console_cost_confirmation as cost

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """CREATE TABLE audit_fulfillment_work_items(
                audit_id TEXT,
                required INTEGER,
                status TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO audit_fulfillment_work_items VALUES (?,?,?)",
            ("AUD-X", 1, "FAILED_RETRYABLE"),
        )
        connection.commit()
    finally:
        connection.close()

    original = cost._CostOutcome(
        comparable=True,
        currency="USD",
        expected=1.0,
        actual=0.5,
        deviation=-0.5,
        deviation_percent=-50.0,
        status="DENTRO DO ESPERADO",
        relation="abaixo da faixa",
        forecast_pages=1,
        actual_pages=1,
        unpriced_ai_attempts=0,
        notes=(),
    )
    monkeypatch.setattr(cost, "_build_outcome", lambda state, forecast: original)
    monkeypatch.setattr(cost, "artifact_status", lambda state: (tmp_path, None))

    closure._install_cost_fulfillment_guard()
    outcome = cost._build_outcome(SimpleNamespace(audit_id="AUD-X"), SimpleNamespace())

    assert outcome is not None
    assert outcome.comparable is False
    assert outcome.status == "NÃO COMPARÁVEL"
    assert outcome.deviation is None
    assert outcome.deviation_percent is None
