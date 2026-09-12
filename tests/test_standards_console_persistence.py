from __future__ import annotations

from rasai.console_config import State
from rasai.console_settings import _known_nonsecret_environment_names, _persisted_environment_values
from rasai.standards_console_runtime import install


def test_standards_toggles_are_exposed_and_persistable_without_secrets(monkeypatch) -> None:
    install()
    names = set(_known_nonsecret_environment_names())
    assert "RASAI_DERIVED_READINESS_METRICS" in names
    assert "RASAI_W3C_VALIDATOR" in names
    assert "RASAI_W3C_CSS_VALIDATOR" in names
    assert "RASAI_MDN_OBSERVATORY" in names
    assert "RASAI_PAGESPEED_ENABLED" in names
    assert "RASAI_CRUX_ENABLED" in names
    assert "RASAI_GSC_ENABLED" in names
    assert "RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL" in names
    assert "RASAI_GSC_SEARCH_ANALYTICS_DAYS" in names
    assert "RASAI_GSC_SEARCH_MAX_ROWS" in names
    assert "RASAI_GSC_FINAL_DATA_LAG_DAYS" in names
    assert "RASAI_PAGESPEED_API_KEY" not in names
    assert "RASAI_CRUX_API_KEY" not in names
    assert "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN" not in names

    monkeypatch.setenv("RASAI_W3C_VALIDATOR", "false")
    monkeypatch.setenv("RASAI_W3C_CSS_VALIDATOR", "false")
    monkeypatch.setenv("RASAI_PAGESPEED_ENABLED", "false")
    monkeypatch.setenv("RASAI_PAGESPEED_API_KEY", "should-never-be-persisted")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL", "sc-domain:example.com")
    monkeypatch.setenv("RASAI_GSC_SEARCH_ANALYTICS_DAYS", "1")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "should-never-be-persisted")
    values = _persisted_environment_values(State())
    assert values["RASAI_W3C_VALIDATOR"] == "false"
    assert values["RASAI_W3C_CSS_VALIDATOR"] == "false"
    assert values["RASAI_PAGESPEED_ENABLED"] == "false"
    assert values["RASAI_GOOGLE_SEARCH_CONSOLE_SITE_URL"] == "sc-domain:example.com"
    assert values["RASAI_GSC_SEARCH_ANALYTICS_DAYS"] == "1"
    assert "RASAI_PAGESPEED_API_KEY" not in values
    assert "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN" not in values
