from __future__ import annotations

from rasai.console_config import State
from rasai.console_settings import _known_nonsecret_environment_names, _persisted_environment_values
from rasai.standards_console_runtime import install


def test_standards_toggles_are_exposed_and_persistable_without_secrets(monkeypatch) -> None:
    install()
    names = set(_known_nonsecret_environment_names())
    assert "RASAI_DERIVED_READINESS_METRICS" in names
    assert "RASAI_W3C_VALIDATOR" in names
    assert "RASAI_MDN_OBSERVATORY" in names
    assert "RASAI_PAGESPEED_ENABLED" in names
    assert "RASAI_CRUX_ENABLED" in names
    assert "RASAI_PAGESPEED_API_KEY" not in names
    assert "RASAI_CRUX_API_KEY" not in names

    monkeypatch.setenv("RASAI_W3C_VALIDATOR", "false")
    monkeypatch.setenv("RASAI_PAGESPEED_ENABLED", "false")
    monkeypatch.setenv("RASAI_PAGESPEED_API_KEY", "should-never-be-persisted")
    values = _persisted_environment_values(State())
    assert values["RASAI_W3C_VALIDATOR"] == "false"
    assert values["RASAI_PAGESPEED_ENABLED"] == "false"
    assert "RASAI_PAGESPEED_API_KEY" not in values
