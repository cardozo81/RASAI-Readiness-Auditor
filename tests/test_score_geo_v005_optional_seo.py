"""#602: versioned optional SEO scoring, deterministic and source-preserving."""
from __future__ import annotations

from datetime import datetime, timezone

from rasai.domain import DeviceContext, RuleExecution, RuleResult
from rasai.optional_seo_score_scenarios import preview_optional_seo_policy_sensitivity
from rasai.score_geo import SCORING_VERSION
from rasai.scoring_v004 import ScoreGeo004Engine
from rasai.scoring_v005 import ScoreGeo005Engine, _effective_v005_execution


def _row(number: int, rule: str, result: RuleResult, data: dict) -> RuleExecution:
    return RuleExecution(
        rule_execution_id=f"REX-602-{number}", audit_id="AUD-602-005",
        rule_id=rule, rule_version="1", page_id=None, snapshot_id=None,
        device=DeviceContext.MOBILE, result=result, observed_value=data,
        expected_condition="fixture", evidence_ids=(f"EV-602-{number}",),
        executed_at=datetime(2026, 10, 19, tzinfo=timezone.utc),
    )


def _score(rows: tuple[RuleExecution, ...], version: int):
    engine = ScoreGeo005Engine() if version == 5 else ScoreGeo004Engine()
    return engine.score(
        audit_id="AUD-602-005", executions=rows,
        devices=(DeviceContext.MOBILE,),
    )


def _values(result) -> dict:
    return {
        score.dimension: (score.value, score.coverage, score.confidence,
                          score.consolidation_status)
        for score in (*result.scores, *result.overall_by_device.values())
    }


def test_005_optional_absence_matches_golden_not_applicable_sensitivity():
    rows = (
        _row(1, "BR-GEO-003", RuleResult.WARNING,
             {"sitemaps": [{"state": "ABSENT", "error": None}]}),
        _row(2, "BR-GEO-013", RuleResult.WARNING, {"canonicals": []}),
        _row(3, "BR-GEO-017", RuleResult.WARNING, {"state": "ABSENT"}),
        _row(4, "BR-GEO-005", RuleResult.PASS, {}),
        _row(5, "BR-GEO-011", RuleResult.PASS, {}),
    )
    unchanged = tuple((r.result, dict(r.observed_value)) for r in rows)
    old = _score(rows, 4)
    new = _score(rows, 5)
    expected = preview_optional_seo_policy_sensitivity(
        "AUD-602-005", rows, device=DeviceContext.MOBILE,
    )["scenarios"]["SENSITIVITY_OPTIONAL_ABSENCE_NOT_APPLICABLE"]
    assert SCORING_VERSION == "SCORE-GEO-005"
    assert all(row.scoring_version == "SCORE-GEO-005"
               for row in (*new.scores, *new.overall_by_device.values()))
    assert all(row.scoring_version == "SCORE-GEO-004"
               for row in (*old.scores, *old.overall_by_device.values()))
    for dimension, snapshot in expected.items():
        actual = next(
            (s for s in (*new.scores, *new.overall_by_device.values())
             if s.dimension == dimension), None,
        )
        assert actual is not None
        assert actual.value == snapshot["value"]
        assert actual.coverage == snapshot["coverage"]
        assert str(actual.confidence) == snapshot["confidence"]
        assert str(actual.consolidation_status) == snapshot["consolidation_status"]
    assert tuple((r.result, dict(r.observed_value)) for r in rows) == unchanged
    assert _values(new) != _values(old)


def test_005_reclassifies_only_evidenced_absence_not_conflict_or_unknown():
    rows = (
        _row(1, "BR-GEO-003", RuleResult.FAIL,
             {"sitemaps": [{"state": "INVALID", "error": None}]}),
        _row(2, "BR-GEO-013", RuleResult.FAIL,
             {"declared": ["https://a.test/", "https://b.test/"],
              "normalized": ["https://a.test/", "https://b.test/"], "invalid": []}),
        _row(3, "BR-GEO-017", RuleResult.UNKNOWN,
             {"state": "NETWORK_ERROR"}),
        _row(4, "BR-GEO-003", RuleResult.WARNING,
             {"sitemaps": [{"state": "HTTP_ERROR", "error": None}]}),
        _row(5, "BR-GEO-013", RuleResult.WARNING,
             {"canonicals": [], "error": "network"}),
        _row(6, "BR-GEO-017", RuleResult.PASS, {"state": "OBTAINED"}),
    )
    for row in rows:
        assert _effective_v005_execution(row) is row
    assert _values(_score(rows, 5)) == _values(_score(rows, 4))


def test_005_optionally_absent_robots_sitemap_canonical_no_pass_credit():
    for rule, observed in (
        ("BR-GEO-003", {"sitemaps": [{"state": "ABSENT"}]}),
        ("BR-GEO-013", {"canonicals": []}),
        ("BR-GEO-017", {"state": "ABSENT"}),
    ):
        source = _row(1, rule, RuleResult.WARNING, observed)
        effective = _effective_v005_execution(source)
        assert effective.result is RuleResult.NOT_APPLICABLE
        assert effective.observed_value["source_rule_result"] == "WARNING"
        assert source.result is RuleResult.WARNING
        assert _effective_v005_execution(effective) == effective


def test_faq_normative_option_a_keeps_existing_warning_semantics():
    """No FAQ advisory-only observation may mutate 039/049 score inputs."""
    from rasai.score_geo import rule_contract
    from rasai.faq_transition_policy import compare_faq_dom_views

    for rule, group in (
        ("BR-GEO-039", "PRIMARY_ANSWERS"),
        ("BR-GEO-049", "INTENT_GAPS"),
    ):
        contract = rule_contract(rule)
        assert contract.warning_factor == 0.5
        assert contract.scoring_group == group

    observed = compare_faq_dom_views(
        '<button aria-controls="faq-answer" aria-expanded="false">FAQ</button>',
        '<button aria-controls="faq-answer" aria-expanded="true">FAQ</button>'
        '<div id="faq-answer">Resposta observada depois</div>',
        target_id="faq-answer",
        before_url="https://example.test/faq",
        later_url="https://example.test/faq",
    )
    assert observed["status"] == "DESCRIPTIVE_SNAPSHOT_PAIR_ONLY"
    assert observed["score_change_authorized"] is False
    assert observed["crawler_discovery_verified"] is False
    assert observed["editorial_answer_absence_proven"] is False

    persisted = (
        _row(1, "BR-GEO-038", RuleResult.PASS, {}),
        _row(2, "BR-GEO-039", RuleResult.WARNING, {}),
        _row(3, "BR-GEO-048", RuleResult.PASS, {}),
        _row(4, "BR-GEO-049", RuleResult.WARNING, {}),
    )
    assert _values(_score(persisted, 5)) == _values(_score(persisted, 4))
    assert persisted[1].result is RuleResult.WARNING
    assert persisted[3].result is RuleResult.WARNING

    not_evidenced = (
        _row(1, "BR-GEO-038", RuleResult.PASS, {}),
        _row(2, "BR-GEO-039", RuleResult.UNKNOWN, {}),
        _row(3, "BR-GEO-048", RuleResult.PASS, {}),
        _row(4, "BR-GEO-049", RuleResult.UNKNOWN, {}),
    )
    assert _values(_score(not_evidenced, 5)) != _values(_score(persisted, 5))
