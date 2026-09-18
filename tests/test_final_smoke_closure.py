from __future__ import annotations

from pathlib import Path
import inspect
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


def test_cat05_is_partial_when_requested_common_crawl_failed(tmp_path: Path) -> None:
    from rasai.catalog_report_catalog_state import _catalog_status

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """CREATE TABLE standards_service_runs(
                audit_id TEXT,
                service_id TEXT,
                requested INTEGER,
                effective_enabled INTEGER,
                targets_attempted INTEGER,
                state TEXT,
                details_json TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO standards_service_runs VALUES (?,?,?,?,?,?,?)",
            (
                "AUD-X",
                "common-crawl",
                1,
                1,
                0,
                "NO_DATA",
                '{"reason":"PRE_SCORING_COLLECTION_STATE_NOT_FOUND"}',
            ),
        )
        connection.commit()
    finally:
        connection.close()

    data = SimpleNamespace(
        audit_id="AUD-X",
        configuration={"audit_catalog": {"selected": ["CAT-05"]}},
        config_hash="same",
        computed_hash="same",
        selected={"CAT-05"},
    )
    status, tone, detail = _catalog_status(database, data, "CAT-05")

    assert status == "PARCIAL"
    assert tone == "warn"
    assert "Common Crawl" in detail


def test_catalog_renderer_does_not_materialize_recommendation_governance() -> None:
    from rasai import catalog_report_site

    source = inspect.getsource(catalog_report_site.materialize_catalog_report_site)

    assert "evaluate_recommendations(" not in source


def test_cat08_final_binding_reasserts_auto_primary_ai_context(monkeypatch) -> None:
    from rasai import ai_orchestration_unification as orchestration
    from rasai import post_smoke_alignment as alignment

    observed: dict[str, object] = {}

    def raw_hook(*, audit_id, workspace, evidence_snapshot):
        del audit_id, workspace, evidence_snapshot
        observed["context"] = orchestration._PRIMARY_AI_CONTEXT.get()
        return {"status": "SUCCESS"}

    monkeypatch.setattr(
        phase,
        "_AI_HOOKS",
        {"IMPROVEMENT_INTELLIGENCE": phase._Hook("IMPROVEMENT_INTELLIGENCE", raw_hook, 100)},
    )
    monkeypatch.setattr(alignment, "_cat08_required", lambda workspace, audit_id: False)
    monkeypatch.setattr(
        alignment,
        "_primary_ai_context",
        lambda workspace, audit_id: ("auto", "", ""),
    )
    orchestration._PRIMARY_AI_CONTEXT.set(None)

    closure._install_improvement_final_binding()
    result = phase._AI_HOOKS["IMPROVEMENT_INTELLIGENCE"].callback(
        audit_id="AUD-X",
        workspace=SimpleNamespace(),
        evidence_snapshot=SimpleNamespace(),
    )

    assert result["status"] == "SUCCESS"
    assert observed["context"] == ("auto", "", "")
    assert orchestration._PRIMARY_AI_CONTEXT.get() is None


def test_common_crawl_final_binding_collects_preseal_after_late_owner(monkeypatch, tmp_path: Path) -> None:
    from rasai import external_observability_runtime as external
    from rasai import standards_service_registry as registry

    calls: list[dict[str, object]] = []
    persisted: list[dict[str, object]] = []

    def late_owner(*, audit_id, workspace, source_blocked=False):
        del audit_id, workspace, source_blocked
        return {
            "collection_state": "SUCCESS",
            "services": {"crux-history": {"collection_state": "SUCCESS"}},
        }

    monkeypatch.setattr(
        phase,
        "_COLLECTION_HOOKS",
        {"EXTERNAL_OBSERVABILITY": phase._Hook("EXTERNAL_OBSERVABILITY", late_owner, 50)},
    )
    monkeypatch.setattr(phase, "_DETERMINISTIC_HOOKS", {})
    monkeypatch.setattr(registry, "service", lambda service_id: service_id)
    monkeypatch.setattr(
        registry,
        "service_state",
        lambda service_id, env: {
            "state": "READY",
            "requested": True,
            "configured": True,
            "effective_enabled": True,
            "configuration_source": "TEST",
            "missing_configuration": [],
        },
    )
    monkeypatch.setattr(external, "common_crawl_max_urls", lambda value: 1)
    monkeypatch.setattr(external, "common_crawl_index_count", lambda value: 1)
    monkeypatch.setattr(external, "_positive_float", lambda value, default: 1.0)

    def collect_common_crawl_history(**kwargs):
        calls.append(dict(kwargs))
        return "DATASET-CC-1"

    monkeypatch.setattr(external, "collect_common_crawl_history", collect_common_crawl_history)
    monkeypatch.setattr(
        external,
        "_upsert_service_run",
        lambda **kwargs: persisted.append(dict(kwargs)),
    )

    closure._install_common_crawl_final_binding()
    hook = phase._COLLECTION_HOOKS["EXTERNAL_OBSERVABILITY"].callback
    workspace = SimpleNamespace(root=tmp_path, database=tmp_path / "audit.db")
    result = hook(audit_id="AUD-X", workspace=workspace, source_blocked=False)

    assert len(calls) == 1
    assert calls[0]["audit_workspace"] == tmp_path
    assert result["collection_state"] == "SUCCESS"
    assert result["services"]["common-crawl"]["collection_state"] == "SUCCESS"
    assert result["services"]["common-crawl"]["datasets"] == ["DATASET-CC-1"]
    assert persisted and persisted[0]["service_id"] == "common-crawl"


def test_recommendation_governance_finishes_before_reporting_phase() -> None:
    from rasai import audit_runner

    source = inspect.getsource(audit_runner.run_audit)
    governance = source.index("evaluate_recommendations(")
    reporting = source.index("_set_status(persistence, audit_id, AuditStatus.REPORTING)")

    assert governance < reporting
