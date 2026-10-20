"""#523 only: unified metadata gate and draft opt-in fail-closed checks."""
from __future__ import annotations

from configparser import ConfigParser
import json
import os
from unittest.mock import patch

from rasai.console_acceptance_contract import (
    classify_console_acceptance,
    inspect_console_acceptance,
    _perplexity_draft,
)
from rasai.console_configuration_inventory import main as inventory_main


def _base():
    return {
        "typed": "TYPED_ADAPTERS_INSPECTED",
        "apdex": "ADAPTERS_VALIDATED_OFFLINE",
        "core": "CORE_CLI_PARITY_VERIFIED",
        "search": "CLI_ADAPTERS_VALIDATED_OFFLINE",
        "gsc": "LOCAL_SCOPE_AND_OAUTH_CONFIG_VERIFIED",
        "perplexity": "DRAFT_RESTORED_NO_EXECUTION_INTENT",
    }


def test_523_gate_separates_pass_optional_absence_external_and_defect():
    original = _base()
    all_ok = classify_console_acceptance(original)
    assert all_ok["status"] == "OFFLINE_CONTRACTS_VERIFIED"
    assert all_ok["issue_523_final_acceptance_proven"] is False

    optional = dict(original, search="NO_SEARCH_QUERY_INPUT",
                    gsc="GSC_DISABLED_BY_CONFIGURATION",
                    perplexity="NO_DRAFT_NO_EXECUTION_INTENT")
    no_request = classify_console_acceptance(optional)
    assert no_request["status"] == "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"
    assert no_request["intentionally_not_requested_consumer_names"] == [
        "gsc", "perplexity", "search",
    ]

    # The operator may configure and save the INI before choosing a URL.
    # It is not a missing external dependency of configuration persistence.
    unprepared = dict(
        original, core="CLI_PARITY_TARGET_NOT_SET", gsc="TARGET_NOT_PREPARED",
        search="NO_SEARCH_QUERY_INPUT",
        perplexity="NO_DRAFT_NO_EXECUTION_INTENT",
    )
    prepared_state = classify_console_acceptance(unprepared)
    assert prepared_state["status"] == "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"
    assert prepared_state["failed_consumer_names"] == []
    assert prepared_state["external_prerequisite_consumer_names"] == []
    assert prepared_state["target_not_prepared_consumer_names"] == ["core", "gsc"]
    assert prepared_state["intentionally_not_requested_consumer_names"] == [
        "perplexity", "search",
    ]
    assert prepared_state["target_scope_execution_verified"] is False
    assert prepared_state["issue_523_final_acceptance_proven"] is False

    missing = dict(original, core="EXTERNAL_WEB_PREREQUISITE_UNVERIFIED",
                   gsc="REQUIRED_OAUTH_NOT_CONFIGURED")
    external = classify_console_acceptance(missing)
    assert external["status"] == "EXTERNAL_PREREQUISITE_OR_TARGET_MISSING"
    assert external["failed_consumer_names"] == []
    assert external["external_prerequisite_consumer_names"] == ["core", "gsc"]

    broken = dict(original, search="CLI_ARGUMENTS_MISMATCH")
    reject = classify_console_acceptance(broken)
    assert reject["status"] == "CONFIGURATION_CONTRACT_FAILURE"
    assert reject["failed_consumer_names"] == ["search"]
    assert classify_console_acceptance(original, invalid_typed_fields=1)["status"] == (
        "CONFIGURATION_CONTRACT_FAILURE"
    )
    assert classify_console_acceptance(original, unknown_typed_fields=1)["status"] == (
        "CONFIGURATION_CONTRACT_FAILURE"
    )


def test_523_perplexity_draft_from_ini_never_inherits_billable_intent(tmp_path):
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai import console_settings

    with patch.dict(os.environ, {}, clear=True):
        _install_search_persistence()
        install()
        state = SearchConsoleState()
        state.perplexity_queries = ("exemplo sem consentimento futuro",)
        state.perplexity_search_type = "fast"
        ini = tmp_path / "draft.ini"
        console_settings.save_console_config(state, ini)
        physical = ini.read_bytes()
        environment_before = dict(os.environ)
        inspected = _perplexity_draft(ini)
        assert inspected["status"] == "DRAFT_RESTORED_NO_EXECUTION_INTENT"
        assert inspected["draft_count"] == 1
        assert inspected["active_request_count"] == 0
        assert inspected["paid_request_inherited"] is False
        assert inspected["requests"] == inspected["audit_writes"] == 0
        assert "exemplo sem consentimento" not in json.dumps(inspected)
        # Save legitimately projects nonsecret session state; the inspector
        # must restore exactly that state, not replace it with an empty env.
        assert os.environ == environment_before
        assert ini.read_bytes() == physical

        parser = ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(ini, encoding="utf-8")
        parser["perplexity_draft"]["queries"] = ""
        with ini.open("w", encoding="utf-8") as fp:
            parser.write(fp)
        empty = _perplexity_draft(ini)
        assert empty["status"] == "NO_DRAFT_NO_EXECUTION_INTENT"


def test_523_inventory_optin_has_nonzero_exit_only_for_real_gate_failure(
    tmp_path, monkeypatch, capsys,
):
    from rasai import console_acceptance_contract
    file = tmp_path / "absent.ini"
    def stub(_path, prior):
        assert "environment_variables" in prior
        return {
            "status": "CONFIGURATION_CONTRACT_FAILURE",
            "consumer_status": {"search": "CLI_ARGUMENTS_MISMATCH"},
        }
    monkeypatch.setattr(console_acceptance_contract, "inspect_console_acceptance", stub)
    assert inventory_main(["--ini", str(file)]) == 0
    assert "acceptance_523" not in json.loads(capsys.readouterr().out)
    assert inventory_main(["--ini", str(file), "--acceptance-523"]) == 2
    body = json.loads(capsys.readouterr().out)
    assert body["acceptance_523"]["status"] == "CONFIGURATION_CONTRACT_FAILURE"
    monkeypatch.setattr(
        console_acceptance_contract, "inspect_console_acceptance",
        lambda _path, prior: {"status": "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"},
    )
    assert inventory_main(["--ini", str(file), "--acceptance-523"]) == 0


def test_523_acceptance_readonly_missing_ini_fails_closed(tmp_path):
    missing = tmp_path / "never-create.ini"
    result = inspect_console_acceptance(missing)
    assert result["status"] == "INI_SOURCE_UNVERIFIABLE"
    assert result["source_generation_consistent"] is False
    assert result["values_exposed"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert result["source_ini_writes"] == 0
    assert not missing.exists()


def test_523_outer_ini_generation_check_rejects_change_between_consumer_checks(
    tmp_path, monkeypatch,
):
    import rasai.console_typed_reconciliation as typed
    from rasai import console_acceptance_contract
    source = tmp_path / "changed.ini"
    source.write_text("[console]\nconfig_version=1\n", encoding="utf-8")
    # The gate must abstain even when every mocked adapter claims success:
    # two successful local inspections cannot attest different generations.
    all_ok = _base()
    def changing_adapter(_path):
        source.write_text("[console]\nconfig_version=2\n", encoding="utf-8")
        return {"status": all_ok["typed"], "counts": {}, "invalid_typed_fields": 0}
    monkeypatch.setattr(typed, "inspect_typed_configuration", changing_adapter)
    previous = {
        "apdex_offline_consumer_preflight": {"status": all_ok["apdex"]},
        "core_offline_consumer_preflight": {"status": all_ok["core"]},
        "search_offline_consumer_preflight": {"status": all_ok["search"]},
        "gsc_offline_consumer_preflight": {"status": all_ok["gsc"]},
        "typed_ini_coverage": {"missing_non_derived_names": []},
    }
    monkeypatch.setattr(
        console_acceptance_contract, "_perplexity_draft",
        lambda _: {"status": all_ok["perplexity"]},
    )
    report = inspect_console_acceptance(source, prior=previous)
    assert report["status"] == "INI_SOURCE_CHANGED_DURING_GATE"
    assert report["source_generation_consistent"] is False
    assert report["issue_523_final_acceptance_proven"] is False
    assert report["values_exposed"] is False


def test_523_legacy_missing_fields_are_incomplete_coverage_not_parser_defect(
    tmp_path, monkeypatch,
):
    from rasai import console_acceptance_contract
    source = tmp_path / "legacy.ini"
    source.write_text("[console]\nconfig_version=1\n", encoding="utf-8")
    ok = _base()
    monkeypatch.setattr(
        console_acceptance_contract, "_perplexity_draft",
        lambda _: {"status": ok["perplexity"]},
    )
    previous = {
        "typed_adapter_reconciliation": {
            "status": ok["typed"], "counts": {}, "invalid_typed_fields": 0,
        },
        "apdex_offline_consumer_preflight": {"status": ok["apdex"]},
        "core_offline_consumer_preflight": {"status": ok["core"]},
        "search_offline_consumer_preflight": {"status": ok["search"]},
        "gsc_offline_consumer_preflight": {"status": ok["gsc"]},
        "typed_ini_coverage": {
            "missing_non_derived_names": [
                "synthetic_apdex_experience.architecture", "ai.max_cycles",
            ],
        },
        "secret_ini_policy_violations": 0,
        "unregistered_secret_ini_key_count": 0,
        "file_readable": True,
    }
    result = inspect_console_acceptance(source, prior=previous)
    assert result["status"] == "OFFLINE_TYPED_COVERAGE_PARTIAL"
    assert result["typed_fields_unavailable"] == 2
    assert result["source_generation_consistent"] is True
    assert result["failed_consumer_names"] == []
    assert result["issue_523_final_acceptance_proven"] is False


def test_523_acceptance_abstains_for_source_symlink_before_running_any_adapter(
    tmp_path, monkeypatch,
):
    from rasai import console_acceptance_contract
    source = tmp_path / "a.ini"
    source.write_text("[console]\nconfig_version=1\n", encoding="utf-8")
    link = tmp_path / "link.ini"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    monkeypatch.setattr(
        console_acceptance_contract, "_perplexity_draft",
        lambda _: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    result = inspect_console_acceptance(link)
    assert result["status"] == "INI_SOURCE_UNVERIFIABLE"
    assert result["source_generation_consistent"] is False
    assert result["provider_requests"] == 0


def test_523_unregistered_secret_ini_is_not_accepted_even_if_cached_adapters_pass(
    tmp_path, monkeypatch,
):
    from rasai import console_acceptance_contract
    source = tmp_path / "private.ini"
    source.write_text(
        "[environment]\nPERPLEXITY_API_KEY = NEVER_SHOW_THIS_CREDENTIAL\n",
        encoding="utf-8",
    )
    statuses = _base()
    previous = {
        "typed_adapter_reconciliation": {
            "status": statuses["typed"], "counts": {}, "invalid_typed_fields": 0,
        },
        "apdex_offline_consumer_preflight": {"status": statuses["apdex"]},
        "core_offline_consumer_preflight": {"status": statuses["core"]},
        "search_offline_consumer_preflight": {"status": statuses["search"]},
        "gsc_offline_consumer_preflight": {"status": statuses["gsc"]},
    }
    monkeypatch.setattr(
        console_acceptance_contract, "_perplexity_draft",
        lambda _: {"status": statuses["perplexity"]},
    )
    before = source.read_bytes()
    report = inspect_console_acceptance(source, prior=previous)
    assert report["status"] == "CONFIGURATION_CONTRACT_FAILURE"
    assert report["secret_ini_policy_violations_detected"] is True
    assert "ini_secret_or_unreadable_source" in report["failed_consumer_names"]
    assert "NEVER_SHOW_THIS_CREDENTIAL" not in json.dumps(report)
    assert source.read_bytes() == before


def test_523_full_saved_ini_acceptance_invokes_each_consumer_once_offline(
    tmp_path, monkeypatch,
):
    """A single real INI and real adapters, not six fabricated PASS statuses."""
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install
    from rasai import console_settings
    from rasai.console_configuration_inventory import inventory

    with patch.dict(os.environ, {"RASAI_GSC_ENABLED": "false"}, clear=True):
        _install_search_persistence()
        install()
        state = SearchConsoleState()
        state.target = "https://example.test/fixture"
        state.ai_provider = "none"
        state.web_performance = False
        state.synthetic_apdex = False
        state.apdex_experience = False
        state.search_queries = ()
        state.perplexity_queries = ()
        source = tmp_path / "operator.ini"
        console_settings.save_console_config(state, source)
        before = source.read_bytes()
        environment_before = dict(os.environ)
        meta = inventory(path=source)
        # The adapter suite uses the same source and no remote endpoint.
        report = inspect_console_acceptance(source, prior=meta)
        assert report["source_generation_consistent"] is True
        assert report["secret_ini_policy_violations_detected"] is False
        assert report["typed_fields_unavailable"] == 0
        assert report["failed_consumer_names"] == []
        assert report["status"] == "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"
        assert report["consumer_status"]["typed"] == "TYPED_ADAPTERS_INSPECTED"
        assert report["consumer_status"]["apdex"] == "ADAPTERS_VALIDATED_OFFLINE"
        assert report["consumer_status"]["core"] == "CORE_CLI_PARITY_VERIFIED"
        assert report["consumer_status"]["search"] == "NO_SEARCH_QUERY_INPUT"
        assert report["consumer_status"]["gsc"] == "GSC_DISABLED_BY_CONFIGURATION"
        assert report["consumer_status"]["perplexity"] == "NO_DRAFT_NO_EXECUTION_INTENT"
        assert os.environ == environment_before
        assert source.read_bytes() == before
        assert report["paid_external_use_authorized"] is False
        assert report["provider_requests"] == report["audit_writes"] == 0


def test_523_real_ini_without_target_is_valid_preparation_not_provider_block(
    tmp_path,
):
    """Read real consumers, not fabricated statuses; preserve the INI/env."""
    from rasai import console_settings
    from rasai.console_complete_persistence import install
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_configuration_inventory import inventory

    with patch.dict(os.environ, {}, clear=True):
        _install_search_persistence()
        install()
        state = SearchConsoleState()
        state.target = ""
        state.ai_provider = "none"
        state.web_performance = False
        state.synthetic_apdex = False
        state.apdex_experience = False
        state.search_queries = ()
        state.perplexity_queries = ()
        file = tmp_path / "preparar-sem-url.ini"
        console_settings.save_console_config(state, file)
        before_bytes = file.read_bytes()
        before_env = dict(os.environ)
        observed = inspect_console_acceptance(file, prior=inventory(path=file))
        assert observed["consumer_status"]["core"] == "CLI_PARITY_TARGET_NOT_SET"
        assert observed["consumer_status"]["gsc"] == "TARGET_NOT_PREPARED"
        assert observed["status"] == "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"
        assert observed["target_not_prepared_consumer_names"] == ["core", "gsc"]
        assert observed["external_prerequisite_consumer_names"] == []
        assert observed["failed_consumer_names"] == []
        assert observed["source_generation_consistent"] is True
        assert observed["typed_fields_unavailable"] == 0
        assert observed["target_scope_execution_verified"] is False
        assert observed["issue_523_final_acceptance_proven"] is False
        assert observed["paid_external_use_authorized"] is False
        assert observed["provider_requests"] == observed["audit_writes"] == 0
        assert file.read_bytes() == before_bytes
        assert os.environ == before_env
