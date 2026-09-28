from __future__ import annotations

import inspect

from rasai import (
    ai_dependency_runtime,
    core_reprocessing,
    m2,
    m3,
    m5,
    m6,
    m21_web_performance,
    pre_scoring_rules,
    reprocess_ai,
    reprocess_measurements,
    reprocess_policy,
    technical_ai_eligibility,
)


def _source(value: object) -> str:
    return inspect.getsource(value)


def test_initial_and_rpr_share_canonical_core_stage_primitives() -> None:
    assert "persist_http_observation" in _source(m2.execute_m2)
    assert "build_http_rule_executions" in _source(m2.execute_m2)
    assert "persist_http_observation" in _source(core_reprocessing._recover_http)
    assert "build_http_rule_executions" in _source(core_reprocessing._recover_http)

    assert "persist_render_capture" in _source(m3.execute_m3)
    assert "persist_render_capture" in _source(core_reprocessing._recover_render)

    assert "execute_m5_foundation_scope" in _source(m5.execute_m5)
    assert "execute_m5_foundation_scope" in _source(core_reprocessing._recover_discovery)
    assert "execute_m5_page_scope" in _source(m5.execute_m5)
    assert "execute_m5_page_scope" in _source(core_reprocessing._recompute_deterministic_snapshot)

    assert "execute_m6_snapshot_scope" in _source(m6.execute_m6)
    assert "execute_m6_snapshot_scope" in _source(core_reprocessing._recompute_deterministic_snapshot)




def test_initial_and_rpr_share_deep_analysis_fulfillment_dependency_contract() -> None:
    initial = _source(ai_dependency_runtime._install_deep_analysis_gate)
    recovery = _source(reprocess_policy.blocking_dependencies)
    assert "deep_analysis_fulfillment_dependency_state" in initial
    assert "deep_analysis_dependency_items" in recovery




def test_initial_and_rpr_share_technical_ai_evidence_gate() -> None:
    initial = _source(technical_ai_eligibility._wrap_m24)
    recovery = _source(technical_ai_eligibility._correct_reprocess_diagnostics)
    assert "technical_evidence_ready" in initial
    assert "technical_evidence_ready" in recovery
    assert "DISCOVERY_ACQUISITION" in _source(reprocess_policy.blocking_dependencies)


def test_initial_and_rpr_share_canonical_pre_score_integrity_rule() -> None:
    assert "execute_finding_integrity_rule" in _source(pre_scoring_rules.execute_pre_scoring_rules)
    assert "execute_finding_integrity_rule" in _source(reprocess_ai._refresh_integrity_rule)


def test_initial_and_rpr_share_m21_observation_and_run_classification() -> None:
    initial = _source(m21_web_performance.execute_m21)
    recovery = _source(reprocess_measurements.recover_web_performance)
    for primitive in (
        "build_web_performance_observation",
        "summarize_web_performance_run",
    ):
        assert primitive in initial
        assert primitive in recovery


def test_apdex_recovery_uses_canonical_measurement_classifiers_and_summaries() -> None:
    synthetic = _source(reprocess_measurements.recover_synthetic_apdex)
    assert "m23.execute_m23_apdex" in synthetic
    assert "m23._sample" in synthetic
    assert "m23._summary" in synthetic

    experience = _source(reprocess_measurements.recover_experience_apdex)
    assert "m25.execute_m25_experience" in experience
    assert "m25.classify_measurement" in experience
    assert "m25._summary" in experience


def test_m21_partial_context_semantics_are_identical_for_initial_and_rpr() -> None:
    assert m21_web_performance.summarize_web_performance_run(
        context_count=1,
        usable_contexts=1,
        partial_contexts=1,
    ) == ("PARTIAL", "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE")
    assert m21_web_performance.summarize_web_performance_run(
        context_count=1,
        usable_contexts=1,
        partial_contexts=0,
    ) == ("SUCCESS", None)
    assert m21_web_performance.summarize_web_performance_run(
        context_count=1,
        usable_contexts=0,
        partial_contexts=0,
    ) == ("UNAVAILABLE", "EXTERNAL_WEB_PERFORMANCE_UNAVAILABLE")
