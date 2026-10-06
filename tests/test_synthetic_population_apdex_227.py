from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from rasai.m25_apdex_experience import ExperienceApdexConfig, UxMeasurement, execute_m25_experience
from rasai.synthetic_population_apdex import (
    StratumStatistics,
    aggregate_population_statistics,
    allocate_population_samples,
    parse_population_profile,
)
from tests.test_m25_synthetic_user_experience import _workspace


def _profile_json() -> str:
    return json.dumps({
        "population_profile_id": "POP-MOBILE-CONTROLLED",
        "profile_version": "1",
        "weight_source": "RASAI_OPERATOR",
        "target_samples_per_page": 4,
        "strata": [
            {
                "stratum_id": "constrained",
                "weight": 50,
                "device": "MOBILE",
                "client_profile_id": "mobile-balanced-chromium",
                "hardware_profile_id": "mobile-entry",
                "network_profile_id": "mobile-3g-constrained",
                "session_mode": "cold",
            },
            {
                "stratum_id": "fast",
                "weight": 50,
                "device": "MOBILE",
                "client_profile_id": "mobile-balanced-chromium",
                "hardware_profile_id": "mobile-premium",
                "network_profile_id": "mobile-4g-fast",
                "session_mode": "warm",
            },
        ],
    })


def test_population_profile_is_strict_weighted_and_same_device() -> None:
    profile = parse_population_profile(
        _profile_json(), expected_device="MOBILE", default_target_samples=100
    )
    assert profile.population_profile_id == "POP-MOBILE-CONTROLLED"
    assert sum(item.weight for item in profile.strata) == 100
    assert allocate_population_samples(5, profile.strata) == {
        "constrained": 3,
        "fast": 2,
    }

    payload = json.loads(_profile_json())
    payload["strata"][0]["device"] = "DESKTOP"
    with pytest.raises(ValueError, match="device MOBILE"):
        parse_population_profile(
            json.dumps(payload), expected_device="MOBILE", default_target_samples=4
        )

    payload = json.loads(_profile_json())
    payload["strata"][0]["geolocation"] = {"lat": -30.0, "lon": -51.0}
    with pytest.raises(ValueError, match="campos não suportados"):
        parse_population_profile(
            json.dumps(payload), expected_device="MOBILE", default_target_samples=4
        )


def test_weighted_aggregate_and_sampling_uncertainty_are_deterministic() -> None:
    profile = parse_population_profile(
        _profile_json(), expected_device="MOBILE", default_target_samples=4
    )
    stats = {
        "constrained": StratumStatistics(
            "constrained", 2, 2, 0, 0, 0, 2, 0.0,
            5000.0, 5000.0, 5000.0, 5000.0, (5000.0, 5000.0),
        ),
        "fast": StratumStatistics(
            "fast", 2, 2, 0, 2, 0, 0, 1.0,
            500.0, 500.0, 500.0, 500.0, (500.0, 500.0),
        ),
    }
    result = aggregate_population_statistics(profile, stats)
    assert result.status == "SUCCESS"
    assert result.weighted_apdex == 0.5
    assert result.observed_weight_percent == 100.0
    assert result.weighted_satisfied_share == 0.5
    assert result.weighted_frustrated_share == 0.5
    assert result.median_ms == 500.0
    assert result.p75_ms == 5000.0
    assert result.standard_error == 0.0
    assert result.ci95_low == result.ci95_high == 0.5

    partial = dict(stats)
    partial["fast"] = StratumStatistics(
        "fast", 2, 0, 2, 0, 0, 0, None,
        None, None, None, None, (),
    )
    partial_result = aggregate_population_statistics(profile, partial)
    assert partial_result.status == "PARTIAL"
    assert partial_result.observed_weight_percent == 50.0
    assert partial_result.weighted_apdex == 0.0


class _PopulationGateway:
    def environment(self):
        return {"system": "TEST", "chromium_version": "test", "m25_profile_version": "test"}

    def close(self):
        return None

    def measure(self, *, profile, **_kwargs):
        duration = 5000.0 if profile.hardware_profile_id == "mobile-entry" else 500.0
        return UxMeasurement(
            status="SUCCESS",
            user_action_duration_ms=duration,
            navigation_duration_ms=duration,
            load_event_end_ms=duration,
            lcp_ms=duration,
            http_status=200,
            final_url="https://example.com/",
        )


def test_population_execution_is_additive_and_does_not_replace_baseline(tmp_path: Path) -> None:
    workspace = _workspace(str(tmp_path))
    config = ExperienceApdexConfig(
        enabled=True,
        target_samples_per_page=4,
        max_attempts_per_page=4,
        max_pages=1,
        device_mix=(("MOBILE", 100.0),),
        satisfied_threshold_seconds=1.0,
        frustrated_threshold_seconds=4.0,
        settle_seconds=0.1,
        delay_seconds=0.0,
        concurrency=1,
        population_profile_json=_profile_json(),
    )
    result = execute_m25_experience(
        audit_id="AUD-M25",
        workspace=workspace,
        config=config,
        gateway_factory=_PopulationGateway,
    )
    assert result.status == "SUCCESS"

    with sqlite3.connect(workspace.database) as db:
        baseline = db.execute(
            "SELECT apdex_score FROM synthetic_ux_apdex_summaries "
            "WHERE audit_id='AUD-M25' AND device='POPULATION'"
        ).fetchone()
        population = db.execute(
            "SELECT weighted_apdex,observed_weight_percent,status "
            "FROM synthetic_population_apdex_summaries WHERE audit_id='AUD-M25'"
        ).fetchone()
        strata = db.execute(
            "SELECT stratum_id,weight,target_samples,valid_samples,apdex_score "
            "FROM synthetic_population_apdex_strata WHERE audit_id='AUD-M25' ORDER BY stratum_id"
        ).fetchall()
        run = db.execute(
            "SELECT population_profile_id,runtime_version,weight_source,device "
            "FROM synthetic_population_apdex_runs WHERE audit_id='AUD-M25'"
        ).fetchone()
        baseline_config = json.loads(db.execute(
            "SELECT configuration FROM synthetic_ux_apdex_runs WHERE audit_id='AUD-M25'"
        ).fetchone()[0])

    assert baseline == (1.0,)
    assert population == (0.5, 100.0, "SUCCESS")
    assert strata == [
        ("constrained", 50.0, 2, 2, 0.0),
        ("fast", 50.0, 2, 2, 1.0),
    ]
    assert run == (
        "POP-MOBILE-CONTROLLED",
        "SYNTHETIC-POPULATION-001",
        "RASAI_OPERATOR",
        "MOBILE",
    )
    assert json.loads(baseline_config["population_profile_json"])["population_profile_id"] == "POP-MOBILE-CONTROLLED"
