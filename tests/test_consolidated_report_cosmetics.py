from rasai.consolidation.consolidated_report_enrichment import _rules_page
from rasai.consolidation.models import ConsolidatedData, ConsolidationFilter, FindingSummary
from rasai.consolidation.presentation import (
    _candidate_cost_html,
    _is_explicit_zero_cost,
    _presentation_css,
    _render_usage,
    finalize_reader_experience,
)
from rasai.consolidation.reporting import (
    _performance_tone,
    _render_html,
    _score_tone,
    _state_text_html,
)
from rasai.consolidation.temporal_apdex import _apdex_result_html, _apdex_tone


def _empty_data() -> ConsolidatedData:
    return ConsolidatedData(
        filters=ConsolidationFilter(),
        audits=(),
        source_fingerprint="source",
        scores=(),
        performance=(),
        apdex=(),
        findings=FindingSummary(
            severity_counts={},
            category_counts={},
            affected_pages=0,
            observations=0,
        ),
        unique_urls=0,
        date_min=None,
        date_max=None,
    )


def test_consolidated_report_uses_catalog_visual_identity() -> None:
    html = _render_html(_empty_data(), "2026-09-21T12:00:00-03:00", "fingerprint")
    for token in (
        "--bg:#f6f8fb",
        "--surface:#fff",
        "--ink:#172033",
        "--secondary-ink:#475467",
        "--muted:#667085",
        "--line:#e2e7ef",
        "--blue:#3157c8",
        "--green:#187a45",
        "--amber:#9a6200",
        "--orange:#9a5b13",
        "--red:#b42318",
        "--nav:#111827",
        "--radius:14px",
    ):
        assert token in html
    assert ".result-value.good{color:var(--green)}" in html
    assert ".result-value.warn{color:var(--amber)}" in html
    assert ".result-value.low{color:var(--orange)}" in html
    assert ".result-value.bad{color:var(--red)}" in html


def test_rules_reference_uses_same_visual_identity() -> None:
    html = _rules_page({"rule_reference": ()})
    for token in (
        "--bg:#f6f8fb",
        "--surface:#fff",
        "--ink:#172033",
        "--secondary-ink:#475467",
        "--green:#187a45",
        "--amber:#9a6200",
        "--red:#b42318",
        "--nav:#111827",
        "--radius:14px",
    ):
        assert token in html
    assert "font:15px/1.5 Inter" in html


def test_sari_visual_ranges_follow_presentation_contract() -> None:
    assert _score_tone(90) == "good"
    assert _score_tone(75) == "good"
    assert _score_tone(60) == "warn"
    assert _score_tone(40) == "low"
    assert _score_tone(39.99) == "bad"
    assert _score_tone(None) == "neutral"


def test_performance_visual_ranges_are_limited_to_primary_metrics() -> None:
    assert _performance_tone("Lighthouse Performance", 90) == "good"
    assert _performance_tone("Lighthouse Performance", 89) == "warn"
    assert _performance_tone("Lighthouse Performance", 49) == "bad"
    assert _performance_tone("LCP de campo (p75)", 2500) == "good"
    assert _performance_tone("LCP de campo (p75)", 4001) == "bad"
    assert _performance_tone("INP de campo (p75)", 200) == "good"
    assert _performance_tone("INP de campo (p75)", 501) == "bad"
    assert _performance_tone("CLS de campo (p75)", 0.1) == "good"
    assert _performance_tone("CLS de campo (p75)", 0.26) == "bad"
    assert _performance_tone("FCP de laboratório", 1200) == "neutral"


def test_neutral_states_use_dark_gray_text_without_status_badge() -> None:
    for value in ("Automático", "Não aplicável", "Não determinado", "Não determinável"):
        rendered = _state_text_html(value)
        assert "state-text neutral" in rendered
        assert "badge" not in rendered
        assert "pill" not in rendered


def test_temporal_apdex_uses_same_font_only_result_ranges() -> None:
    assert _apdex_tone(0.85) == "good"
    assert _apdex_tone(0.70) == "warn"
    assert _apdex_tone(0.69) == "bad"
    assert "result-value good" in _apdex_result_html(0.94)
    assert "result-value warn" in _apdex_result_html(0.70)
    assert "result-value bad" in _apdex_result_html(0.50)


def test_specialist_layer_removes_semantic_background_badges() -> None:
    css = _presentation_css()
    assert ".status-pill,.priority-badge,.signal-key,.ai-origin" in css
    assert ".decision-state.good,.rasai-state-chip.state-good" in css
    assert "background:transparent!important" in css
    assert ".rasai-state-chip.state-neutral{color:var(--secondary-ink);font-weight:400}" in css
    assert ".decision-hero{background:#fff;border:1px solid var(--line);border-radius:14px" in css


def test_zero_cost_ai_usage_uses_light_gray_for_cost_and_input_output_tokens() -> None:
    attempts = [{
        "attempt_no": 1,
        "round_no": 1,
        "provider": "TEST",
        "model": "model",
        "reasoning": "LOW",
        "status": "SUCCESS",
        "input_tokens": 120,
        "output_tokens": 42,
        "estimated_cost": 0,
        "currency": "USD",
        "duration_ms": 10,
    }]
    html = _render_usage(attempts)
    assert _is_explicit_zero_cost(0) is True
    assert "<span class='no-cost-value'>USD 0.00000000</span>" in html
    assert "<span class='no-cost-value'>120</span>" in html
    assert "<span class='no-cost-value'>42</span>" in html


def test_unpriced_ai_usage_is_not_presented_as_zero_cost() -> None:
    attempts = [{
        "attempt_no": 1,
        "round_no": 1,
        "provider": "TEST",
        "model": "model",
        "reasoning": "LOW",
        "status": "SUCCESS",
        "input_tokens": 120,
        "output_tokens": 42,
        "estimated_cost": None,
        "currency": "USD",
        "duration_ms": 10,
    }]
    html = _render_usage(attempts)
    assert _is_explicit_zero_cost(None) is False
    assert "<span class='no-cost-value'>120</span>" not in html
    assert "<span class='no-cost-value'>42</span>" not in html
    assert "1 tentativa(s) sem custo calculável" in html


def test_zero_cost_candidate_is_also_visually_secondary() -> None:
    rendered = _candidate_cost_html({
        "estimated_cost": 0,
        "currency": "USD",
    })
    assert rendered == "<span class='no-cost-value'>USD 0.00000000</span>"


def test_final_reader_layer_keeps_state_chips_font_only() -> None:
    html = "<html><head></head><body><header><h1>CONS</h1></header><main></main></body></html>"
    rendered = finalize_reader_experience(html, None)
    assert "rasai-cons-header-alignment" in rendered
    assert ".rasai-status-badge,.rasai-state-chip{display:inline;padding:0;border:0!important;border-radius:0;background:transparent!important" in rendered
    assert ".rasai-state-chip.state-neutral,.state-neutral.rasai-status-badge{color:var(--secondary-ink)!important;font-weight:400}" in rendered


def test_deterministic_longitudinal_metrics_use_font_only_signal_classes() -> None:
    import inspect
    from rasai.consolidation.specialist import _longitudinal_deterministic_html

    source = inspect.getsource(_longitudinal_deterministic_html)
    assert "metric signal-negative" in source
    assert "metric signal-positive" in source
    assert "metric signal-warning" in source


def test_longitudinal_states_reuse_same_font_only_semantics() -> None:
    from rasai.consolidation.specialist import _catalog_state_html, _longitudinal_state_html

    assert "state-text good" in _longitudinal_state_html("IMPROVED")
    assert "state-text bad" in _longitudinal_state_html("REGRESSED")
    assert "state-text warn" in _longitudinal_state_html("PERSISTENTE_ATENCAO")
    assert "state-text neutral" in _longitudinal_state_html("NOT_COMPARABLE")
    assert "state-text neutral" in _catalog_state_html("Não aplicável")
    assert "state-text neutral" in _catalog_state_html("Não determinado")
