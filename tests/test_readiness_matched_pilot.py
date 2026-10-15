"""#322: offline paired local pilot does not certify M25 production readiness."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from rasai.readiness_matched_pilot_322 import (
    assess_matched_readiness_pilot, main,
)


def _pairs(n=5, overhead=8):
    return [
        {
            "page_id": "PAGE-ONE",
            "device": "MOBILE",
            "architecture": "CSR_SPA",
            "browser_version": "Chromium TEST",
            "network_profile": "offline-static-fixture",
            "cpu_profile": "unthrottled-local",
            "context_profile": "viewport=390x844",
            "navigation_url": "http://localhost/testfixture",
            "control": {
                "sample_id": f"CTRL-{i}",
                "load_duration_ms": 120 + i,
            },
            "probe": {
                "sample_id": f"PROBE-{i}",
                "load_duration_ms": 120 + i + overhead,
                "active_probe_wall_ms": overhead,
                "enabled": True,
                "identity_proof": "CALLER_DECLARED_NOT_ATTESTED_BY_M25",
                "source_page_reused": True,
            },
        }
        for i in range(n)
    ]


def test_322_matched_local_pairs_finite_criteria_do_not_authorize_m25():
    data = _pairs()
    original = deepcopy(data)
    result = assess_matched_readiness_pilot(data)
    assert result["status"] == "MATCHED_LOCAL_PILOT_ASSESSED"
    assert result["pairs_accepted"] == 5
    assert result["measured_wall_delta_p90_ms"] == 8
    assert result["max_observed_probe_active_ms"] == 8
    assert result["within_declared_overhead_budget"] is True
    assert result["gateway_identity_attested"] is False
    assert result["m25_production_activation_approved"] is False
    assert result["m25_apdex_changed"] is False
    assert result["audit_writes"] == result["provider_requests"] == 0
    assert original == data


def test_322_over_budget_abstains_from_production_gate():
    value = assess_matched_readiness_pilot(_pairs(overhead=65))
    assert value["within_declared_overhead_budget"] is False
    assert value["reason"] == "LOCAL_PROBE_OVERHEAD_EXCEEDS_DECLARED_BUDGET"
    assert value["m25_production_activation_approved"] is False


@pytest.mark.parametrize("problem", [
    "few", "duplicate", "cross", "not_enabled", "clock_nan",
    "clock_missing", "unknown_arch", "browser_mismatch", "profile_mismatch",
])
def test_322_invalid_pairing_abstains_without_fabricated_p90(problem):
    pairs = _pairs()
    if problem == "few":
        pairs = pairs[:2]
    elif problem == "duplicate":
        pairs[1]["probe"]["sample_id"] = pairs[0]["probe"]["sample_id"]
    elif problem == "cross":
        pairs[1]["probe"]["sample_id"] = pairs[1]["control"]["sample_id"]
    elif problem == "not_enabled":
        pairs[2]["probe"]["enabled"] = False
    elif problem == "clock_nan":
        pairs[3]["probe"]["active_probe_wall_ms"] = float("nan")
    elif problem == "clock_missing":
        pairs[3]["control"].pop("load_duration_ms")
    elif problem == "unknown_arch":
        pairs[2]["architecture"] = "UNKNOWN"
    elif problem == "browser_mismatch":
        pairs[4]["browser_version"] = "Different runtime"
    elif problem == "profile_mismatch":
        pairs[2]["context_profile"] = "unmatched viewport"
    result = assess_matched_readiness_pilot(pairs)
    assert result["status"] == "NOT_EVALUABLE"
    assert result["measured_wall_delta_p90_ms"] is None
    assert result["within_declared_overhead_budget"] is None
    assert result["m25_production_activation_approved"] is False


def test_322_local_cli_is_read_only_and_rejects_symlink(tmp_path, capsys):
    path = tmp_path / "pairs.json"
    path.write_text(json.dumps({"pairs": _pairs()}), encoding="utf-8")
    source = path.read_bytes()
    assert main(["--json", str(path), "--budget-ms", "15"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "MATCHED_LOCAL_PILOT_ASSESSED"
    assert output["provider_requests"] == 0
    assert output["audit_writes"] == 0
    assert source == path.read_bytes()
    link = tmp_path / "alias.json"
    try:
        link.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")
    with pytest.raises(SystemExit):
        main(["--json", str(link)])
