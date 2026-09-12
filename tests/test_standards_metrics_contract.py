from __future__ import annotations

from rasai.standards_metrics import ndcg_at_k, precision_at_k, reciprocal_rank
from rasai.standards_runtime import _SERVICE_PAYLOAD_DEFAULTS, _bool_payload
from rasai.standards_saas_runtime import _requested
from rasai.standards_service_registry import (
    CRUX_ENABLED_ENV,
    GSC_ENABLED_ENV,
    GSC_SITE_URL_ENV,
    PAGESPEED_ENABLED_ENV,
    service,
    service_state,
    services,
)


def test_zero_credential_services_are_default_on() -> None:
    env: dict[str, str] = {}
    for service_id in (
        "derived-readiness",
        "retrieval-metrics",
        "open-web-metrics",
        "w3c-validator",
        "mdn-observatory",
    ):
        state = service_state(service(service_id), env)
        assert state["requested"] is True
        assert state["configured"] is True
        assert state["effective_enabled"] is True
        assert state["state"] == "READY"


def test_dataset_service_is_not_configured_until_dataset_exists() -> None:
    state = service_state(service("web-platform-baseline"), {})
    assert state["requested"] is True
    assert state["configured"] is False
    assert state["effective_enabled"] is False
    assert state["state"] == "NOT_CONFIGURED"


def test_credential_services_activate_only_after_required_configuration() -> None:
    pagespeed = service("pagespeed")
    missing = service_state(pagespeed, {})
    assert missing["requested"] is False
    assert missing["effective_enabled"] is False
    assert missing["state"] == "DISABLED"

    configured = service_state(pagespeed, {"RASAI_PAGESPEED_API_KEY": "key"})
    assert configured["requested"] is True
    assert configured["configured"] is True
    assert configured["effective_enabled"] is True
    assert configured["state"] == "READY"

    gsc = service("google-search-console")
    token_only = service_state(gsc, {"RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "token"})
    assert token_only["effective_enabled"] is False
    assert GSC_SITE_URL_ENV in token_only["missing_configuration"]
    gsc_ready = service_state(gsc, {
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "token",
        GSC_SITE_URL_ENV: "sc-domain:example.com",
    })
    assert gsc_ready["state"] == "READY"
    assert gsc_ready["effective_enabled"] is True


def test_credential_saas_defaults_preserve_auto_semantics(monkeypatch) -> None:
    assert _SERVICE_PAYLOAD_DEFAULTS["pagespeed_enabled"] is None
    assert _SERVICE_PAYLOAD_DEFAULTS["crux_enabled"] is None
    assert _SERVICE_PAYLOAD_DEFAULTS["gsc_enabled"] is None
    assert _bool_payload({}, "pagespeed_enabled", None) is None
    assert _bool_payload({"pagespeed_enabled": False}, "pagespeed_enabled", None) is False
    assert _bool_payload({"pagespeed_enabled": True}, "pagespeed_enabled", None) is True

    monkeypatch.setenv("RASAI_PAGESPEED_API_KEY", "key")
    assert _requested({}, "pagespeed_enabled", "pagespeed") is True
    assert _requested({"pagespeed_enabled": None}, "pagespeed_enabled", "pagespeed") is True
    assert _requested({"pagespeed_enabled": False}, "pagespeed_enabled", "pagespeed") is False
    assert _requested({"pagespeed_enabled": True}, "pagespeed_enabled", "pagespeed") is True


def test_explicit_disable_wins_even_with_credentials() -> None:
    pagespeed = service_state(
        service("pagespeed"),
        {"RASAI_PAGESPEED_API_KEY": "key", PAGESPEED_ENABLED_ENV: "false"},
    )
    crux = service_state(
        service("crux"),
        {"RASAI_CRUX_API_KEY": "key", CRUX_ENABLED_ENV: "0"},
    )
    gsc = service_state(
        service("google-search-console"),
        {
            "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "token",
            GSC_SITE_URL_ENV: "sc-domain:example.com",
            GSC_ENABLED_ENV: "false",
        },
    )
    assert pagespeed["state"] == "DISABLED"
    assert crux["state"] == "DISABLED"
    assert gsc["state"] == "DISABLED"
    assert pagespeed["effective_enabled"] is False
    assert crux["effective_enabled"] is False
    assert gsc["effective_enabled"] is False


def test_all_services_have_independent_toggle_and_relation_degree() -> None:
    items = services()
    assert len({item.enabled_env for item in items}) == len(items)
    assert all(1 <= item.relation_degree <= 5 for item in items)
    assert all(item.purpose and item.scopes for item in items)


def test_retrieval_metric_formulas_are_deterministic() -> None:
    grades = [0, 3, 2, 0]
    assert precision_at_k(grades, 4) == 0.5
    assert reciprocal_rank(grades) == 0.5
    assert reciprocal_rank([0, 0, 0]) == 0.0
    value = ndcg_at_k(grades, 4)
    assert value is not None
    assert 0 < value < 1
    assert ndcg_at_k([3, 2, 0, 0], 4) == 1.0
