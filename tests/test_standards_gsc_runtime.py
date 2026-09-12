from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai import standards_gsc_observability_runtime as runtime
from rasai.standards_gsc_contract import _validate_site_url
from rasai.standards_gsc_policy import (
    DEFAULT_GSC_FINAL_DATA_LAG_DAYS,
    DEFAULT_GSC_SEARCH_ANALYTICS_DAYS,
    DEFAULT_GSC_SEARCH_MAX_ROWS,
    final_data_lag_days,
    search_analytics_days,
    search_max_rows,
)
from rasai.standards_saas_runtime import install as install_saas_runtime
from rasai.standards_service_registry import GSC_ENABLED_ENV, GSC_SITE_URL_ENV, service, service_state


def test_gsc_service_requires_token_and_property() -> None:
    item = service("google-search-console")
    assert service_state(item, {})["state"] == "DISABLED"
    token_only = service_state(item, {"RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "secret"})
    assert token_only["state"] == "DISABLED"
    assert token_only["effective_enabled"] is False
    configured = service_state(item, {
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "secret",
        GSC_SITE_URL_ENV: "sc-domain:example.com",
    })
    assert configured["state"] == "READY"
    assert configured["effective_enabled"] is True


def test_gsc_property_and_policy_validation() -> None:
    assert _validate_site_url("sc-domain:example.com") == "sc-domain:example.com"
    assert _validate_site_url("https://example.com/") == "https://example.com/"
    with pytest.raises(ValueError):
        _validate_site_url("example.com")
    assert search_analytics_days(None) == DEFAULT_GSC_SEARCH_ANALYTICS_DAYS
    assert search_analytics_days("0") == 0
    assert search_max_rows(None) == DEFAULT_GSC_SEARCH_MAX_ROWS
    assert final_data_lag_days(None) == DEFAULT_GSC_FINAL_DATA_LAG_DAYS
    with pytest.raises(ValueError):
        search_analytics_days("32")
    with pytest.raises(ValueError):
        search_max_rows("50001")


def test_bounded_gsc_collection_uses_existing_collectors_without_exposing_token(tmp_path: Path, monkeypatch) -> None:
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.executescript(
            """
            CREATE TABLE pages (page_id TEXT PRIMARY KEY,audit_id TEXT,normalized_url TEXT);
            INSERT INTO pages VALUES ('P1','AUD-GSC','https://example.com/a');
            INSERT INTO pages VALUES ('P2','AUD-GSC','https://example.com/b');
            INSERT INTO pages VALUES ('P3','AUD-GSC','https://example.com/c');
            """
        )
        connection.commit()
    finally:
        connection.close()

    calls: dict[str, object] = {}

    def sitemaps(**kwargs):
        calls["sitemaps"] = kwargs
        return "OBS-SITEMAPS"

    def inspection(**kwargs):
        calls["inspection"] = kwargs
        return "OBS-INSPECTION"

    def search(**kwargs):
        calls["search"] = kwargs
        return "OBS-SEARCH"

    monkeypatch.setattr(runtime, "collect_sitemaps", sitemaps)
    monkeypatch.setattr(runtime, "collect_url_inspection", inspection)
    monkeypatch.setattr(runtime, "collect_search_analytics", search)

    workspace = SimpleNamespace(root=tmp_path, database=database)
    result = runtime.collect_configured_search_console(
        audit_id="AUD-GSC",
        workspace=workspace,
        env={
            "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "top-secret-token",
            GSC_SITE_URL_ENV: "sc-domain:example.com",
            "RASAI_STANDARDS_MAX_URLS": "2",
            "RASAI_STANDARDS_TIMEOUT_SECONDS": "15",
            "RASAI_GSC_SEARCH_ANALYTICS_DAYS": "1",
            "RASAI_GSC_SEARCH_MAX_ROWS": "500",
            "RASAI_GSC_FINAL_DATA_LAG_DAYS": "3",
        },
    )

    assert result["collection_state"] == "SUCCESS"
    assert result["errors"] == []
    assert tuple(calls["inspection"]["urls"]) == (
        "https://example.com/a",
        "https://example.com/b",
    )
    assert calls["search"]["max_rows"] == 500
    assert calls["search"]["data_state"] == "final"
    assert date.fromisoformat(calls["search"]["start_date"]) == date.fromisoformat(calls["search"]["end_date"])
    assert "top-secret-token" not in repr(result)
    assert calls["sitemaps"]["access_token"] == "top-secret-token"


def test_saas_job_without_gsc_property_masks_worker_global_property(monkeypatch) -> None:
    monkeypatch.setenv(GSC_SITE_URL_ENV, "sc-domain:wrong-tenant.example")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "worker-secret")
    install_saas_runtime()
    from rasai import audit_execution_contract as contract

    auto = contract.audit_job_environment_overrides({})
    explicit = contract.audit_job_environment_overrides({"gsc_enabled": True})
    disabled = contract.audit_job_environment_overrides({"gsc_enabled": False})

    assert auto[GSC_SITE_URL_ENV] == ""
    assert auto[GSC_ENABLED_ENV] == "false"
    assert explicit[GSC_SITE_URL_ENV] == ""
    assert disabled[GSC_SITE_URL_ENV] == ""


def test_saas_job_property_is_the_only_gsc_property_context(monkeypatch) -> None:
    monkeypatch.setenv(GSC_SITE_URL_ENV, "sc-domain:wrong-tenant.example")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "worker-secret")
    install_saas_runtime()
    from rasai import audit_execution_contract as contract

    overrides = contract.audit_job_environment_overrides({
        "gsc_site_url": "sc-domain:correct.example",
        "gsc_enabled": None,
    })
    assert overrides[GSC_SITE_URL_ENV] == "sc-domain:correct.example"
    assert GSC_ENABLED_ENV not in overrides
