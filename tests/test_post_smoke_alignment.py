from __future__ import annotations

from rasai.observability.store import observability_database_path

def _obs_path(workspace: Path) -> Path:
    path = observability_database_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.post_smoke_alignment import _cat08_ai_authorized, _cat08_required, _primary_ai_context
from rasai.m18_persistence import current_attempt_governance
from rasai.post_smoke_hotfix import (
    _install_materialized_sidecar_counts,
    _latest_common_crawl_dataset,
)


def test_cat08_required_uses_frozen_plan_and_auto_session(tmp_path: Path) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY,
                configuration_json TEXT NOT NULL
            );
            CREATE TABLE ai_audit_sessions(
                audit_id TEXT PRIMARY KEY,
                strategy TEXT,
                initial_provider TEXT,
                initial_model TEXT,
                initial_reasoning_profile TEXT,
                effective_provider TEXT,
                effective_model TEXT,
                effective_reasoning_profile TEXT
            );
            """
        )
        payload = {
            "audit_catalog": {
                "selected": ["CAT-08"],
                "ai_enabled": True,
                "items": [
                    {
                        "id": "CAT-08",
                        "selected": True,
                        "ai_mode": "REQUIRED",
                        "ai_execution_enabled": True,
                    }
                ],
            }
        }
        connection.execute(
            "INSERT INTO audit_execution_configurations VALUES(?,?)",
            ("AUD-1", json.dumps(payload)),
        )
        connection.execute(
            "INSERT INTO ai_audit_sessions VALUES(?,?,?,?,?,?,?,?)",
            (
                "AUD-1",
                "AUTO",
                "DEEPSEEK",
                "deepseek-v4-pro",
                "LOW",
                "OPENAI",
                "gpt-5.6-luna",
                "NONE",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(database=database)
    assert _cat08_required(workspace, "AUD-1") is True
    assert _primary_ai_context(workspace, "AUD-1") == ("auto", "", "")


def test_rpr_policy_overrides_original_cat08_ai_authorization(tmp_path: Path) -> None:
    from rasai.reprocess_policy import reprocess_policy

    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """CREATE TABLE audit_execution_configurations(
                audit_id TEXT PRIMARY KEY,
                configuration_json TEXT NOT NULL
            )"""
        )
        payload = {
            "audit_catalog": {
                "selected": ["CAT-08"],
                "ai_enabled": False,
                "items": [
                    {
                        "id": "CAT-08",
                        "selected": True,
                        "ai_mode": "REQUIRED",
                        "ai_execution_enabled": False,
                    }
                ],
            }
        }
        connection.execute(
            "INSERT INTO audit_execution_configurations VALUES(?,?)",
            ("AUD-RPR", json.dumps(payload)),
        )
        connection.commit()
    finally:
        connection.close()

    workspace = SimpleNamespace(database=database)

    assert _cat08_ai_authorized(workspace, "AUD-RPR") is False

    with reprocess_policy(
        selected_items=["IMPROVEMENT_INTELLIGENCE::AUDIT"],
        use_ai=True,
        ai_provider="auto",
    ):
        assert _cat08_ai_authorized(workspace, "AUD-RPR") is True
        assert _primary_ai_context(workspace, "AUD-RPR") == ("auto", "", "")

    with reprocess_policy(
        selected_items=["IMPROVEMENT_INTELLIGENCE::AUDIT"],
        use_ai=False,
        ai_provider="auto",
    ):
        assert _cat08_ai_authorized(workspace, "AUD-RPR") is False
        assert _primary_ai_context(workspace, "AUD-RPR") is None


def test_common_crawl_scoring_reuses_preseal_dataset(tmp_path: Path) -> None:
    database = _obs_path(tmp_path)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE datasets(dataset_id TEXT,source_type TEXT,collected_at TEXT)"
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-OLD", "COMMON_CRAWL_CDX_HISTORY", "2026-09-17T10:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-NEW", "COMMON_CRAWL_CDX_HISTORY", "2026-09-17T11:00:00+00:00"),
        )
        connection.commit()
    finally:
        connection.close()

    assert _latest_common_crawl_dataset(tmp_path) == "OBS-NEW"


def test_empty_common_crawl_dataset_is_not_counted_as_source_with_data(tmp_path: Path) -> None:
    audit_database = tmp_path / "audit.db"
    sqlite3.connect(audit_database).close()
    sidecar = _obs_path(tmp_path)
    connection = sqlite3.connect(sidecar)
    try:
        connection.executescript(
            """
            CREATE TABLE datasets(dataset_id TEXT,source_type TEXT,collected_at TEXT);
            CREATE TABLE web_archive_observations(dataset_id TEXT,record_id TEXT);
            CREATE TABLE crux_history(dataset_id TEXT,record_id TEXT);
            """
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-CC", "COMMON_CRAWL_CDX_HISTORY", "2026-09-17T11:00:00+00:00"),
        )
        connection.execute(
            "INSERT INTO datasets VALUES(?,?,?)",
            ("OBS-CRUX", "CHROME_UX_REPORT_HISTORY", "2026-09-17T11:00:00+00:00"),
        )
        connection.execute("INSERT INTO crux_history VALUES(?,?)", ("OBS-CRUX", "CRUX-1"))
        connection.commit()
    finally:
        connection.close()

    _install_materialized_sidecar_counts()
    from rasai import post_smoke_alignment as alignment

    counts = alignment._sidecar_source_counts(audit_database)
    assert counts.get("CHROME_UX_REPORT_HISTORY") == 1
    assert "COMMON_CRAWL_CDX_HISTORY" not in counts

def test_semantic_governance_preserves_existing_audit_runner_wrapper_chain(monkeypatch) -> None:
    from rasai import audit_runner, m7, post_smoke_alignment as alignment

    calls: list[str] = []

    def existing_stack(*args, **kwargs):
        calls.append("existing-stack")
        return "wrapped-result"

    def canonical(*args, **kwargs):
        calls.append("canonical-direct")
        return "canonical-result"

    def m20_already_wrapped(*args, **kwargs):
        return None

    m20_already_wrapped._rasai_post_smoke_governance = True
    monkeypatch.setattr(audit_runner, "execute_m7", existing_stack)
    monkeypatch.setattr(m7, "execute_m7", canonical)
    monkeypatch.setattr(audit_runner, "execute_m20", m20_already_wrapped)

    alignment._install_ai_governance_completion()
    result = audit_runner.execute_m7(
        audit_id="AUD",
        workspace=None,
    )

    assert result == "wrapped-result"
    assert calls == ["existing-stack"]

def test_content_remediation_prepares_governance_before_provider_call(monkeypatch) -> None:
    from rasai import audit_runner, m7, post_smoke_alignment as alignment

    order: list[str] = []

    def m7_already_wrapped(*args, **kwargs):
        return None

    m7_already_wrapped._rasai_post_smoke_governance = True

    def provider_boundary(*args, **kwargs):
        order.append("provider")
        assert current_attempt_governance() == (
            "CONTENT_REMEDIATION",
            "AIT-CONTENT",
            "AIR-CONTENT",
        )
        return SimpleNamespace(
            status="SUCCESS",
            suggestion_ids=("S1",),
            attempted_contexts=1,
        )

    monkeypatch.setattr(m7, "execute_m7", m7_already_wrapped)
    monkeypatch.setattr(audit_runner, "execute_m20", provider_boundary)
    monkeypatch.setattr(
        alignment,
        "_record_dependency",
        lambda **kwargs: order.append("dependency"),
    )
    monkeypatch.setattr(
        alignment,
        "_prepare_content_task",
        lambda workspace, audit_id: (
            order.append("prepare") or ("AIT-CONTENT", "AIR-CONTENT", ("FINDING:F1",))
        ),
    )
    monkeypatch.setattr(
        alignment,
        "_complete_content_task",
        lambda workspace, round_id, requirements, result, failed=False: order.append("complete"),
    )

    alignment._install_ai_governance_completion()
    result = audit_runner.execute_m20(
        audit_id="AUD",
        workspace=SimpleNamespace(),
        enabled=True,
    )

    assert result.status == "SUCCESS"
    assert order == ["dependency", "prepare", "provider", "complete"]


def test_improvement_runtime_projects_invalid_configuration_before_provider(
    monkeypatch,
) -> None:
    from rasai import improvement_intelligence_runtime as runtime

    projected: dict[str, object] = {}
    monkeypatch.setattr(
        runtime.ImprovementConfig,
        "from_environment",
        classmethod(
            lambda cls, env=None: (_ for _ in ()).throw(
                ValueError("domínios de análise desconhecidos: INVALID")
            )
        ),
    )

    def project(_workspace, *, audit_id, component, status, error_class, error_code,
                error_message, retryable, **_kwargs):
        projected.update(
            audit_id=audit_id,
            component=component,
            status=status,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )

    monkeypatch.setattr(runtime, "set_work_item_status", project)
    monkeypatch.setattr(runtime, "try_append_operational_event", lambda *args, **kwargs: None)

    outcome = runtime._governed_improvement_hook(
        audit_id="AUD-1",
        workspace=SimpleNamespace(),
        evidence_snapshot=SimpleNamespace(evidence_snapshot_id="AIE-1"),
    )

    assert outcome == {
        "status": "NOT_CONFIGURED",
        "reason": "IMPROVEMENT_CONFIGURATION_INVALID",
        "provider_called": False,
    }
    assert projected["status"] == "NOT_CONFIGURED"
    assert projected["error_class"] == "CONFIGURATION"
    assert projected["error_code"] == "IMPROVEMENT_CONFIGURATION_INVALID"
    assert "INVALID" in str(projected["error_message"])


def test_improvement_runtime_projects_governance_preparation_failure(
    monkeypatch,
) -> None:
    from rasai import improvement_intelligence_runtime as runtime

    config = SimpleNamespace(
        enabled=True,
        provider="auto",
        model="",
        reasoning="",
        domains=("CONTENT",),
        max_recommendations=30,
        language="pt-BR",
        fingerprint=lambda: "CFG-FP",
    )
    projected: dict[str, object] = {}

    monkeypatch.setattr(runtime.ImprovementConfig, "from_environment", classmethod(lambda cls, env=None: config))
    monkeypatch.setattr(runtime, "_apply_reprocess_ai_policy", lambda value: value)
    monkeypatch.setattr(runtime, "_register_required_fulfillment", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        runtime,
        "register_task",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("task registration failed")),
    )

    def project(_workspace, *, audit_id, component, status, error_class, error_code,
                error_message, retryable, **_kwargs):
        projected.update(
            audit_id=audit_id,
            component=component,
            status=status,
            error_class=error_class,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )

    monkeypatch.setattr(runtime, "set_work_item_status", project)
    monkeypatch.setattr(runtime, "try_append_operational_event", lambda *args, **kwargs: None)

    outcome = runtime._governed_improvement_hook(
        audit_id="AUD-1",
        workspace=SimpleNamespace(),
        evidence_snapshot=SimpleNamespace(
            evidence_snapshot_id="AIE-1",
            fingerprint="EVIDENCE-FP",
            evidence_ids=("EV-1",),
        ),
    )

    assert outcome == {
        "status": "ERROR",
        "reason": "IMPROVEMENT_GOVERNANCE_PREPARATION_RUNTIMEERROR",
        "provider_called": False,
    }
    assert projected["status"] == "FAILED_RETRYABLE"
    assert projected["error_class"] == "ORCHESTRATION"
    assert projected["error_code"] == "IMPROVEMENT_GOVERNANCE_PREPARATION_RUNTIMEERROR"
