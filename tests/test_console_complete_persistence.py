from __future__ import annotations

from configparser import ConfigParser
import os

from rasai import console_settings
from rasai.console_complete_persistence import install as install_complete_persistence
from rasai.console_config import is_secret
from rasai.console_search_intelligence import SearchConsoleState
from rasai import console_ui_refactor as ui


def _public_nonsecret_names() -> set[str]:
    from rasai import console_provider_environment as facade

    return {
        spec.name
        for spec in facade.refresh_specs()
        if not spec.sensitive and not is_secret(spec.name)
    }


def test_complete_projection_contains_every_public_nonsecret_setting(monkeypatch) -> None:
    ui._install_search_persistence()
    install_complete_persistence()
    from rasai import console_provider_environment as facade

    specs = facade.refresh_specs()
    for spec in specs:
        monkeypatch.delenv(spec.name, raising=False)

    values = console_settings._persisted_environment_values(SearchConsoleState())
    assert set(values) == _public_nonsecret_names()

    # SERP governance defaults must be materialized even when the operator never created
    # an explicit environment override.
    assert values["RASAI_SERP_MODE"]
    assert values["RASAI_SERP_PROVIDER"]
    assert values["RASAI_SERP_MAX_QUERIES"]
    assert values["RASAI_SERP_MAX_REQUESTS"]
    assert values["RASAI_SERP_MAX_DEPTH"]
    assert values["RASAI_SERP_MAX_COMPETITORS"]
    assert values["RASAI_SERP_TIMEOUT_SECONDS"]
    assert values["RASAI_SERP_RETRIES"]
    assert values["RASAI_SERP_MIN_INTERVAL_SECONDS"]

    # RASAI_CONFIG is an optional selector. It is inventoried but must not be synthesized
    # from descriptive/default copy, because defining it changes missing-file semantics.
    assert "RASAI_CONFIG" in values
    assert values["RASAI_CONFIG"] == ""


def test_save_materializes_search_inputs_and_all_safe_environment_settings(tmp_path, monkeypatch) -> None:
    ui._install_search_persistence()
    install_complete_persistence()

    state = SearchConsoleState()
    state.search_queries = ("seguro auto", "seguro residencial")
    state.search_depth = 20
    state.search_region = "Porto Alegre, RS, Brazil"
    state.search_device = "mobile"
    state.search_competitive = True

    monkeypatch.setenv("RASAI_SERP_MAX_REQUESTS", "25")
    monkeypatch.setenv("RASAI_SERPAPI_API_KEY", "secret-serp")
    monkeypatch.setenv("RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN", "secret-gsc")
    monkeypatch.delenv("RASAI_CONFIG", raising=False)

    destination = tmp_path / "rasai-console.ini"
    console_settings.save_console_config(state, destination)

    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(destination, encoding="utf-8")

    assert set(parser["environment"]) == _public_nonsecret_names()
    assert parser.get("environment", "RASAI_SERP_MAX_REQUESTS") == "25"
    assert parser.get("environment", "RASAI_CONFIG") == ""
    assert parser.get("search_intelligence", "queries") == "seguro auto; seguro residencial"
    assert parser.getint("search_intelligence", "depth") == 20
    assert parser.get("search_intelligence", "region") == "Porto Alegre, RS, Brazil"
    assert parser.get("search_intelligence", "device") == "mobile"
    assert parser.getboolean("search_intelligence", "competitive") is True

    assert not parser.has_option("environment", "RASAI_SERPAPI_API_KEY")
    assert not parser.has_option("environment", "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN")
    assert "secret-serp" not in destination.read_text(encoding="utf-8")
    assert "secret-gsc" not in destination.read_text(encoding="utf-8")

    # Loading the generated INI must not turn the optional default TOML into an explicit
    # RASAI_CONFIG override in the current process.
    monkeypatch.delenv("RASAI_CONFIG", raising=False)
    restored = SearchConsoleState()
    console_settings.load_console_config(restored, destination)
    assert "RASAI_CONFIG" not in os.environ
