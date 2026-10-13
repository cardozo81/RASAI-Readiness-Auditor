"""Offline metadata-only inventory gate for every installed EnvironmentSpec."""
from __future__ import annotations

import json
from pathlib import Path

from rasai.console_config import is_secret
from rasai.console_configuration_inventory_523 import inventory, main
from rasai.console_provider_environment import refresh_specs


def test_inventory_has_every_live_env_spec_once_and_never_prints_credentials(tmp_path):
    path = tmp_path / "audit.ini"
    path.write_text(
        "[environment]\n"
        "RASAI_SERP_MAX_REQUESTS=7\n"
        "OPENAI_API_KEY=PAST_SECRET_MUST_NOT_LEAK\n"
        "[synthetic_apdex_experience]\n"
        "architecture=HYDRATED\nprofile_mode=CUSTOM\n",
        encoding="utf-8",
    )
    fake_env = {
        "OPENAI_API_KEY": "ACTIVE_SECRET_MUST_NOT_LEAK",
        "RASAI_SERP_MAX_REQUESTS": "13",
    }
    result = inventory(path=path, environ=fake_env)
    specs = refresh_specs()
    mapped = result["environment_variables"]
    assert result["registry_size"] == len(specs)
    assert len(mapped) == len(specs)
    assert {entry["name"] for entry in mapped} == {spec.name for spec in specs}
    assert all(entry["scope"] and entry["status"] for entry in mapped)
    assert all(entry["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY" for entry in mapped)
    assert all(entry["audit_snapshot"] == "AUD_DEPENDENT_NOT_INFERRED" for entry in mapped)
    for row in mapped:
        assert row["persist_ini"] == (not row["sensitive"])
        if row["sensitive"]:
            assert row["scope"] == "OS_SECRET_OR_SESSION"
        else:
            assert row["scope"] == "INI_AND_SESSION"

    by_name = {entry["name"]: entry for entry in mapped}
    assert by_name["RASAI_SERP_MAX_REQUESTS"]["status"] == "SESSION_OVERRIDES_INI"
    assert by_name["OPENAI_API_KEY"]["status"] == "SECRET_PRESENT"
    typed = {entry["name"]: entry for entry in result["typed_state_fields"]}
    assert typed["synthetic_apdex_experience.architecture"]["ini_present"] is True
    assert typed["synthetic_apdex_experience.profile_mode"]["ini_present"] is True
    assert result["metadata_only"] and not result["values_exposed"]
    assert not result["live_consumers_verified"]
    assert not result["audit_snapshot_coverage_verified"]
    rendered = json.dumps(result, ensure_ascii=False)
    assert "PAST_SECRET_MUST_NOT_LEAK" not in rendered
    assert "ACTIVE_SECRET_MUST_NOT_LEAK" not in rendered
    assert "HYDRATED" not in rendered


def test_execution_intent_is_never_recovered_from_ini_or_secret(tmp_path):
    path = tmp_path / "settings.ini"
    path.write_text(
        "[environment]\nPERPLEXITY_API_KEY = credentials\n"
        "RASAI_PERPLEXITY_ENABLED = true\n"
        "[search_intelligence]\nqueries = teste seguro\n",
        encoding="utf-8",
    )
    result = inventory(
        path=path,
        environ={"PERPLEXITY_API_KEY": "EVEN_MORE_SECRET"},
    )
    inputs = {entry["name"]: entry for entry in result["execution_inputs"]}
    assert inputs["perplexity_queries"]["scope"] == "SESSION_ONLY_EXECUTION_OPT_IN"
    assert inputs["perplexity_search_type"]["scope"] == "SESSION_ONLY_EXECUTION_OPT_IN"
    assert not inputs["perplexity_queries"]["new_audit_consent_inherited"]
    assert inputs["search_intelligence.queries"]["scope"] == "REUSABLE_INI_EXECUTION_INPUT"
    assert "EVEN_MORE_SECRET" not in json.dumps(result)
    assert "credentials" not in json.dumps(result)


def test_cli_prints_only_json_and_has_no_file_writes(tmp_path, capsys):
    ini = tmp_path / "console.ini"
    ini.write_text("[console]\nproject = confidential project\n", encoding="utf-8")
    before = ini.read_bytes()
    assert main(["--ini", str(ini)]) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["contract"] == "RASAI-CONSOLE-CONFIG-INVENTORY-523-1"
    assert "confidential project" not in output
    assert str(tmp_path) not in output
    assert before == ini.read_bytes()


def test_derived_apdex_device_mix_missing_does_not_count_as_lost_setting(tmp_path):
    """Physical inventory from the operator had only device_mix omitted (70/71)."""
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_complete_persistence import install
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai import console_settings

    _install_search_persistence()
    install()
    state = SearchConsoleState()
    state.device = "desktop"
    parser = console_settings._parser_for_state(state)
    parser.remove_option("synthetic_apdex_experience", "device_mix")
    path = tmp_path / "captured.ini"
    with path.open("w", encoding="utf-8") as stream:
        parser.write(stream)
    before = path.read_bytes()

    result = inventory(path=path, environ={})
    coverage = result["typed_ini_coverage"]
    assert coverage["total"] == 71
    assert coverage["present"] == 70
    assert coverage["missing_derived_names"] == [
        "synthetic_apdex_experience.device_mix"
    ]
    assert coverage["missing_non_derived_names"] == []
    assert not coverage["missing_non_derived_is_execution_failure_proven"]
    rows = {row["name"]: row for row in result["typed_state_fields"]}
    assert rows["synthetic_apdex_experience.device_mix"]["scope"] == (
        "DERIVED_FROM_CONSOLE_DEVICE"
    )
    assert rows["synthetic_apdex_experience.device_mix"][
        "missing_ini_is_effective_config_loss"
    ] is False
    assert path.read_bytes() == before


def test_non_derived_absent_ini_field_is_a_gap_not_asserted_runtime_failure(tmp_path):
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_complete_persistence import install
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai import console_settings

    _install_search_persistence()
    install()
    parser = console_settings._parser_for_state(SearchConsoleState())
    parser.remove_option("synthetic_apdex_experience", "architecture")
    path = tmp_path / "incomplete.ini"
    with path.open("w", encoding="utf-8") as stream:
        parser.write(stream)
    result = inventory(path=path, environ={})
    coverage = result["typed_ini_coverage"]
    assert coverage["missing_non_derived_names"] == [
        "synthetic_apdex_experience.architecture"
    ]
    assert coverage["missing_derived_names"] == []
    assert not coverage["missing_non_derived_is_execution_failure_proven"]


def test_absent_file_does_not_fabricate_missing_ini_alerts(tmp_path):
    result = inventory(path=tmp_path / "missing.ini", environ={})
    assert result["file_readable"] is False
    assert result["typed_ini_coverage"]["missing_derived_names"] == []
    assert result["typed_ini_coverage"]["missing_non_derived_names"] == []
