from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from urllib.error import HTTPError

from rasai.integration_diagnostics import (
    STATUS_AUTHENTICATION_ERROR,
    STATUS_AUTHORIZATION_ERROR,
    STATUS_NOT_CONFIGURED,
    STATUS_TRANSIENT_FAILURE,
    IntegrationDiagnostic,
    configuration_fingerprint,
    get_integration_spec,
    integration_specs,
    load_diagnostics,
    result_currency,
    run_diagnostic,
    save_diagnostic,
)


class _Response:
    def __init__(self, payload: object, status: int = 200) -> None:
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")

    def getcode(self) -> int:
        return self.status

    def read(self, _limit: int = -1) -> bytes:
        return self._raw

    def close(self) -> None:
        return None


def _http_error(status: int, payload: object):
    def opener(request, timeout=0):
        raise HTTPError(
            request.full_url,
            status,
            "error",
            {},
            BytesIO(json.dumps(payload).encode("utf-8")),
        )

    return opener


def test_missing_dependency_does_not_touch_network() -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None

    def forbidden(*_args, **_kwargs):
        raise AssertionError("network must not be called when required configuration is missing")

    result = run_diagnostic(spec, env={}, opener=forbidden)
    assert result.status == STATUS_NOT_CONFIGURED
    assert result.category == "DEPENDENCY"
    assert "OPENAI_API_KEY" in result.detail


def test_http_503_is_transient_not_configuration_error() -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    env = {"OPENAI_API_KEY": "sk-test", "RASAI_OPENAI_MODEL": "gpt-5.6-terra"}
    result = run_diagnostic(
        spec,
        env=env,
        opener=_http_error(503, {"error": {"message": "temporarily unavailable"}}),
    )
    assert result.status == STATUS_TRANSIENT_FAILURE
    assert result.transient is True
    assert result.deterministic is False
    assert result.http_status == 503


def test_http_401_is_authentication_error() -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    env = {"OPENAI_API_KEY": "sk-test", "RASAI_OPENAI_MODEL": "gpt-5.6-terra"}
    result = run_diagnostic(
        spec,
        env=env,
        opener=_http_error(401, {"error": {"message": "invalid api key"}}),
    )
    assert result.status == STATUS_AUTHENTICATION_ERROR
    assert result.deterministic is True
    assert result.transient is False


def test_gsc_valid_oauth_without_configured_property_is_authorization_error() -> None:
    spec = get_integration_spec("service:google-search-console")
    assert spec is not None
    env = {
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "oauth-secret",
        "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL": "sc-domain:expected.example",
    }

    def opener(_request, timeout=0):
        return _Response({"siteEntry": [{"siteUrl": "sc-domain:other.example", "permissionLevel": "siteOwner"}]})

    result = run_diagnostic(spec, env=env, opener=opener)
    assert result.status == STATUS_AUTHORIZATION_ERROR
    assert result.category == "PROPERTY_ACCESS"
    assert "expected.example" in result.detail


def test_persisted_diagnostic_is_invalidated_when_configuration_changes(tmp_path) -> None:
    spec = get_integration_spec("ai:openai")
    assert spec is not None
    env_before = {"OPENAI_API_KEY": "sk-a", "RASAI_OPENAI_MODEL": "gpt-5.6-terra"}
    diagnostic = IntegrationDiagnostic(
        integration_id=spec.id,
        label=spec.label,
        checked_at=datetime.now(timezone.utc).isoformat(),
        status="OPERATIONAL",
        category="OK",
        detail="ok",
        action="none",
        configuration_fingerprint=configuration_fingerprint(spec, env_before),
    )
    save_diagnostic(tmp_path, diagnostic)
    loaded = load_diagnostics(tmp_path)[spec.id]
    assert result_currency(spec, loaded, env_before) == "CURRENT"

    env_after = {"OPENAI_API_KEY": "sk-b", "RASAI_OPENAI_MODEL": "gpt-5.6-terra"}
    assert result_currency(spec, loaded, env_after) == "CONFIG_CHANGED"


def test_catalog_covers_current_ai_serp_and_key_external_services() -> None:
    ids = {item.id for item in integration_specs()}
    assert {
        "ai:openai",
        "ai:deepseek",
        "ai:mimo",
        "ai:xai",
        "ai:qwen",
        "ai:gemini",
        "ai:anthropic",
        "ai:copilot",
        "serp:serpapi",
        "serp:serpapi-bing",
        "serp:zenserp",
        "serp:scrapingdog",
        "service:pagespeed",
        "service:crux",
        "service:crux-history",
        "service:google-search-console",
        "service:microsoft-clarity",
        "service:dynatrace",
    }.issubset(ids)

    clarity = next(item for item in integration_specs() if item.id == "service:microsoft-clarity")
    assert clarity.safe_for_bulk is False
