"""#523 only: unified metadata gate and draft opt-in fail-closed checks."""
from __future__ import annotations

from configparser import ConfigParser
import json
import os
from unittest.mock import patch

from rasai.console_acceptance_523 import (
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
        inspected = _perplexity_draft(ini)
        assert inspected["status"] == "DRAFT_RESTORED_NO_EXECUTION_INTENT"
        assert inspected["draft_count"] == 1
        assert inspected["active_request_count"] == 0
        assert inspected["paid_request_inherited"] is False
        assert inspected["requests"] == inspected["audit_writes"] == 0
        assert "exemplo sem consentimento" not in json.dumps(inspected)
        assert os.environ == {}
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
    from rasai import console_acceptance_523
    file = tmp_path / "absent.ini"
    def stub(_path, prior):
        assert "environment_variables" in prior
        return {
            "status": "CONFIGURATION_CONTRACT_FAILURE",
            "consumer_status": {"search": "CLI_ARGUMENTS_MISMATCH"},
        }
    monkeypatch.setattr(console_acceptance_523, "inspect_console_acceptance", stub)
    assert inventory_main(["--ini", str(file)]) == 0
    assert "acceptance_523" not in json.loads(capsys.readouterr().out)
    assert inventory_main(["--ini", str(file), "--acceptance-523"]) == 2
    body = json.loads(capsys.readouterr().out)
    assert body["acceptance_523"]["status"] == "CONFIGURATION_CONTRACT_FAILURE"
    monkeypatch.setattr(
        console_acceptance_523, "inspect_console_acceptance",
        lambda _path, prior: {"status": "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"},
    )
    assert inventory_main(["--ini", str(file), "--acceptance-523"]) == 0


def test_523_acceptance_readonly_missing_ini_fails_closed(tmp_path):
    missing = tmp_path / "never-create.ini"
    result = inspect_console_acceptance(missing)
    assert result["status"] == "CONFIGURATION_CONTRACT_FAILURE"
    assert result["values_exposed"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert result["source_ini_writes"] == 0
    assert not missing.exists()
