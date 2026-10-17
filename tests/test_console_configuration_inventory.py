"""Offline metadata-only inventory gate for every installed EnvironmentSpec."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from rasai.console_config import is_secret
from rasai.console_configuration_inventory import inventory, main
from rasai.console_provider_environment import refresh_specs



def test_apdex_state_survives_save_then_load_in_fresh_python_process(tmp_path):
    """#523: verify an actual interpreter boundary, not only State round trips."""
    from rasai.console_m23 import State
    from rasai.console_settings import save_console_config

    ini = tmp_path / "roundtrip-apdex.ini"
    state = State()
    state.apdex_experience = True
    state.apdex_experience_architecture = "CSR_SPA"
    state.apdex_experience_profile_mode = "CUSTOM"
    state.apdex_experience_kpm = "DOM_INTERACTIVE"
    state.apdex_experience_satisfied = 5.0
    state.apdex_experience_frustrated = 20.0
    save_console_config(state, ini)
    source = ini.read_bytes()

    script = (
        "import json,sys; "
        "from pathlib import Path; "
        "from rasai.console_m23 import State; "
        "from rasai.console_settings import load_console_config; "
        "s=State(); r=load_console_config(s,Path(sys.argv[1])); "
        "print(json.dumps({'architecture':s.apdex_experience_architecture,"
        "'profile_mode':s.apdex_experience_profile_mode,"
        "'kpm':s.apdex_experience_kpm,'satisfied':s.apdex_experience_satisfied,"
        "'frustrated':s.apdex_experience_frustrated,"
        "'perplexity_intent':bool(getattr(s,'perplexity_queries',()))}))"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {
            "RASAI_APDEX_EXPERIENCE_ARCHITECTURE",
            "RASAI_APDEX_EXPERIENCE_PROFILE_MODE",
            "RASAI_APDEX_EXPERIENCE_KPM",
            "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS",
            "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS",
        }
    }
    completed = subprocess.run(
        [sys.executable, "-c", script, str(ini)],
        env=env, capture_output=True, text=True, check=True, timeout=30,
    )
    restored = json.loads(completed.stdout)
    assert restored == {
        "architecture": "CSR_SPA",
        "profile_mode": "CUSTOM",
        "kpm": "DOM_INTERACTIVE",
        "satisfied": 5.0,
        "frustrated": 20.0,
        "perplexity_intent": False,
    }
    assert ini.read_bytes() == source




def test_full_apdex_groups_and_effective_adapter_projection_cross_process(tmp_path):
    """#523: all M23/M25 typed INI values and declared CLI env inputs."""
    from rasai.console_m23 import State
    from rasai.console_settings import (
        _runtime_environment_projection, _state_values, save_console_config,
    )

    state = State()
    state.synthetic_apdex = True
    state.apdex_threshold = 4.5
    state.apdex_samples = 13
    state.apdex_max_attempts = 17
    state.apdex_max_pages = 1
    state.apdex_timeout = 48.0
    state.apdex_delay = 0.25
    state.apdex_concurrency = 2
    state.apdex_experience = True
    state.apdex_experience_architecture = "HYDRATED"
    state.apdex_experience_profile_mode = "CUSTOM"
    state.apdex_experience_session_mode = "warm"
    state.apdex_experience_kpm = "USER_ACTION_DURATION"
    state.apdex_experience_samples = 14
    state.apdex_experience_max_attempts = 17
    state.apdex_experience_max_pages = 1
    state.apdex_experience_satisfied = 4.0
    state.apdex_experience_frustrated = 16.0
    state.apdex_experience_errors = True
    state.apdex_experience_javascript_errors = False
    state.apdex_experience_request_errors = True
    state.apdex_experience_console_errors = False
    state.apdex_experience_javascript_capture = True
    state.apdex_experience_xhr_capture = False
    state.apdex_experience_fetch_capture = True
    state.apdex_experience_console_capture = False
    state.apdex_experience_max_error_details = 18
    state.apdex_experience_error_scope = "first-party"
    state.apdex_experience_settle = 2.75
    state.apdex_experience_delay = 0.25
    state.apdex_experience_concurrency = 2
    state.apdex_dynatrace_import = False

    ini = tmp_path / "isolated-apdex.ini"
    before_env = os.environ.copy()
    try:
        save_console_config(state, ini)
        expected_typed = {
            section: _state_values(state)[section]
            for section in ("synthetic_apdex", "synthetic_apdex_experience")
        }
        expected_projection = {
            key: value for key, value in _runtime_environment_projection(state).items()
            if key == "RASAI_SYNTHETIC_APDEX" or key.startswith("RASAI_APDEX_")
        }
        source_bytes = ini.read_bytes()
        child_code = (
            "import json,sys;from pathlib import Path;"
            "from rasai.console_m23 import State;"
            "from rasai.console_settings import load_console_config,"
            "_state_values,_runtime_environment_projection;"
            "s=State();load_console_config(s,Path(sys.argv[1]));"
            "p=_runtime_environment_projection(s);"
            "print(json.dumps({'typed':{k:_state_values(s)[k] for k in "
            "('synthetic_apdex','synthetic_apdex_experience')},"
            "'projection':{k:v for k,v in p.items() if k=='RASAI_SYNTHETIC_APDEX'"
            " or k.startswith('RASAI_APDEX_')},"
            "'perplexity_intent':bool(getattr(s,'perplexity_queries',()))}))"
        )
        child_env = {
            k: v for k, v in before_env.items()
            if k != "RASAI_SYNTHETIC_APDEX"
            and not k.startswith(("RASAI_APDEX_", "RASAI_DYNATRACE_"))
        }
        completed = subprocess.run(
            [sys.executable, "-c", child_code, str(ini)],
            env=child_env, check=True, capture_output=True, text=True, timeout=30,
        )
        restored = json.loads(completed.stdout)
        assert restored["typed"] == expected_typed
        assert restored["projection"] == expected_projection
        assert restored["perplexity_intent"] is False
        assert ini.read_bytes() == source_bytes
    finally:
        os.environ.clear()
        os.environ.update(before_env)



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
    assert by_name["RASAI_SERP_MAX_REQUESTS"]["status"] == (
        "SESSION_DIFFERS_FROM_INI_EFFECTIVE_PRIORITY_UNVERIFIED"
    )
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
    """Device mix is the sole derived field absent from a generated inventory."""
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
    expected_count = sum(len(values) for values in console_settings._state_values(state).values())
    assert coverage["total"] == expected_count
    assert coverage["present"] == expected_count - 1
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


def test_optional_apdex_preflight_checks_real_m23_m25_without_starting_aud(tmp_path):
    from unittest.mock import patch
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    from rasai import console_settings

    _install_search_persistence()
    install()
    ini = tmp_path / "effective.ini"
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.device = "desktop"
        state.synthetic_apdex = True
        state.apdex_threshold = 2.1
        state.apdex_samples = 5
        state.apdex_max_attempts = 8
        state.apdex_timeout = 48.0
        state.apdex_delay = 1.25
        state.apdex_concurrency = 2
        state.apdex_experience = True
        state.apdex_experience_samples = 7
        state.apdex_experience_max_attempts = 10
        state.apdex_experience_kpm = "USER_ACTION_DURATION"
        state.apdex_experience_satisfied = 2.5
        state.apdex_experience_frustrated = 9.0
        state.apdex_experience_xhr_capture = False
        state.apdex_experience_fetch_capture = True
        console_settings.save_console_config(state, ini)
        before = ini.read_bytes()
        before_env = dict(os.environ)

        outcome = inspect_apdex_consumers(ini, environ={})
        assert outcome["status"] == "ADAPTERS_VALIDATED_OFFLINE"
        assert outcome["active_m23"] is True
        assert outcome["active_m25"] is True
        assert outcome["single_device_enforced"] is True
        assert outcome["load_warning_count"] == 0
        assert outcome["external_requests"] == outcome["audit_writes"] == 0
        assert outcome["values_exposed"] is False
        assert outcome["collector_execution_verified"] is False
        assert outcome["dynatrace_live_verified"] is False
        assert os.environ == before_env
        assert ini.read_bytes() == before
        assert main(["--ini", str(ini), "--verify-apdex"]) == 0
        # The CLI normally produces JSON; this call never modifies operator input.
        assert ini.read_bytes() == before


def test_apdex_preflight_missing_source_never_creates_file(tmp_path):
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    ini = tmp_path / "no-config.ini"
    result = inspect_apdex_consumers(ini)
    assert result["status"] == "SOURCE_UNAVAILABLE"
    assert result["active_m23"] is None
    assert result["audit_writes"] == result["external_requests"] == 0
    assert not ini.exists()


def test_apdex_preflight_rejects_bad_operator_apdex_without_echoing_values(tmp_path):
    from unittest.mock import patch
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    from rasai import console_settings
    _install_search_persistence()
    install()
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.synthetic_apdex = True
        state.apdex_threshold = 2.0
        ini = tmp_path / "bad-apdex.ini"
        console_settings.save_console_config(state, ini)
        from configparser import ConfigParser
        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ini, encoding="utf-8")
        parser.set("synthetic_apdex", "threshold_seconds", "invalid-value")
        with ini.open("w", encoding="utf-8") as stream:
            parser.write(stream)
        before = ini.read_bytes()
        outcome = inspect_apdex_consumers(ini, environ={})
        assert outcome["status"] in {
            "ADAPTERS_PARTIAL_LOAD_WARNINGS", "CONFIG_OR_ADAPTER_INVALID"
        }
        assert "invalid-value" not in json.dumps(outcome)
        assert ini.read_bytes() == before


def test_apdex_readonly_preflight_preserves_existing_m25_handoff_even_on_error(tmp_path):
    """An offline inspection cannot cancel a pending production M25 task."""
    from unittest.mock import patch
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    from rasai.m25_apdex_experience import ExperienceApdexConfig
    from rasai.m25_runtime import peek_pending_config, set_pending_config
    from rasai import console_settings

    _install_search_persistence()
    install()
    path = tmp_path / "persisted.ini"
    with patch.dict(os.environ, {}, clear=True):
        state = SearchConsoleState()
        state.device = "mobile"
        state.apdex_experience = True
        state.apdex_experience_samples = 7
        state.apdex_experience_max_attempts = 10
        console_settings.save_console_config(state, path)
        source_bytes = path.read_bytes()

        original = peek_pending_config()
        real_pending = ExperienceApdexConfig(
            enabled=True,
            target_samples_per_page=9,
            max_attempts_per_page=13,
            device_mix=(("DESKTOP", 100.0),),
            satisfied_threshold_seconds=2.0,
            frustrated_threshold_seconds=8.0,
        )
        set_pending_config(real_pending)
        try:
            assert peek_pending_config() is real_pending
            success = inspect_apdex_consumers(path, environ={})
            assert success["status"] == "ADAPTERS_VALIDATED_OFFLINE"
            assert success["active_m25"] is True
            assert peek_pending_config() is real_pending

            missing = inspect_apdex_consumers(tmp_path / "missing.ini", environ={})
            assert missing["status"] == "SOURCE_UNAVAILABLE"
            assert peek_pending_config() is real_pending

            broken = tmp_path / "broken.ini"
            broken.write_bytes(b"[broken invalid ini")
            invalid = inspect_apdex_consumers(broken, environ={})
            assert invalid["status"] == "CONFIG_OR_ADAPTER_INVALID"
            assert peek_pending_config() is real_pending
            assert path.read_bytes() == source_bytes
        finally:
            set_pending_config(original)


def test_apdex_preflight_does_not_call_shared_m25_setter(tmp_path, monkeypatch):
    """The adapter still executes, but its one-shot write is locally captured."""
    from unittest.mock import patch
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    from rasai import console_settings, m25_runtime

    _install_search_persistence()
    install()
    with patch.dict(os.environ, {}, clear=True):
        path = tmp_path / "fresh.ini"
        state = SearchConsoleState()
        state.apdex_experience = True
        console_settings.save_console_config(state, path)
        def reject_shared_set(_config):
            raise AssertionError("inspector must never write process-global M25 pending state")
        monkeypatch.setattr(m25_runtime, "set_pending_config", reject_shared_set)
        response = inspect_apdex_consumers(path, environ={})
        assert response["status"] == "ADAPTERS_VALIDATED_OFFLINE"
        assert response["active_m25"] is True


def test_all_registry_variables_have_explicit_nonclaiming_adapter_affinity(tmp_path):
    """Source CLI constants are navigational hints, not executed-consumer proof."""
    from rasai import m23_cli, m25_cli
    from rasai.console_configuration_inventory import _declared_apdex_consumer_surface

    hints = _declared_apdex_consumer_surface()
    assert set(m25_cli.M25_ENV_NAMES).issubset(hints)
    assert set(m23_cli.profile_environment_names()).issubset(hints)
    assert hints["RASAI_APDEX_THRESHOLD_SECONDS"] == (
        "M23_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF"
    )
    assert hints["RASAI_APDEX_EXPERIENCE_KPM"] == (
        "M25_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF"
    )
    assert hints["RASAI_APDEX_EXPERIENCE_ARCHITECTURE"] == (
        "CAT07_DECLARATIVE_INPUT_NOT_M25_MEASUREMENT"
    )
    assert hints["RASAI_APDEX_EXPERIENCE_PROFILE_MODE"] == (
        "CAT07_DECLARATIVE_INPUT_NOT_M25_MEASUREMENT"
    )
    assert hints["RASAI_APDEX_EXPERIENCE_DEVICE_MIX"] == (
        "INERT_DEVICE_MIX_DERIVED_FROM_CONSOLE_DEVICE"
    )

    ini = tmp_path / "operator.ini"
    ini.write_text("[environment]\nOPENAI_API_KEY = SHOULD_NOT_LEAK\n", encoding="utf-8")
    result = inventory(path=ini, environ={"OPENAI_API_KEY": "SECRET_TEST"})
    rows = result["environment_variables"]
    assert len(rows) == result["registry_size"] == len(refresh_specs())
    assert all(row["declared_adapter_surface"] for row in rows)
    assert all(row["declared_adapter_surface_is_execution_proof"] is False for row in rows)
    assert all(row["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY" for row in rows)
    coverage = result["apdex_adapter_surface_coverage"]
    assert coverage["mapped_registry_variables"] + coverage["unmapped_registry_variables"] == len(rows)
    assert coverage["mapped_registry_variables"] > 0
    assert coverage["unmapped_registry_variables"] > 0
    assert coverage["execution_or_aud_snapshot_coverage_proven"] is False
    as_rows = {row["name"]: row for row in rows}
    assert as_rows["RASAI_APDEX_THRESHOLD_SECONDS"]["declared_adapter_surface"] == (
        "M23_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF"
    )
    assert as_rows["RASAI_APDEX_EXPERIENCE_ARCHITECTURE"]["declared_adapter_surface"] == (
        "CAT07_DECLARATIVE_INPUT_NOT_M25_MEASUREMENT"
    )
    # The inert historical device mix is intentionally absent from the
    # live EnvironmentSpec registry, not a lost execution setting.
    assert "RASAI_APDEX_EXPERIENCE_DEVICE_MIX" not in as_rows
    assert as_rows["OPENAI_API_KEY"]["declared_adapter_surface"] == (
        "NOT_MAPPED_NO_CONSUMER_INFERENCE"
    )
    rendered = json.dumps(result)
    assert "SHOULD_NOT_LEAK" not in rendered
    assert "SECRET_TEST" not in rendered
    assert ini.read_text(encoding="utf-8").endswith("SHOULD_NOT_LEAK\n")


def test_ini_inventory_reports_physical_source_condition_without_disclosing_values(tmp_path):
    from rasai.console_configuration_inventory import inventory

    missing = inventory(path=tmp_path / "never-created.ini", environ={})
    assert missing["ini_source_status"] == "SOURCE_NOT_FOUND_OR_NOT_A_FILE"
    assert missing["file_readable"] is False
    assert missing["typed_ini_coverage"]["missing_non_derived_names"] == []

    invalid = tmp_path / "invalid.ini"
    invalid.write_text("[broken secret\npassword=MUST_NOT_LEAK", encoding="utf-8")
    result = inventory(path=invalid, environ={})
    assert result["ini_source_status"] == "SOURCE_INVALID_INI"
    assert result["file_readable"] is False
    assert "MUST_NOT_LEAK" not in json.dumps(result)

    oversized = tmp_path / "oversized.ini"
    oversized.write_bytes(b"[environment]\n" + b"X" * 2_000_000)
    large = inventory(path=oversized, environ={})
    assert large["ini_source_status"] == "SOURCE_TOO_LARGE"
    assert large["file_readable"] is False

    good = tmp_path / "good.ini"
    good.write_text("[environment]\nOPENAI_API_KEY=MUST_STAY_SECRET\n", encoding="utf-8")
    ok = inventory(path=good, environ={})
    assert ok["ini_source_status"] == "SOURCE_PARSED_NO_RUNTIME_CONSUMER_PROOF"
    assert ok["file_readable"] is True
    assert ok["ini_source_status_is_execution_proof"] is False
    assert "MUST_STAY_SECRET" not in json.dumps(ok)


def test_ini_inventory_abstains_if_file_changes_while_opening(tmp_path, monkeypatch):
    """A mutable INI is not a reliable source for a metadata inventory."""
    from rasai.console_configuration_inventory import inventory

    operator_ini = tmp_path / "operator.ini"
    operator_ini.write_text(
        "[environment]\nRASAI_SERP_MAX_REQUESTS=7\n"
        "OPENAI_API_KEY=ABSOLUTELY_NOT_TO_LEAK\n", encoding="utf-8"
    )
    original_open = Path.open
    appended = []

    def racing_open(self, mode="r", *args, **kwargs):
        if self == operator_ini and mode == "rb" and not appended:
            with original_open(self, "ab") as stream:
                stream.write(b"RASAI_PERPLEXITY_ENABLED=true\n")
            appended.append(True)
        return original_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", racing_open)
    response = inventory(path=operator_ini, environ={})
    assert appended
    assert response["ini_source_status"] == "SOURCE_CHANGED_DURING_READ"
    assert response["file_readable"] is False
    assert response["typed_ini_coverage"]["missing_non_derived_names"] == []
    assert "ABSOLUTELY_NOT_TO_LEAK" not in json.dumps(response)


def test_ini_inventory_refuses_symlinked_file_without_following_target(tmp_path):
    from rasai.console_configuration_inventory import inventory

    target = tmp_path / "private.ini"
    target.write_text(
        "[environment]\nOPENAI_API_KEY=TARGET_SECRET_NEVER_EMITTED\n",
        encoding="utf-8",
    )
    link = tmp_path / "operator.ini"
    import pytest
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink not permitted by platform: {exc}")
    data = inventory(path=link, environ={})
    assert data["ini_source_status"] == "SOURCE_SYMLINK_DISALLOWED"
    assert data["file_readable"] is False
    assert "TARGET_SECRET_NEVER_EMITTED" not in json.dumps(data)
    assert target.is_file()


def test_search_affinity_is_source_declared_and_never_claims_live_execution(
    tmp_path, monkeypatch,
):
    """SERP config inputs and Perplexity opt-in are never provider telemetry."""
    from rasai.search_intelligence.config import (
        SERP_ENV_NAMES, SERP_PROVIDER_KEY_ENVS,
    )
    from rasai.search_intelligence.perplexity import API_KEY_ENV
    from rasai.console_perplexity_readiness import _FILTERS
    from rasai.console_configuration_inventory import (
        _declared_search_consumer_surface,
    )
    from urllib import request

    monkeypatch.setattr(
        request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("metadata inventory may not contact a provider")
        ),
    )
    surface = _declared_search_consumer_surface()
    assert set(SERP_ENV_NAMES) <= set(surface)
    assert all(
        surface[key] == "SERP_PROVIDER_SECRET_DECLARED_NOT_REQUEST_PROOF"
        for key in SERP_PROVIDER_KEY_ENVS
    )
    assert all(
        surface[key] == "SERP_CONFIG_INPUT_DECLARED_NOT_REQUEST_PROOF"
        for key in set(SERP_ENV_NAMES) - set(SERP_PROVIDER_KEY_ENVS)
    )
    assert surface[API_KEY_ENV] == "PERPLEXITY_KEY_READINESS_NOT_REQUEST_CONSENT"
    assert surface["RASAI_PERPLEXITY_ENABLED"] == (
        "PERPLEXITY_ACTIVATION_READINESS_NOT_PER_AUD_CONSENT"
    )
    assert set(_FILTERS) <= set(surface)

    filename = tmp_path / "operator.ini"
    filename.write_text(
        "[environment]\n"
        "RASAI_SERP_MAX_REQUESTS = 7\n"
        "RASAI_PERPLEXITY_ENABLED = true\n"
        "PERPLEXITY_API_KEY = SECRET_IN_INI_MUST_NOT_LEAK\n",
        encoding="utf-8",
    )
    before = filename.read_bytes()
    report = inventory(path=filename, environ={
        "PERPLEXITY_API_KEY": "ACTIVE_KEY_MUST_NOT_LEAK",
        "RASAI_SERP_MAX_REQUESTS": "12",
    })
    rows = {row["name"]: row for row in report["environment_variables"]}
    assert rows["RASAI_SERP_MAX_REQUESTS"]["declared_adapter_surface"] == (
        "SERP_CONFIG_INPUT_DECLARED_NOT_REQUEST_PROOF"
    )
    assert rows["RASAI_PERPLEXITY_ENABLED"]["declared_adapter_surface"] == (
        "PERPLEXITY_ACTIVATION_READINESS_NOT_PER_AUD_CONSENT"
    )
    assert rows[API_KEY_ENV]["declared_adapter_surface"] == (
        "PERPLEXITY_KEY_READINESS_NOT_REQUEST_CONSENT"
    )
    assert rows[API_KEY_ENV]["sensitive"] is True
    assert rows[API_KEY_ENV]["persist_ini"] is False
    assert rows[API_KEY_ENV]["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY"
    assert rows["RASAI_PERPLEXITY_ENABLED"]["runtime_consumer"] == (
        "NOT_PROVEN_BY_REGISTRY"
    )
    assert report["search_adapter_surface_coverage"][
        "mapped_registry_variables"
    ] > 0
    assert (
        report["search_adapter_surface_coverage"]["mapped_registry_variables"]
        + report["search_adapter_surface_coverage"]["unmapped_registry_variables"]
        == report["registry_size"]
    )
    assert report["search_adapter_surface_coverage"][
        "real_provider_request_coverage_proven"
    ] is False
    assert report["search_adapter_surface_coverage"][
        "per_aud_provider_consent_proven"
    ] is False
    assert report["execution_inputs"][1]["new_audit_consent_inherited"] is False
    assert report["metadata_only"] is True
    assert filename.read_bytes() == before
    rendered = json.dumps(report)
    assert "SECRET_IN_INI_MUST_NOT_LEAK" not in rendered
    assert "ACTIVE_KEY_MUST_NOT_LEAK" not in rendered


def test_gsc_affinity_is_code_declaration_not_property_or_oauth_proof(
    tmp_path, monkeypatch,
):
    """Audit GSC source constants but never refresh tokens or query an API."""
    from rasai import gsc_scope, gsc_oauth, standards_gsc_policy
    from rasai.console_configuration_inventory import (
        _declared_gsc_consumer_surface,
    )

    monkeypatch.setattr(
        gsc_oauth, "resolve_access_token",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("inventory may not resolve OAuth tokens")
        ),
    )
    hints = _declared_gsc_consumer_surface()
    assert hints[gsc_scope.GSC_ENABLED_ENV] == (
        "GSC_SCOPE_DECLARED_NOT_PROPERTY_OR_API_PROOF"
    )
    assert hints[gsc_scope.GSC_SITE_URL_ENV] == (
        "GSC_SCOPE_DECLARED_NOT_PROPERTY_OR_API_PROOF"
    )
    for secret in (
        gsc_oauth.ACCESS_TOKEN_ENV, gsc_oauth.CLIENT_SECRET_ENV,
        gsc_oauth.REFRESH_TOKEN_ENV,
    ):
        assert hints[secret] == (
            "GSC_OAUTH_INPUT_DECLARED_NOT_AUTHENTICATION_PROOF"
        )
    assert hints[standards_gsc_policy.GSC_SEARCH_MAX_ROWS_ENV] == (
        "GSC_ANALYTICS_POLICY_DECLARED_NOT_DATA_FINALITY_PROOF"
    )
    target = tmp_path / "gsc.ini"
    target.write_text(
        "[environment]\n"
        "RASAI_GSC_ENABLED = true\n"
        "RASAI_GSC_SEARCH_MAX_ROWS = 100\n"
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN = OLD_OAUTH_SECRET\n",
        encoding="utf-8",
    )
    previous = target.read_bytes()
    report = inventory(path=target, environ={
        "RASAI_GOOGLE_SEARCH_CONSOLE_ACCESS_TOKEN": "NEW_OAUTH_SECRET",
    })
    by_name = {r["name"]: r for r in report["environment_variables"]}
    assert by_name[gsc_scope.GSC_ENABLED_ENV]["declared_adapter_surface"] == (
        "GSC_SCOPE_DECLARED_NOT_PROPERTY_OR_API_PROOF"
    )
    assert by_name[gsc_oauth.ACCESS_TOKEN_ENV]["declared_adapter_surface"] == (
        "GSC_OAUTH_INPUT_DECLARED_NOT_AUTHENTICATION_PROOF"
    )
    assert by_name[gsc_oauth.ACCESS_TOKEN_ENV]["runtime_consumer"] == (
        "NOT_PROVEN_BY_REGISTRY"
    )
    assert by_name[gsc_oauth.ACCESS_TOKEN_ENV]["persist_ini"] is False
    coverage = report["gsc_adapter_surface_coverage"]
    assert coverage["mapped_registry_variables"] > 0
    assert coverage["mapped_registry_variables"] + coverage[
        "unmapped_registry_variables"
    ] == report["registry_size"]
    assert coverage["authenticated_property_coverage_proven"] is False
    assert coverage["actual_gsc_api_read_coverage_proven"] is False
    assert report["metadata_only"] is True
    assert target.read_bytes() == previous
    rendered = json.dumps(report)
    assert "OLD_OAUTH_SECRET" not in rendered
    assert "NEW_OAUTH_SECRET" not in rendered


def test_inventory_posix_same_size_rewrite_with_restored_mtime_abstains(
    tmp_path, monkeypatch,
):
    """#523: metadata inventory may not certify in-place edited INI as sealed."""
    import pytest

    if os.name == "nt":
        pytest.skip("Windows creation time is not POSIX ctime")

    operator_ini = tmp_path / "operator.ini"
    original = (
        b"[environment]\nRASAI_SERP_MAX_REQUESTS=7\n"
        b"OPENAI_API_KEY=SECRET_NOT_IN_REPORT\n"
    )
    operator_ini.write_bytes(original)
    original_stat = operator_ini.stat()
    real_open = Path.open
    rewritten = []

    def rewrite_after_first_open(self, mode="r", *args, **kwargs):
        stream = real_open(self, mode, *args, **kwargs)
        if self == operator_ini and mode == "rb" and not rewritten:
            with real_open(self, "r+b") as writer:
                writer.seek(original.index(b"RASAI_SERP_MAX_REQUESTS=7"))
                writer.write(b"RASAI_SERP_MAX_REQUESTS=8")
            os.utime(
                operator_ini,
                ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
            )
            rewritten.append(True)
        return stream

    monkeypatch.setattr(Path, "open", rewrite_after_first_open)
    report = inventory(path=operator_ini, environ={})
    assert rewritten == [True]
    after = operator_ini.stat()
    assert after.st_size == original_stat.st_size
    assert after.st_mtime_ns == original_stat.st_mtime_ns
    assert after.st_ctime_ns != original_stat.st_ctime_ns
    assert report["ini_source_status"] == "SOURCE_CHANGED_DURING_READ"
    assert report["file_readable"] is False
    assert report["typed_ini_coverage"]["missing_non_derived_names"] == []
    assert "SECRET_NOT_IN_REPORT" not in json.dumps(report)
    assert b"RASAI_SERP_MAX_REQUESTS=8" in operator_ini.read_bytes()


def test_523_core_console_runtime_input_affinity_is_static_and_safe(
    tmp_path, monkeypatch,
):
    """Real bootstrap keys are inventoried, never misreported as used by M21/AI."""
    import socket
    from rasai import console_config as core
    from rasai.console_configuration_inventory import (
        _declared_console_core_surface,
    )

    core_map = _declared_console_core_surface()
    assert all(key.startswith("RASAI_") for key in core_map)
    assert core.AI_TIMEOUT_ENV in core_map
    assert core.AI_MAX_CYCLES_ENV in core_map
    assert core.AI_CYCLE_DELAY_ENV in core_map
    assert core.WEB_PERFORMANCE_TIMEOUT_ENV in core_map
    assert set(core.CONTENT_CONTEXT_ENV_NAMES).issubset(core_map)
    assert core_map["RASAI_DEVICE_CONTEXT"] == (
        "CONSOLE_DEVICE_INPUT_NOT_EXECUTION_PROOF"
    )
    assert core_map["RASAI_WEB_PERFORMANCE"] == (
        "CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF"
    )
    assert core_map["RASAI_AI_CONTENT_REMEDIATION"] == (
        "CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF"
    )
    assert "OPENAI_API_KEY" not in core_map  # No provider consent inference.

    session = {
        "RASAI_DEVICE_CONTEXT": "desktop",
        "RASAI_WEB_PERFORMANCE": "true",
        "RASAI_WEB_PERFORMANCE_MAX_PAGES": "2",
        "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": "crux",
        core.WEB_PERFORMANCE_TIMEOUT_ENV: "33",
        core.AI_TIMEOUT_ENV: "127",
        core.AI_MAX_CYCLES_ENV: "2",
        core.AI_CYCLE_DELAY_ENV: "0.5",
        "OPENAI_API_KEY": "NEVER_ECHO_CORE_API_KEY_523",
    }
    # Confirm the fields are genuinely recognized by the existing
    # parser; do not call any runtime engine or provider.
    state = core.State()
    assert core.apply_environment_defaults(
        state, env=session, names=set(session),
    ) == ()
    assert state.device == "desktop"
    assert state.web_performance is True
    assert state.web_max_pages == 2
    assert state.field_source == "crux"
    assert state.ai_timeout == 127

    def no_network(*_args, **_kwargs):
        raise AssertionError("inventory may not establish live provider use")
    monkeypatch.setattr(socket, "create_connection", no_network)
    source = tmp_path / "core-configuration.ini"
    source.write_text(
        "[environment]\nRASAI_WEB_PERFORMANCE=true\n"
        "OPENAI_API_KEY=SHOULD_NOT_BE_IN_OUTPUT\n",
        encoding="utf-8",
    )
    original = source.read_bytes()
    report = inventory(path=source, environ=session)
    coverage = report["console_core_adapter_surface_coverage"]
    assert coverage["source"] == (
        "CONSOLE_CONFIG_APPLY_ENVIRONMENT_DEFAULTS_DECLARATIONS"
    )
    assert coverage["mapped_registry_variables"] > 0
    assert (
        coverage["mapped_registry_variables"]
        + coverage["unmapped_registry_variables"]
    ) == report["registry_size"]
    assert coverage["runtime_device_or_provider_execution_proven"] is False
    assert coverage["actual_web_performance_or_ai_usage_proven"] is False
    rows = {r["name"]: r for r in report["environment_variables"]}
    for key in core_map:
        if key in rows:
            assert rows[key]["declared_adapter_surface"] == core_map[key]
            assert rows[key]["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY"
            assert rows[key]["declared_adapter_surface_is_execution_proof"] is False
    assert rows["OPENAI_API_KEY"]["sensitive"] is True
    assert "NEVER_ECHO_CORE_API_KEY_523" not in json.dumps(report)
    assert "SHOULD_NOT_BE_IN_OUTPUT" not in json.dumps(report)
    assert source.read_bytes() == original

def test_apdex_preflight_rejects_identical_byte_inode_swap(tmp_path, monkeypatch):
    """An INI swapped *during* read cannot be certified by its SHA alone."""
    import pytest
    from unittest.mock import patch
    from rasai import console_settings
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers

    if os.name == "nt":
        pytest.skip("Windows can forbid os.replace while file descriptor is open")
    _install_search_persistence()
    install()
    candidate = tmp_path / "apdex.ini"
    replacement = tmp_path / "replacement.ini"
    with patch.dict(os.environ, {}, clear=True):
        console_settings.save_console_config(SearchConsoleState(), candidate)
        initial = candidate.read_bytes()
        replacement.write_bytes(initial)
        original_open = Path.open
        swapped = [False]

        def replace_after_open(self, *args, **kwargs):
            stream = original_open(self, *args, **kwargs)
            if self == candidate and args and args[0] == "rb" and not swapped[0]:
                os.replace(replacement, candidate)
                swapped[0] = True
            return stream

        monkeypatch.setattr(Path, "open", replace_after_open)
        outcome = inspect_apdex_consumers(candidate, environ={})
        assert swapped[0]
        assert outcome["status"] == "SOURCE_CHANGED"
        assert candidate.read_bytes() == initial
        assert outcome["audit_writes"] == outcome["external_requests"] == 0


def test_apdex_preflight_rejects_same_content_swap_after_adapter(tmp_path, monkeypatch):
    """Even after a clean initial read, a new inode invalidates the result."""
    import pytest
    from unittest.mock import patch
    from rasai import console_settings, m23_cli
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers

    if os.name == "nt":
        pytest.skip("POSIX-only source replacement scenario")
    _install_search_persistence()
    install()
    candidate = tmp_path / "apdex.ini"
    replacement = tmp_path / "replacement.ini"
    with patch.dict(os.environ, {}, clear=True):
        console_settings.save_console_config(SearchConsoleState(), candidate)
        original_bytes = candidate.read_bytes()
        replacement.write_bytes(original_bytes)
        original_adapter = m23_cli.configured_apdex
        swapped = [False]

        def adapter_then_swap(*args, **kwargs):
            result = original_adapter(*args, **kwargs)
            if not swapped[0]:
                os.replace(replacement, candidate)
                swapped[0] = True
            return result

        monkeypatch.setattr(m23_cli, "configured_apdex", adapter_then_swap)
        outcome = inspect_apdex_consumers(candidate, environ={})
        assert swapped[0]
        assert outcome["status"] == "SOURCE_CHANGED"
        assert candidate.read_bytes() == original_bytes
        assert outcome["audit_writes"] == outcome["external_requests"] == 0


def test_apdex_preflight_rejects_descriptor_identity_mismatch_cross_platform(tmp_path):
    """Stat versus fstat mismatch must be fail-closed on Linux and Windows."""
    from types import SimpleNamespace
    from unittest.mock import patch
    from rasai import console_apdex_effective_validation as inspector

    candidate = tmp_path / "operator.ini"
    candidate.write_bytes(b"[environment]\\n")
    original_fstat = os.fstat

    def wrong_inode(fd):
        source = original_fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        values = {key: getattr(source, key) for key in fields}
        values["st_ino"] += 1
        return SimpleNamespace(**values)

    with patch.object(inspector.os, "fstat", wrong_inode):
        contents, identity, status = inspector._verified_source(candidate)
    assert contents is None and identity is None
    assert status == "SOURCE_CHANGED"
    assert candidate.read_bytes() == b"[environment]\\n"



def test_apdex_load_warning_categories_are_sanitized_and_exhaustive():
    from rasai.console_apdex_effective_validation import _classify_load_warnings

    warnings = [
        "environment.NOT_A_REAL_VAR: variável não reconhecida ou não persistível",
        "console.device: invalid sensitive candidate",
        "RASAI_PRESENTATION_TIMEZONE: invalid private timezone",
        "não foi possível ler C:/sensitive/operator.ini: ConfigError",
        "unrecognized private diagnostic data",
    ]
    classified = _classify_load_warnings(warnings)
    assert classified == {
        "unknown_or_nonpersistible_environment": 1,
        "invalid_typed_state": 1,
        "invalid_presentation_timezone": 1,
        "unreadable_ini": 1,
        "other_unclassified": 1,
    }
    assert sum(classified.values()) == len(warnings)
    assert not any("sensitive" in str(value) or "NOT_A_REAL_VAR" in str(value)
                   for value in classified.values())


def test_apdex_load_warning_categories_empty():
    from rasai.console_apdex_effective_validation import _classify_load_warnings
    assert sum(_classify_load_warnings([]).values()) == 0


def test_rejected_environment_warning_reasons_are_non_disclosing():
    from rasai.console_apdex_effective_validation import (
        _classify_environment_warning_reasons,
    )

    warnings = [
        "environment.OPENAI_API_KEY: variável não reconhecida ou não persistível",
        "environment.LEGACY_PRIVATE_TOKEN: variável não reconhecida ou não persistível",
        "environment.RASAI_RETIRED_INPUT: variável não reconhecida ou não persistível",
        "environment.: variável não reconhecida ou não persistível",
        "console.device: invalid and irrelevant",
    ]
    result = _classify_environment_warning_reasons(warnings)
    assert result == {
        "registered_but_excluded": 1,
        "unregistered_secret_pattern": 1,
        "unregistered_name": 1,
        "empty_name": 1,
    }
    rendered = json.dumps(result)
    for forbidden in ("OPENAI_API_KEY", "LEGACY_PRIVATE_TOKEN", "RASAI_RETIRED_INPUT"):
        assert forbidden not in rendered
    assert all(value == 0 for value in _classify_environment_warning_reasons([]).values())


def test_apdex_preflight_classifies_rejected_environment_without_read_write_leak(
    tmp_path,
):
    from unittest.mock import patch
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers

    path = tmp_path / "operator.ini"
    path.write_text(
        "[environment]\n"
        "OPENAI_API_KEY = NEVER_ECHO_PRIVATE_SECRET\n"
        "LEGACY_PRIVATE_TOKEN = NEVER_ECHO_OLD_SECRET\n"
        "RASAI_RETIRED_INPUT = NEVER_ECHO_SETTING\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        result = inspect_apdex_consumers(path, environ={})
    assert result["status"] == "ADAPTERS_PARTIAL_LOAD_WARNINGS"
    assert result["load_warning_count"] == 3
    assert result["load_warning_categories"]["unknown_or_nonpersistible_environment"] == 3
    assert result["load_warning_environment_reasons"] == {
        "registered_but_excluded": 1,
        "unregistered_secret_pattern": 1,
        "unregistered_name": 1,
        "empty_name": 0,
    }
    assert sum(result["load_warning_environment_reasons"].values()) == 3
    assert result["external_requests"] == result["audit_writes"] == 0
    assert result["values_exposed"] is False
    assert path.read_bytes() == before
    rendered = json.dumps(result)
    for forbidden in (
        "OPENAI_API_KEY", "LEGACY_PRIVATE_TOKEN", "RASAI_RETIRED_INPUT",
        "NEVER_ECHO",
    ):
        assert forbidden not in rendered


def test_security_and_improvement_declared_adapters_are_not_runtime_proof(tmp_path):
    """Contract inventory comes from actual constants; no external access is executed."""
    from rasai import passive_security, improvement_intelligence as improvement

    result = inventory(path=tmp_path / "no-operator.ini", environ={})
    rows = {row["name"]: row for row in result["environment_variables"]}
    for name in (
        passive_security.ENABLED_ENV, passive_security.EXTERNAL_TIMEOUT_ENV,
        passive_security.OSV_ENV, passive_security.KEV_ENV,
        improvement.ENABLED_ENV, improvement.MAX_RECOMMENDATIONS_ENV,
        improvement.TIMEOUT_ENV, improvement.AI_ANALYSIS_LANGUAGE_ENV,
    ):
        assert rows[name]["declared_adapter_surface"] != (
            "NOT_MAPPED_NO_CONSUMER_INFERENCE"
        )
        assert rows[name]["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY"
        assert rows[name]["declared_adapter_surface_is_execution_proof"] is False
    status = result["security_improvement_adapter_surface_coverage"]
    assert status["mapped_registry_variables"] >= 8
    assert not status["external_security_feeds_or_ai_provider_calls_proven"]
    assert not status["security_snapshot_or_improvement_execution_proven"]
    assert not (tmp_path / "no-operator.ini").exists()


def test_ai_catalog_runtime_selectors_are_declared_without_execution_proof(tmp_path):
    from rasai import ai_model_catalog, ai_pricing_catalog, ai_task_profiles

    result = inventory(path=tmp_path / "not-created.ini", environ={})
    rows = {item["name"]: item for item in result["environment_variables"]}
    names = (
        ai_model_catalog.MODEL_SOURCE_ENV, ai_model_catalog.MODEL_FILE_ENV,
        ai_pricing_catalog.PRICING_SOURCE_ENV, ai_pricing_catalog.PRICING_FILE_ENV,
        ai_task_profiles.PROFILE_SOURCE_ENV, ai_task_profiles.PROFILE_FILE_ENV,
    )
    for name in names:
        assert rows[name]["declared_adapter_surface"] != (
            "NOT_MAPPED_NO_CONSUMER_INFERENCE"
        )
        assert rows[name]["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY"
        assert rows[name]["declared_adapter_surface_is_execution_proof"] is False
    assert result["ai_catalog_adapter_surface_coverage"][
        "mapped_registry_variables"
    ] == len(names)
    assert result["ai_catalog_adapter_surface_coverage"][
        "catalog_load_or_provider_use_proven"
    ] is False
    assert not (tmp_path / "not-created.ini").exists()


def test_presentation_timezone_adapter_declared_without_clock_mutation_claim(tmp_path):
    from rasai.time_contract import PRESENTATION_TIMEZONE_ENV

    result = inventory(path=tmp_path / "none.ini", environ={})
    row = next(item for item in result["environment_variables"]
               if item["name"] == PRESENTATION_TIMEZONE_ENV)
    assert row["declared_adapter_surface"] == (
        "PRESENTATION_FORMAT_INPUT_NOT_PERSISTED_CLOCK_CHANGE"
    )
    assert row["runtime_consumer"] == "NOT_PROVEN_BY_REGISTRY"
    assert row["declared_adapter_surface_is_execution_proof"] is False
    assert not (tmp_path / "none.ini").exists()
