from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from rasai.audit_fulfillment import BLOCKED, LIVE_RECOLLECTION, REPLAY_SAFE, SUCCESS, list_work_items, register_work_item, set_work_item_status
from rasai.core_integrity_runtime import install as install_core_integrity
from rasai.domain import Audit
from rasai.execution_environment import override_environment, resolve_environment
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.selective_optional_reprocess import (
    _backfill_console_search,
    _install_contextual_optional_hooks,
    _recover_search,
    _validate_success_integrity,
)
from rasai.selective_reprocess_context import scope


AUDIT_ID = "AUD-OPTIONAL-RPR"


def _workspace(root: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="optional recovery"))
    return workspace


def _success_item(workspace: AuditWorkspace, component: str, temporal_mode: str = REPLAY_SAFE) -> None:
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component=component,
        required=True,
        temporal_mode=temporal_mode,
        status=SUCCESS,
        retryable=False,
        configuration={"requested": True},
    )
    set_work_item_status(
        workspace,
        audit_id=AUDIT_ID,
        component=component,
        status=SUCCESS,
        result_ref=f"{component.casefold()}:effective",
        retryable=False,
    )


def test_search_recovery_uses_persisted_contract_and_current_secret(monkeypatch) -> None:
    from rasai import selective_optional_reprocess as runtime
    from rasai.search_intelligence import runtime as search_runtime
    from rasai.search_intelligence.models import DomainMatchStatus

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        register_work_item(
            workspace,
            audit_id=AUDIT_ID,
            component="SEARCH_INTELLIGENCE",
            required=True,
            temporal_mode=LIVE_RECOLLECTION,
            retryable=True,
            configuration={
                "requested": True,
                "queries": ["rasai readiness"],
                "depth": 10,
                "region": "RS",
                "device": "mobile",
                "competitive": False,
                "compare_content": True,
                "max_content_pages": 4,
                "content_timeout_seconds": 12.5,
                "content_max_bytes": 1_500_000,
                "content_max_redirects": 2,
                "market": "BR",
                "language": "pt-BR",
                "mode": "live",
                "provider": "serpapi",
                "engine": "google",
                "max_queries": 10,
                "max_requests": 10,
                "max_depth": 20,
                "max_competitors": 10,
                "timeout_seconds": 20,
                "retries": 0,
                "min_interval_seconds": 0,
            },
        )
        item = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "SEARCH_INTELLIGENCE")
        monkeypatch.setenv("RASAI_SERPAPI_API_KEY", "current-secret")
        monkeypatch.setattr(runtime, "_audit_domain", lambda *args, **kwargs: "example.com")
        monkeypatch.setattr(runtime, "_audit_target_url", lambda *args, **kwargs: "https://example.com/")
        captured: dict[str, object] = {}

        def fake_execute(requests, *, config, environment, workspace_root, fixture_path=None, evidence_sink=None):
            items = tuple(requests)
            captured["requests"] = items
            captured["config"] = config
            captured["environment"] = dict(environment)
            assert environment["RASAI_SERPAPI_API_KEY"] == "current-secret"
            return SimpleNamespace(
                mode="live",
                provider="serpapi",
                results=tuple(
                    SimpleNamespace(
                        domain_status=DomainMatchStatus.NOT_FOUND_WITHIN_DEPTH,
                        error_code=None,
                        error_message=None,
                    )
                    for _ in items
                ),
                projected_http_request_ceiling=1,
                actual_http_requests=1,
                persisted=True,
            )

        monkeypatch.setattr(search_runtime, "execute_search", fake_execute)
        from rasai.search_intelligence import competitive_runtime as competitive_runtime

        def fake_competitive(execution, **kwargs):
            captured["competitive_kwargs"] = kwargs
            return SimpleNamespace(
                analyses=(),
                content_enabled=kwargs["content_enabled"],
                content_http_requests=0,
                persisted=True,
            )

        monkeypatch.setattr(competitive_runtime, "execute_competitive_intelligence", fake_competitive)

        assert _recover_search(workspace, AUDIT_ID, item) is True

        effective = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "SEARCH_INTELLIGENCE")
        assert effective.status == "SUCCESS"
        requests = captured["requests"]
        assert len(requests) == 1
        assert requests[0].query == "rasai readiness"
        assert requests[0].domain_of_interest == "example.com"
        assert captured["config"].provider == "serpapi"
        assert captured["config"].mode == "live"
        assert captured["config"].retries == 0
        assert captured["config"].min_interval_seconds == 0.0
        competitive_kwargs = captured["competitive_kwargs"]
        assert competitive_kwargs["content_enabled"] is True
        assert competitive_kwargs["customer_url"] == "https://example.com/"
        assert competitive_kwargs["max_competitor_pages"] == 4
        assert competitive_kwargs["fetcher"].timeout_seconds == 12.5
        assert competitive_kwargs["fetcher"].max_bytes == 1_500_000
        assert competitive_kwargs["fetcher"].max_redirects == 2


def test_successful_optional_services_are_reused_by_contextual_hooks() -> None:
    from rasai import improvement_intelligence_runtime as improvement_runtime
    from rasai import standards_gsc_observability_runtime as gsc_runtime

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        _success_item(workspace, "IMPROVEMENT_INTELLIGENCE")
        _success_item(workspace, "GOOGLE_SEARCH_CONSOLE", LIVE_RECOLLECTION)
        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS improvement_intelligence_runs(
                        audit_id TEXT PRIMARY KEY,status TEXT,target_url TEXT,findings_count INTEGER,
                        recommendations_count INTEGER,provider TEXT,model TEXT,reasoning TEXT,reason TEXT
                    )"""
                )
                connection.execute(
                    "INSERT INTO improvement_intelligence_runs VALUES(?,?,?,?,?,?,?,?,?)",
                    (AUDIT_ID, "COMPLETE", "https://example.com/", 3, 2, "OPENAI", "gpt-5.6-sol", "LOW", None),
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS standards_service_runs(
                        audit_id TEXT,service_id TEXT,state TEXT,targets_attempted INTEGER,
                        targets_succeeded INTEGER,details_json TEXT
                    )"""
                )
                connection.execute(
                    "INSERT INTO standards_service_runs VALUES(?,?,?,?,?,?)",
                    (
                        AUDIT_ID,
                        "google-search-console",
                        "SUCCESS",
                        2,
                        2,
                        json.dumps({"operations": [{"name": "SITEMAPS", "status": "SUCCESS", "dataset_id": "GSC-1"}]}),
                    ),
                )
        finally:
            connection.close()

        _install_contextual_optional_hooks()
        assert getattr(improvement_runtime.execute_improvement_intelligence, "_rasai_contextual_optional_reuse", False)
        assert getattr(gsc_runtime.collect_configured_search_console, "_rasai_contextual_optional_reuse", False)

        with scope(AUDIT_ID, {"TECHNICAL_AI"}, workspace=workspace):
            reused = improvement_runtime.execute_improvement_intelligence(audit_id=AUDIT_ID, workspace=workspace)
            assert reused.reused is True
            assert reused.status == "COMPLETE"
            gsc = gsc_runtime.collect_configured_search_console(audit_id=AUDIT_ID, workspace=workspace)
            assert gsc["effective_enabled"] is True
            assert gsc["targets_succeeded"] == 2


def test_contextual_environment_does_not_mutate_process_environment(monkeypatch) -> None:
    monkeypatch.setenv("RASAI_TEST_CONTEXT_VALUE", "base")
    assert resolve_environment()["RASAI_TEST_CONTEXT_VALUE"] == "base"
    with override_environment({"RASAI_TEST_CONTEXT_VALUE": "reprocess", "RASAI_ONLY_CONTEXT": "yes"}):
        resolved = resolve_environment()
        assert resolved["RASAI_TEST_CONTEXT_VALUE"] == "reprocess"
        assert resolved["RASAI_ONLY_CONTEXT"] == "yes"
        assert __import__("os").environ["RASAI_TEST_CONTEXT_VALUE"] == "base"
        assert "RASAI_ONLY_CONTEXT" not in __import__("os").environ
    assert resolve_environment()["RASAI_TEST_CONTEXT_VALUE"] == "base"


def test_success_without_persisted_optional_evidence_is_blocked_by_integrity() -> None:
    install_core_integrity()
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        _success_item(workspace, "SEARCH_INTELLIGENCE", LIVE_RECOLLECTION)
        _success_item(workspace, "IMPROVEMENT_INTELLIGENCE")
        _success_item(workspace, "GOOGLE_SEARCH_CONSOLE", LIVE_RECOLLECTION)
        _success_item(workspace, "WEB_PERFORMANCE", LIVE_RECOLLECTION)
        _success_item(workspace, "SYNTHETIC_APDEX", LIVE_RECOLLECTION)
        _success_item(workspace, "EXPERIENCE_APDEX", LIVE_RECOLLECTION)
        _success_item(workspace, "PASSIVE_SECURITY")

        _validate_success_integrity(workspace, AUDIT_ID)

        items = {item.component: item for item in list_work_items(workspace, AUDIT_ID)}
        for component in (
            "SEARCH_INTELLIGENCE",
            "IMPROVEMENT_INTELLIGENCE",
            "GOOGLE_SEARCH_CONSOLE",
            "WEB_PERFORMANCE",
            "SYNTHETIC_APDEX",
            "EXPERIENCE_APDEX",
            "PASSIVE_SECURITY",
        ):
            assert items[component].status == BLOCKED
            assert items[component].retryable is False
            assert items[component].last_error_class == "INTEGRITY"
            assert items[component].last_error_code == "PERSISTED_EVIDENCE_MISSING"
            assert items[component].effective_result_ref == f"{component.casefold()}:effective"


def test_saved_console_search_is_backfilled_into_denominator() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory))
        payload = {
            "settings": {
                "environment": {
                    "RASAI_SERP_MODE": "live",
                    "RASAI_SERP_PROVIDER": "serpapi",
                    "RASAI_SERP_MAX_REQUESTS": "10",
                }
            },
            "search_intelligence": {
                "enabled": True,
                "queries": ["rasai"],
                "depth": 10,
                "region": "RS",
                "device": "mobile",
                "competitive": True,
                "compare_content": True,
                "max_content_pages": 3,
                "content_timeout_seconds": 10.0,
                "content_max_bytes": 2000000,
                "content_max_redirects": 5,
                "ai_competitive": False,
                "ymyl_mode": "AUTO",
            },
        }
        connection = sqlite3.connect(workspace.database)
        try:
            with connection:
                connection.execute(
                    """CREATE TABLE audit_execution_configurations(
                        audit_id TEXT PRIMARY KEY,configuration_json TEXT
                    )"""
                )
                connection.execute(
                    "INSERT INTO audit_execution_configurations VALUES(?,?)",
                    (AUDIT_ID, json.dumps(payload)),
                )
        finally:
            connection.close()

        _backfill_console_search(workspace, AUDIT_ID)

        item = next(item for item in list_work_items(workspace, AUDIT_ID) if item.component == "SEARCH_INTELLIGENCE")
        assert item.status == "REQUESTED_NOT_EXECUTED"
        assert item.required is True
        assert item.configuration["queries"] == ["rasai"]
        assert item.configuration["mode"] == "live"
        assert item.configuration["provider"] == "serpapi"
        assert item.configuration["compare_content"] is True
        assert item.configuration["max_content_pages"] == 3
        assert item.configuration["content_timeout_seconds"] == 10.0
        assert item.configuration["content_max_bytes"] == 2_000_000
        assert item.configuration["content_max_redirects"] == 5
        assert item.configuration["ai_competitive"] is False
        assert item.configuration["ymyl_mode"] == "AUTO"
