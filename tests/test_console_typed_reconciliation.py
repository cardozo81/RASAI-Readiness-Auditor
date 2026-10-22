"""#523: no-write, no-disclosure typed adapter coverage for a physical INI."""
from __future__ import annotations

import json
import os

from rasai.console_typed_reconciliation import inspect_typed_configuration
from rasai.console_configuration_inventory import main as inventory_main


def test_typed_ini_reconciles_apdex_fields_without_exposing_values(tmp_path, monkeypatch, capsys):
    source = tmp_path / "session.ini"
    source.write_text(
        "[console]\ndevice=desktop\n"
        "[synthetic_apdex]\nenabled = true\n"
        "samples_per_context = 8\nconcurrency = 2\n"
        "[synthetic_apdex_experience]\n"
        "architecture = CSR_SPA\nprofile_mode = DYNATRACE_GUIDED\n"
        "kpm = VISUALLY_COMPLETE\n"
        "xhr_capture = false\nfetch_capture = true\n"
        "concurrency = 2\n"
        "dynatrace_config_json = {}\n"
        "[ai]\nmodel=customer-pricing-secret-do-not-print\n",
        encoding="utf-8",
    )
    before = source.read_bytes()
    environment = dict(os.environ)
    result = inspect_typed_configuration(source)
    assert result["status"] == "TYPED_ADAPTERS_INSPECTED"
    rows = {row["field"]: row for row in result["fields"]}
    for field in (
        "synthetic_apdex.enabled", "synthetic_apdex.samples_per_context",
        "synthetic_apdex_experience.architecture",
        "synthetic_apdex_experience.profile_mode",
        "synthetic_apdex_experience.kpm",
        "synthetic_apdex_experience.xhr_capture",
        "synthetic_apdex_experience.fetch_capture",
    ):
        assert rows[field]["state"] == "DECLARED_RUNTIME_PROJECTION"
        assert rows[field]["runtime_input_proven"] is False
    assert rows["synthetic_apdex_experience.device_mix"]["state"] == "DERIVED_FROM_DEVICE"
    assert result["runtime_consumption_verified"] is False
    assert result["new_audit_consent_inherited"] is False
    payload = json.dumps(result)
    assert "customer-pricing-secret-do-not-print" not in payload
    assert "DYNATRACE_GUIDED" not in payload
    assert "CSR_SPA" not in payload
    assert source.read_bytes() == before
    assert os.environ == environment
    assert inventory_main(["--ini", str(source), "--reconcile-typed"]) == 0
    combined = json.loads(capsys.readouterr().out)
    assert combined["typed_adapter_reconciliation"]["status"] == "TYPED_ADAPTERS_INSPECTED"
    assert source.read_bytes() == before


def test_typed_ini_reports_invalid_and_unknown_as_metadata_only(tmp_path):
    source = tmp_path / "session.ini"
    source.write_text(
        "[synthetic_apdex_experience]\narchitecture=NOT_A_VALID_CLASS\n"
        "samples_per_page = 0\nprofile_mode=CUSTOM\n"
        "new_secret_or_unknown = never-display-me\n",
        encoding="utf-8",
    )
    row = inspect_typed_configuration(source)
    assert row["invalid_typed_fields"] >= 2
    assert row["counts"].get("UNRECOGNIZED_INPUT_COUNT") == 1
    assert "never-display-me" not in json.dumps(row)
    assert "NOT_A_VALID_CLASS" not in json.dumps(row)


def test_typed_ini_refuses_missing_symlink_and_invalid_encoding_without_writes(tmp_path):
    missing = tmp_path / "not-found.ini"
    result = inspect_typed_configuration(missing)
    assert result["status"] == "NOT_VERIFIABLE"
    assert not missing.exists()
    bad = tmp_path / "bad.ini"
    bad.write_bytes(b"\xff\xfe\xfd")
    data = bad.read_bytes()
    assert inspect_typed_configuration(bad)["status"] == "NOT_VERIFIABLE"
    assert bad.read_bytes() == data
    link = tmp_path / "shadow.ini"
    try:
        link.symlink_to(bad)
    except (OSError, NotImplementedError):
        return
    assert inspect_typed_configuration(link)["status"] == "NOT_VERIFIABLE"
    assert bad.read_bytes() == data


def test_empty_optional_apdex_values_are_not_runtime_inputs(tmp_path):
    source = tmp_path / "optional.ini"
    source.write_text(
        "[synthetic_apdex]\nthreshold_seconds =\n"
        "[synthetic_apdex_experience]\nsatisfied_seconds =\nfrustrated_seconds =\n",
        encoding="utf-8",
    )
    before = source.read_bytes()
    result = inspect_typed_configuration(source)
    fields = {row["field"]: row for row in result["fields"]}
    for field in (
        "synthetic_apdex.threshold_seconds",
        "synthetic_apdex_experience.satisfied_seconds",
        "synthetic_apdex_experience.frustrated_seconds",
    ):
        assert fields[field]["state"] == "RUNTIME_PROJECTION_EMPTY"
        assert fields[field]["runtime_input_proven"] is False
    assert source.read_bytes() == before



def test_typed_inspection_validates_all_installed_sections_without_mutating_timezone(tmp_path):
    from unittest.mock import patch
    from rasai.console_ui_refactor import _install_search_persistence

    _install_search_persistence()
    source = tmp_path / "full-typed.ini"
    source.write_text(
        "[presentation]\ntimezone=America/Sao_Paulo\n"
        "[search_intelligence]\nqueries=local term\ncontent_max_redirects=0\n"
        "[perplexity_draft]\nqueries=draft only\nsearch_type=fast\n",
        encoding="utf-8",
    )
    before = source.read_bytes()
    with patch.dict(os.environ, {}, clear=True):
        result = inspect_typed_configuration(source)
        assert os.environ == {}
    fields = {entry["field"]: entry for entry in result["fields"]}
    for field in (
        "presentation.timezone", "search_intelligence.queries",
        "search_intelligence.content_max_redirects", "perplexity_draft.queries",
        "perplexity_draft.search_type",
    ):
        assert fields[field]["state"] == "ADAPTER_PARSED"
    assert result["invalid_typed_fields"] == 0
    assert result["counts"].get("UNRECOGNIZED_INPUT_COUNT", 0) == 0
    assert "local term" not in json.dumps(result)
    assert "draft only" not in json.dumps(result)
    assert source.read_bytes() == before


def test_typed_inspection_rejects_unowned_ini_inputs_without_value_disclosure(tmp_path):
    from unittest.mock import patch
    from rasai.console_ui_refactor import _install_search_persistence

    _install_search_persistence()
    cases = (
        "[presentation]\nunexpected=DO_NOT_ECHO_ME\n",
        "[search_intelligence]\nunknown_setting=DO_NOT_ECHO_ME\n",
        "[perplexity_draft]\nunknown_setting=DO_NOT_ECHO_ME\n",
        "[environment]\nNOT_IN_CURRENT_REGISTRY=DO_NOT_ECHO_ME\n",
        "[DEFAULT]\ninvalid_default=DO_NOT_ECHO_ME\n[console]\nproject=fixture\n",
        "[non_owned_private_section]\nunknown_setting=DO_NOT_ECHO_ME\n",
    )
    source = tmp_path / "unowned.ini"
    with patch.dict(os.environ, {}, clear=True):
        for case in cases:
            source.write_text(case, encoding="utf-8")
            before = source.read_bytes()
            report = inspect_typed_configuration(source)
            assert report["counts"].get("UNRECOGNIZED_INPUT_COUNT", 0) >= 1
            assert report["status"] == "TYPED_ADAPTERS_INSPECTED"
            assert "DO_NOT_ECHO_ME" not in json.dumps(report)
            assert "non_owned_private_section" not in json.dumps(report)
            assert source.read_bytes() == before
        assert os.environ == {}


def test_typed_inspection_validates_presentation_timezone_without_setting_process_env(tmp_path):
    from unittest.mock import patch
    source = tmp_path / "invalid-tz.ini"
    source.write_text("[presentation]\ntimezone=-03:00\n", encoding="utf-8")
    with patch.dict(os.environ, {}, clear=True):
        report = inspect_typed_configuration(source)
        assert os.environ == {}
    fields = {entry["field"]: entry for entry in report["fields"]}
    assert fields["presentation.timezone"]["state"] == "INVALID_TYPED_VALUE"
    assert report["invalid_typed_fields"] >= 1
