"""Secret name-only policy diagnostics for offline configuration inventory (#523)."""
from __future__ import annotations

import json

from rasai.console_configuration_inventory_523 import inventory


def test_inventory_flags_secret_keys_in_ini_without_disclosing_values(tmp_path):
    path = tmp_path / "synthetic.ini"
    path.write_text(
        "[environment]\n"
        "OPENAI_API_KEY=FAKE_SECRET_ALPHA\n"
        "PERPLEXITY_API_KEY=FAKE_SECRET_BETA\n"
        "RASAI_SERP_MAX_REQUESTS=7\n",
        encoding="utf-8",
    )
    original = path.read_bytes()
    report = inventory(path=path, environ={})
    rows = {item["name"]: item for item in report["environment_variables"]}
    assert report["secret_ini_scan_complete"] is True
    assert report["secret_ini_policy_violations"] == 2
    assert rows["OPENAI_API_KEY"]["secret_present_in_ini_violation"] is True
    assert rows["PERPLEXITY_API_KEY"]["secret_present_in_ini_violation"] is True
    assert rows["RASAI_SERP_MAX_REQUESTS"]["secret_present_in_ini_violation"] is False
    payload = json.dumps(report)
    assert "FAKE_SECRET_ALPHA" not in payload
    assert "FAKE_SECRET_BETA" not in payload
    assert path.read_bytes() == original


def test_inventory_secret_scan_abstains_when_source_unreadable(tmp_path):
    report = inventory(path=tmp_path / "not-created.ini", environ={})
    assert report["secret_ini_scan_complete"] is False
    assert report["secret_ini_policy_violations"] == 0
    assert report["file_readable"] is False
