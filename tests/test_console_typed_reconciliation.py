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
