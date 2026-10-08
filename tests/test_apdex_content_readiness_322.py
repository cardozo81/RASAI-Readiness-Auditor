"""#322: deterministic and noninvasive, no Playwright or paid providers."""
from __future__ import annotations

from rasai.apdex_content_readiness_observation import (
    METHOD_VERSION, PrimaryContentCheckpoint as C, classify_primary_content_readiness as classify,
)


def observation(architecture="CSR_SPA", *, expired=False, enabled=True, samples=None, context="CTX-A"):
    return classify(
        sample_id="M25-SAMPLE-1",
        context_id=context,
        architecture=architecture,
        load_ms=300.0,
        enabled=enabled,
        window_ms=1200,
        window_expired=expired,
        checkpoints=() if samples is None else samples,
    )


def cp(at, text, heading=30, skeleton=False, context="CTX-A"):
    return C("M25-SAMPLE-1", context, at, text, heading, skeleton)


def test_spa_materialized_later_is_separate_from_navigation_load():
    value = observation(samples=[cp(310, 0), cp(740, 400), cp(860, 410)])
    assert value.status == "OBSERVED"
    assert value.primary_content_ms == 740.0
    assert value.post_load_delta_ms == 440.0
    assert value.method_version == METHOD_VERSION


def test_hydrated_early_content_does_not_invent_negative_latency():
    value = observation("HYDRATED", samples=[cp(200, 450), cp(320, 451)])
    assert value.status == "OBSERVED"
    assert value.post_load_delta_ms == 0.0


def test_skeleton_cannot_count_as_ready_and_timeout_is_censored():
    value = observation(samples=[cp(550, 800, skeleton=True), cp(1490, 900, skeleton=True)], expired=True)
    assert value.status == "TIMEOUT"
    assert value.post_load_delta_ms is None


def test_static_unknown_opt_out_do_not_trigger_inferred_observations():
    assert observation("STATIC_OR_SSR", expired=True).status == "NOT_APPLICABLE"
    assert observation("UNKNOWN", expired=True).status == "NOT_APPLICABLE"
    assert observation(enabled=False, samples=[cp(500, 900)]).status == "NOT_APPLICABLE"


def test_mixed_unstable_or_missing_content_is_not_observed():
    assert observation("MIXED", samples=[cp(340, 450)]).status == "NOT_OBSERVED"
    assert observation(expired=True).status == "TIMEOUT"


def test_cross_sample_context_is_rejected_not_assumed_temporally_comparable():
    val = observation(samples=[cp(500, 900, context="CTX-OTHER")])
    assert val.status == "ERROR"
    assert val.post_load_delta_ms is None


def test_invalid_monotonic_order_and_bounds_are_rejected():
    assert observation(samples=[cp(600, 450), cp(500, 450)]).status == "ERROR"
    assert observation(samples=[cp(1600, 450)]).status == "ERROR"


def test_no_legacy_apdex_formula_or_database_dependency():
    from rasai import apdex_content_readiness_observation as module
    assert not any(
        name.startswith("synthetic_apdex") or name.startswith("synthetic_ux_apdex")
        for name in module.__dict__
    )


def test_intervening_skeleton_resets_stability():
    value = observation(samples=[cp(500, 500), cp(560, 600, skeleton=True), cp(650, 500)])
    assert value.status == 'NOT_OBSERVED'
    stable = observation(samples=[cp(500, 500), cp(560, 600, skeleton=True), cp(650, 500), cp(770, 520)])
    assert stable.status == 'OBSERVED'
    assert stable.primary_content_ms == 650


def test_apdex_report_discloses_load_vs_main_content_without_fabricated_metric():
    from rasai.catalog_report_page import _apdex_readiness_notice

    for catalog_id in ("CAT-06", "CAT-07"):
        message = _apdex_readiness_notice(catalog_id)
        assert "Carregamento não é prontidão do conteúdo" in message
        assert "não mede o instante de conteúdo principal pronto" in message
        assert "same-sample de prontidão validada" in message
        assert "capture-context.html" in message
        assert "cat-04.html" in message
    assert _apdex_readiness_notice("CAT-05") == ""
