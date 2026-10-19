"""#602: decision matrix uses only parity-verified offline sensitivity output."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from rasai.optional_seo_policy_decision import build_optional_seo_decision_matrix


def _replay():
    def score(value, coverage, confidence="HIGH", gate="ATTENTION"):
        return {
            "value": value,
            "coverage": coverage,
            "confidence": confidence,
            "consolidation_status": "CONSOLIDATED",
            "readiness_limitations": [
                "READINESS_STATUS:" + gate, "CRITICAL_GATE:DISCOVERY_ACCESS:WARNING",
            ],
        }
    return {
        "contract": "RASAI-SEO-POLICY-SENSITIVITY-602-001",
        "canonical_scoring_version": "SCORE-GEO-004",
        "source_audit_db_replay_parity": "VERIFIED_SCORE_GEO_004",
        "source_audit_db_sha256": "a" * 64,
        "published_score_mutated": False,
        "new_scoring_version_approved": False,
        "provider_requests": 0, "audit_writes": 0,
        "source_rule_executions": 59,
        "optional_absence_executions": 3,
        "scenarios": {
            "CANONICAL_SCORE_GEO_004": {
                "DISCOVERY_ACCESS": score(93, .9),
                "OVERALL_READINESS": score(86.484962, .974737),
            },
            "SENSITIVITY_OPTIONAL_ABSENCE_PASS": {
                "DISCOVERY_ACCESS": score(99, 1),
                "OVERALL_READINESS": score(89.958647, .974737, gate="READY"),
            },
            "SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE": {
                "DISCOVERY_ACCESS": score(98, .8, "MEDIUM"),
                "OVERALL_READINESS": score(89.800752, .95, "MEDIUM", "READY"),
            },
        },
    }


def test_decision_matrix_golden_transitions_and_immutability():
    replay = _replay()
    frozen = deepcopy(replay)
    output = build_optional_seo_decision_matrix(replay)
    assert replay == frozen
    assert output["status"] == "DECISION_SUPPORT_ONLY_NOT_NORMATIVE"
    assert output["source_audit_db_sha256"] == "a" * 64
    assert output["new_scoring_version_approved"] is False
    assert output["provider_requests"] == output["audit_writes"] == 0
    assert output["all_values_non_additive"] is True
    assert len(output["rows"]) == 4
    selected = {
        (row["scenario"], row["dimension"]): row for row in output["rows"]
    }
    chosen = selected[("SENSITIVITY_OPTIONAL_ABSENCE_PASS", "OVERALL_READINESS")]
    assert chosen["delta_points"] == 3.473685
    assert chosen["delta_coverage_fraction"] == 0
    assert chosen["canonical_readiness_gates"][0] == "READINESS_STATUS:ATTENTION"
    assert chosen["scenario_readiness_gates"][0] == "READINESS_STATUS:READY"
    assert chosen["interpretation"] == "CHANGED"
    alternative = selected[(
        "SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE", "DISCOVERY_ACCESS"
    )]
    assert alternative["delta_points"] == 5
    assert alternative["delta_coverage_fraction"] == -.1
    assert alternative["canonical_confidence"] == "HIGH"
    assert alternative["scenario_confidence"] == "MEDIUM"


@pytest.mark.parametrize(("field", "replacement"), [
    ("source_audit_db_replay_parity", "UNVERIFIED"),
    ("new_scoring_version_approved", True),
    ("provider_requests", 1),
    ("audit_writes", 1),
    ("published_score_mutated", True),
    ("source_audit_db_sha256", "missing"),
    ("contract", "unrecognized"),
    ("canonical_scoring_version", "SCORE-GEO-999"),
])
def test_fail_closed_if_source_not_physically_verified(field, replacement):
    replay = _replay()
    replay[field] = replacement
    with pytest.raises(ValueError):
        build_optional_seo_decision_matrix(replay)


def test_refuse_incomplete_scenario_universe_and_unmatched_dimensions():
    replay = _replay()
    del replay["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_PASS"]
    with pytest.raises(ValueError, match="scenario"):
        build_optional_seo_decision_matrix(replay)
    replay = _replay()
    del replay["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_PASS"]["DISCOVERY_ACCESS"]
    with pytest.raises(ValueError, match="dimensions"):
        build_optional_seo_decision_matrix(replay)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -1, 101, True])
def test_invalid_score_does_not_fabricate_delta(invalid):
    replay = _replay()
    replay["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_PASS"]["DISCOVERY_ACCESS"]["value"] = invalid
    output = build_optional_seo_decision_matrix(replay)
    row = next(row for row in output["rows"] if row["scenario"].endswith("_PASS")
               and row["dimension"] == "DISCOVERY_ACCESS")
    assert row["scenario_points"] is None
    assert row["delta_points"] is None
    assert row["interpretation"] == "UNVERIFIABLE"


def test_nondeterminable_confidence_and_missing_gate_never_report_no_change():
    replay = _replay()
    replay["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_PASS"]["OVERALL_READINESS"].pop(
        "readiness_limitations"
    )
    matrix = build_optional_seo_decision_matrix(replay)
    assert next(row for row in matrix["rows"] if row["dimension"] == "OVERALL_READINESS"
                and row["scenario"].endswith("_PASS"))["interpretation"] == "UNVERIFIABLE"


def test_existing_cli_switch_reuses_only_parity_verified_result(monkeypatch, capsys):
    from rasai import optional_seo_audit_replay as cli
    original = _replay()
    def offline_replay(*args, **kwargs):
        return deepcopy(original)
    monkeypatch.setattr(cli, "replay_optional_seo_from_audit", offline_replay)
    assert cli.main(["AUD-TEST", "--format", "decision-matrix"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["contract"] == "RASAI-SEO-POLICY-DECISION-602-001"
    assert output["new_scoring_version_approved"] is False
    assert len(output["rows"]) == 4
    assert cli.main(["AUD-TEST", "--format", "scenarios"]) == 0
    legacy = json.loads(capsys.readouterr().out)
    assert legacy["contract"] == "RASAI-SEO-POLICY-SENSITIVITY-602-001"
