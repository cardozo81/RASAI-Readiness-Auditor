from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai import external_measurement_runtime
from rasai.discovery import RobotsState, SitemapState
from rasai.domain import RuleResult
from rasai.m5 import _evaluate_robots, _evaluate_sitemaps
from rasai.m7 import _deterministic_outcome
from rasai.m21_web_performance import ExternalServiceError, PageSpeedInsightsClient
from rasai.m24_ai import _schema
from rasai.m24_scoring import _bounded_result
from rasai.scoring import _metadata


def _m2(*, robots: RobotsState, sitemaps: tuple[SitemapState, ...]):
    return SimpleNamespace(
        discovery=SimpleNamespace(
            robots=SimpleNamespace(state=robots, url="https://example.test/robots.txt"),
            sitemaps=tuple(
                SimpleNamespace(url=f"https://example.test/sitemap-{index}.xml", state=state, error=None)
                for index, state in enumerate(sitemaps)
            ),
        )
    )



def test_optional_seo_scenarios_recompute_score_coverage_confidence_and_gates_in_memory() -> None:
    from datetime import datetime, timezone

    from rasai.domain import DeviceContext, RuleExecution
    from rasai.optional_seo_score_scenarios_602 import (
        preview_optional_seo_policy_sensitivity,
    )
    from rasai.scoring_v004 import ScoreGeo004Engine

    audit_id = "AUD-SENSITIVITY-1"
    def row(number, rule, data):
        return RuleExecution(
            rule_execution_id=f"RULE-{number}",
            audit_id=audit_id,
            rule_id=rule,
            rule_version="fixture",
            page_id=None,
            snapshot_id=None,
            device=DeviceContext.MOBILE,
            result=RuleResult.WARNING,
            observed_value=data,
            expected_condition="fixture",
            evidence_ids=(),
            executed_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        )
    rules = (
        row(1, "BR-GEO-003", {"sitemaps": [{"state": "ABSENT"}]}),
        row(2, "BR-GEO-017", {"state": "ABSENT"}),
        row(3, "BR-GEO-013", {"canonicals": []}),
    )
    source = tuple((x.rule_execution_id, x.result, x.observed_value) for x in rules)
    result = preview_optional_seo_policy_sensitivity(
        audit_id, rules, device=DeviceContext.MOBILE,
    )
    assert result["optional_absence_executions"] == 3
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert result["new_scoring_version_approved"] is False
    baseline = result["scenarios"]["CANONICAL_SCORE_GEO_004"]
    pass_only = result["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_PASS"]
    not_applicable = result["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE"]
    canonical = ScoreGeo004Engine().score(
        audit_id=audit_id, executions=rules, devices=(DeviceContext.MOBILE,),
    )
    assert baseline["DISCOVERY_ACCESS"]["value"] == pytest.approx(
        next(s.value for s in canonical.scores if s.dimension == "DISCOVERY_ACCESS")
    )
    assert pass_only["DISCOVERY_ACCESS"]["value"] > baseline["DISCOVERY_ACCESS"]["value"]
    assert pass_only["INDEXABILITY"]["value"] > baseline["INDEXABILITY"]["value"]
    assert not_applicable["DISCOVERY_ACCESS"]["coverage"] != baseline["DISCOVERY_ACCESS"]["coverage"]
    assert "confidence" in not_applicable["OVERALL_READINESS"]
    assert "readiness_limitations" in not_applicable["OVERALL_READINESS"]
    assert source == tuple((x.rule_execution_id, x.result, x.observed_value) for x in rules)


def test_optional_seo_scenario_malformed_and_conflict_never_promote_to_pass() -> None:
    from datetime import datetime, timezone

    from rasai.domain import DeviceContext, RuleExecution
    from rasai.optional_seo_score_scenarios_602 import (
        preview_optional_seo_policy_sensitivity,
    )

    def row(audit, identifier, raw):
        return RuleExecution(
            rule_execution_id=identifier,
            audit_id=audit,
            rule_id="BR-GEO-013",
            rule_version="fixture",
            page_id=None,
            snapshot_id=None,
            device=DeviceContext.MOBILE,
            result=RuleResult.WARNING,
            observed_value=raw,
            expected_condition=None,
            evidence_ids=(),
            executed_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        )
    conflict = row(
        "AUD-EXAMPLE", "RULE-A",
        {"declared": ["/a", "/b"], "invalid": [], "normalized": [
            "https://example.test/a", "https://example.test/b",
        ]},
    )
    preview = preview_optional_seo_policy_sensitivity(
        "AUD-EXAMPLE", (conflict,), device=DeviceContext.MOBILE,
    )
    assert preview["optional_absence_executions"] == 0
    assert preview["scenarios"]["CANONICAL_SCORE_GEO_004"] == (
        preview["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_PASS"]
    )
    with pytest.raises(ValueError, match="ambiguous"):
        preview_optional_seo_policy_sensitivity(
            "AUD-EXAMPLE", (conflict, conflict), device=DeviceContext.MOBILE,
        )
    with pytest.raises(ValueError, match="audit scope"):
        preview_optional_seo_policy_sensitivity(
            "AUD-OTHER", (conflict,), device=DeviceContext.MOBILE,
        )




def test_optional_policy_replay_requires_exact_persisted_sari_parity(tmp_path) -> None:
    import json
    import sqlite3
    from datetime import datetime, timezone

    from rasai.domain import DeviceContext, RuleExecution
    from rasai.optional_seo_audit_replay_602 import replay_optional_seo_from_audit
    from rasai.scoring_v004 import ScoreGeo004Engine

    folder = tmp_path / "AUD-SCENARIO1"
    folder.mkdir()
    db = folder / "audit.db"
    stamp = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)
    fixtures = (
        RuleExecution(
            rule_execution_id=f"RULE-{number}", audit_id=folder.name,
            rule_id=rule_id, rule_version="fixture", page_id=None,
            snapshot_id=None, device=DeviceContext.MOBILE,
            result=RuleResult.WARNING, observed_value=evidence,
            expected_condition=None, evidence_ids=(), executed_at=stamp,
        )
        for number, (rule_id, evidence) in enumerate(
            (
                ("BR-GEO-003", {"sitemaps": [{"state": "ABSENT"}]}),
                ("BR-GEO-017", {"state": "ABSENT"}),
                ("BR-GEO-013", {"canonicals": []}),
            ),
            start=1,
        )
    )
    records = tuple(fixtures)
    calculated = ScoreGeo004Engine().score(
        audit_id=folder.name, executions=records, devices=(DeviceContext.MOBILE,),
    )
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE audits(audit_id TEXT)")
        con.execute("INSERT INTO audits VALUES (?)", (folder.name,))
        con.execute(
            "CREATE TABLE rule_executions("
            "rule_execution_id TEXT,audit_id TEXT,rule_id TEXT,rule_version TEXT,"
            "page_id TEXT,snapshot_id TEXT,device TEXT,result TEXT,"
            "observed_value TEXT,expected_condition TEXT,evidence_ids TEXT,"
            "executed_at TEXT,error TEXT)"
        )
        con.execute(
            "CREATE TABLE scores(dimension TEXT,value REAL,coverage REAL,"
            "confidence TEXT,consolidation_status TEXT,scoring_version TEXT,"
            "audit_id TEXT,device TEXT,limitations TEXT)"
        )
        for record in records:
            con.execute(
                "INSERT INTO rule_executions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.rule_execution_id, record.audit_id, record.rule_id,
                    record.rule_version, record.page_id, record.snapshot_id,
                    record.device.value, record.result.value,
                    json.dumps(record.observed_value), record.expected_condition,
                    json.dumps(record.evidence_ids), record.executed_at.isoformat(),
                    record.error,
                ),
            )
        for score in (*calculated.scores, calculated.overall_by_device[DeviceContext.MOBILE]):
            con.execute(
                "INSERT INTO scores VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    score.dimension, score.value, score.coverage,
                    score.confidence.value, score.consolidation_status.value,
                    score.scoring_version, folder.name, score.device.value,
                    json.dumps(score.limitations),
                ),
            )
    original = db.read_bytes()
    verified = replay_optional_seo_from_audit(folder)
    assert verified["source_audit_db_replay_parity"] == "VERIFIED_SCORE_GEO_004"
    assert verified["optional_absence_executions"] == 3
    assert verified["provider_requests"] == verified["audit_writes"] == 0
    assert verified["published_score_mutated"] is False
    assert db.read_bytes() == original

    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE scores SET value=75 WHERE dimension='INDEXABILITY'"
        )
    tampered = db.read_bytes()
    with pytest.raises(ValueError, match="baseline numeric parity"):
        replay_optional_seo_from_audit(folder)
    assert db.read_bytes() == tampered

    # Even if the raw score matches, changing readiness status must not
    # pass the physical contract parity gate.
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE scores SET value=? WHERE dimension='INDEXABILITY'",
            (next(x.value for x in calculated.scores if x.dimension == "INDEXABILITY"),),
        )
        con.execute(
            "UPDATE scores SET limitations=? WHERE dimension='OVERALL_READINESS'",
            (json.dumps(["READINESS_STATUS:READY", "CRITICAL_GATE:INDEXABILITY:PASS"]),),
        )
    with pytest.raises(ValueError, match="readiness gate parity"):
        replay_optional_seo_from_audit(folder)



def test_absent_discovery_resources_are_not_positive_passes() -> None:
    m2 = _m2(robots=RobotsState.ABSENT, sitemaps=(SitemapState.ABSENT,))
    assert _evaluate_robots(m2).result is RuleResult.WARNING
    assert _evaluate_sitemaps(m2).result is RuleResult.WARNING


def test_invalid_sitemap_is_materially_unfavorable() -> None:
    m2 = _m2(robots=RobotsState.OBTAINED, sitemaps=(SitemapState.INVALID,))
    assert _evaluate_sitemaps(m2).result is RuleResult.FAIL


def test_discovery_weights_are_static_and_ai_shares_deterministic_group() -> None:
    sitemap = _metadata("BR-GEO-003")
    sitemap_ai = _metadata("BR-GEO-055")
    robots = _metadata("BR-GEO-017")
    robots_ai = _metadata("BR-GEO-056")
    assert sitemap.dimension == sitemap_ai.dimension == "DISCOVERY_ACCESS"
    # Three percent of Discovery is reserved for positive-only Common Crawl
    # corroboration, so every pre-existing technical group is scaled by 0.97 while
    # preserving its relative weight whenever the external signal is absent.
    assert sitemap.weight == sitemap_ai.weight == pytest.approx(0.0485)
    assert sitemap.scoring_group == sitemap_ai.scoring_group == "SITEMAP"
    assert robots.dimension == robots_ai.dimension == "DISCOVERY_ACCESS"
    assert robots.weight == robots_ai.weight == pytest.approx(0.1455)
    assert robots.scoring_group == robots_ai.scoring_group == "ROBOTS"
    assert sitemap.evidence_role != sitemap_ai.evidence_role
    assert robots.evidence_role != robots_ai.evidence_role


def test_missing_jsonld_is_measured_as_modest_warning() -> None:
    outcome = _deterministic_outcome(
        "BR-GEO-034",
        "Example",
        {"present": False, "invalid_blocks": 0, "types": []},
        "EV-1",
    )
    assert outcome is not None
    assert outcome.evaluation.result is RuleResult.WARNING
    assert _metadata("BR-GEO-034").warning_factor == pytest.approx(0.80)


def test_technical_ai_schema_never_exposes_arbitrary_weight() -> None:
    schema = _schema()
    resource = schema["properties"]["resource_assessments"]["items"]
    assert resource["properties"]["verdict"]["enum"] == ["POSITIVE", "NEUTRAL", "NEGATIVE"]
    assert "weight" not in resource["properties"]


def test_low_confidence_ai_cannot_create_hard_pass_or_fail() -> None:
    assert _bounded_result("POSITIVE", 0.59) is RuleResult.WARNING
    assert _bounded_result("NEGATIVE", 0.59) is RuleResult.WARNING
    assert _bounded_result("NEGATIVE", 0.90) is RuleResult.FAIL


def test_pagespeed_does_not_retry_transient_failure(monkeypatch) -> None:
    external_measurement_runtime.install()
    calls = []

    def fake_request_json(**kwargs):
        calls.append(kwargs)
        raise ExternalServiceError("PAGESPEED_INSIGHTS", "temporary", http_status=500)

    monkeypatch.setattr("rasai.m21_web_performance._request_json", fake_request_json)
    with pytest.raises(ExternalServiceError):
        PageSpeedInsightsClient("key").run(
            url="https://example.test/",
            strategy="mobile",
            categories=("performance",),
            timeout_seconds=1.0,
        )
    assert len(calls) == 1
