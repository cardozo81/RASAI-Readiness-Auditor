from __future__ import annotations

from rasai import audit_execution_contract as contract
from rasai.console_config import State
from rasai.console_settings import _known_nonsecret_environment_names, _persisted_environment_values
from rasai.external_observability_console import install as install_external_console
from rasai.external_observability_runtime import install_service_contract as install_external_contract
from rasai.standards_console_runtime import install as install_standards_console
from rasai.standards_runtime import install_pre_context


def _install() -> None:
    install_pre_context()
    install_external_contract()
    install_standards_console()
    install_external_console()


def test_console_persists_controls_but_never_external_secrets(monkeypatch) -> None:
    _install()
    names = set(_known_nonsecret_environment_names())
    for name in (
        "RASAI_CRUX_HISTORY_ENABLED",
        "RASAI_CLARITY_ENABLED",
        "RASAI_CLARITY_DAYS",
        "RASAI_CLARITY_DIMENSIONS",
        "RASAI_COMMON_CRAWL_ENABLED",
        "RASAI_COMMON_CRAWL_MAX_URLS",
        "RASAI_COMMON_CRAWL_INDEX_COUNT",
    ):
        assert name in names
    assert "RASAI_CLARITY_API_TOKEN" not in names
    assert "RASAI_CRUX_API_KEY" not in names

    monkeypatch.setenv("RASAI_CLARITY_ENABLED", "true")
    monkeypatch.setenv("RASAI_CLARITY_DAYS", "2")
    monkeypatch.setenv("RASAI_CLARITY_DIMENSIONS", "URL,Device")
    monkeypatch.setenv("RASAI_COMMON_CRAWL_ENABLED", "false")
    monkeypatch.setenv("RASAI_COMMON_CRAWL_MAX_URLS", "4")
    monkeypatch.setenv("RASAI_CLARITY_API_TOKEN", "never-persist-this")
    monkeypatch.setenv("RASAI_CRUX_API_KEY", "never-persist-this-either")

    values = _persisted_environment_values(State())
    assert values["RASAI_CLARITY_ENABLED"] == "true"
    assert values["RASAI_CLARITY_DAYS"] == "2"
    assert values["RASAI_CLARITY_DIMENSIONS"] == "URL,Device"
    assert values["RASAI_COMMON_CRAWL_ENABLED"] == "false"
    assert values["RASAI_COMMON_CRAWL_MAX_URLS"] == "4"
    assert "RASAI_CLARITY_API_TOKEN" not in values
    assert "RASAI_CRUX_API_KEY" not in values


def test_audit_job_contract_is_secret_free_and_preserves_auto_semantics() -> None:
    _install()
    defaults = contract.audit_job_defaults()
    assert defaults["crux_history_enabled"] is None
    assert defaults["clarity_enabled"] is False
    assert defaults["common_crawl_enabled"] is True
    assert defaults["clarity_days"] == 1
    assert defaults["clarity_dimensions"] == "URL,Device"
    assert defaults["common_crawl_max_urls"] == 3
    assert defaults["common_crawl_index_count"] == 2

    payload = contract.normalize_audit_job_payload(
        {
            "crux_history_enabled": None,
            "clarity_enabled": True,
            "common_crawl_enabled": False,
            "clarity_days": 3,
            "clarity_dimensions": "URL,Device,Country/Region",
            "common_crawl_max_urls": 5,
            "common_crawl_index_count": 4,
        }
    )
    assert payload["clarity_enabled"] is True
    assert payload["clarity_dimensions"] == "URL,Device,Country/Region"

    environment = contract.audit_job_environment_overrides(payload)
    assert "RASAI_CRUX_HISTORY_ENABLED" not in environment
    assert environment["RASAI_CLARITY_ENABLED"] == "true"
    assert environment["RASAI_COMMON_CRAWL_ENABLED"] == "false"
    assert environment["RASAI_CLARITY_DAYS"] == "3"
    assert environment["RASAI_CLARITY_DIMENSIONS"] == "URL,Device,Country/Region"
    assert "RASAI_CLARITY_API_TOKEN" not in environment
    assert "RASAI_CRUX_API_KEY" not in environment
