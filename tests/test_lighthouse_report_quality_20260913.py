from __future__ import annotations

import sqlite3

from rasai.console_config import State, build_command
from rasai.console_execution_profiles import clear_profile, effective_profile, set_profile
from rasai.report_completion import AUDIT_ALWAYS_PAGES
from rasai.report_presentation_finalizer import (
    _apdex_visual,
    _decorate_ux_apdex,
    _dependency_states,
    _move_ai_cost_to_final_data_block,
)
from rasai.report_semantics import _lighthouse_score_state, _threshold_state


def test_complete_safe_profile_really_enables_full_lighthouse_transport() -> None:
    state = State(target="https://example.test/")
    session = set_profile(state, profile_id="complete-safe")
    try:
        with effective_profile(state, session):
            assert state.web_performance is True
            assert state.lighthouse_categories == (
                "performance,accessibility,best-practices,seo,agentic-browsing"
            )
            command = build_command(state)
            assert "--web-performance" in command
            index = command.index("--lighthouse-categories")
            assert command[index + 1] == state.lighthouse_categories
    finally:
        clear_profile(state)


def test_lighthouse_and_cwv_color_boundaries_are_canonical() -> None:
    assert _lighthouse_score_state("90/100", primary=True)[0] == "good"
    assert _lighthouse_score_state("89/100", primary=True)[0] == "warn"
    assert _lighthouse_score_state("50/100", primary=True)[0] == "warn"
    assert _lighthouse_score_state("49/100", primary=True)[0] == "bad"

    assert _threshold_state("2500 ms", good=2500.0, needs=4000.0, primary=True)[0] == "good"
    assert _threshold_state("2501 ms", good=2500.0, needs=4000.0, primary=True)[0] == "warn"
    assert _threshold_state("4001 ms", good=2500.0, needs=4000.0, primary=True)[0] == "bad"
    assert _threshold_state("200 ms", good=200.0, needs=500.0, primary=True)[0] == "good"
    assert _threshold_state("500 ms", good=200.0, needs=500.0, primary=True)[0] == "warn"
    assert _threshold_state("501 ms", good=200.0, needs=500.0, primary=True)[0] == "bad"
    assert _threshold_state("0.1", good=0.1, needs=0.25, primary=True)[0] == "good"
    assert _threshold_state("0.25", good=0.1, needs=0.25, primary=True)[0] == "warn"
    assert _threshold_state("0.251", good=0.1, needs=0.25, primary=True)[0] == "bad"


def test_ux_apdex_uses_same_score_bands_as_standard_apdex() -> None:
    assert _apdex_visual(0.94) == ("good", "Excelente")
    assert _apdex_visual(0.85) == ("good", "Bom")
    assert _apdex_visual(0.70) == ("warn", "Regular")
    assert _apdex_visual(0.50) == ("bad", "Ruim")
    assert _apdex_visual(0.49) == ("bad", "Inaceitável")

    html = "<article class='population-card'><div>URL</div><div class='population-score'>0.850</div><div>dados</div></article>"
    rendered = _decorate_ux_apdex(html)
    assert "population-card result-state-good" in rendered
    assert "population-score-state good" in rendered
    assert "Bom" in rendered
    assert "0.850" in rendered


def test_ai_cost_is_final_data_block_before_footer() -> None:
    html = """<html><body><main>
<section id='first'>A</section>
<section class='panel ai-cost-attribution' data-ai-cost-attribution='true'>CUSTO</section>
<section id='last-domain'>B</section>
<footer class='footer'>RODAPE</footer>
</main></body></html>"""
    rendered = _move_ai_cost_to_final_data_block(html)
    assert rendered.index("last-domain") < rendered.index("data-ai-cost-attribution")
    assert rendered.index("data-ai-cost-attribution") < rendered.index("footer")


def test_pagespeed_http_success_without_lighthouse_scores_gets_explicit_cause() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(
            """
            CREATE TABLE web_performance_runs(
                audit_id TEXT, enabled INTEGER, status TEXT, reason TEXT, pagespeed_successes INTEGER
            );
            CREATE TABLE web_performance_attempts(
                audit_id TEXT, service TEXT, status TEXT, http_status INTEGER,
                error_code TEXT, error_message TEXT, created_at TEXT
            );
            CREATE TABLE web_performance_observations(
                audit_id TEXT, status TEXT, error_summary TEXT,
                performance_score REAL, accessibility_score REAL,
                best_practices_score REAL, seo_score REAL, agentic_browsing_score REAL,
                captured_at TEXT
            );
            INSERT INTO web_performance_runs VALUES('AUD-X',1,'UNAVAILABLE','EXTERNAL_WEB_PERFORMANCE_UNAVAILABLE',1);
            INSERT INTO web_performance_attempts VALUES('AUD-X','PAGESPEED_INSIGHTS','SUCCESS',200,NULL,NULL,'2026-09-13T12:00:00Z');
            INSERT INTO web_performance_observations VALUES(
                'AUD-X','UNAVAILABLE','LIGHTHOUSE_RESULT_MISSING',NULL,NULL,NULL,NULL,NULL,
                '2026-09-13T12:00:01Z'
            );
            """
        )
        states = _dependency_states(connection, "AUD-X")
    finally:
        connection.close()

    assert "lighthouse" in states
    assert "PageSpeed concluiu o transporte" in states["lighthouse"]
    assert "LIGHTHOUSE_RESULT_MISSING" in states["lighthouse"]
    assert "nenhum score válido" in states["lighthouse"]


def test_report_contract_still_requires_every_canonical_html() -> None:
    expected = set(AUDIT_ALWAYS_PAGES)
    assert "index.html" in expected
    assert "web-performance.html" in expected
    assert "accessibility.html" in expected
    assert "ai-usage.html" in expected
    assert "scoring.html" in expected
    assert "apdex.html" in expected
    assert "apdex-experience.html" in expected
