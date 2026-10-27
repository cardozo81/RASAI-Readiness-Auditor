"""AUD-71091931: GEO query integrity, provider projection, terminal console.

These are offline contract fixtures. No NYTimes requests and no paid API calls.
"""
from __future__ import annotations

from contextlib import closing
from io import StringIO
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sqlite3

import pytest

from rasai.geo_report import geo_body
from rasai.geo_search_alignment import geo_configuration_view
from rasai.console_progress_presentation import _public_stage_status


def _db(tmp_path: Path, *, second_failed: bool = False) -> Path:
    path = tmp_path / "audit.db"
    with closing(sqlite3.connect(path)) as con, con:
        con.executescript("""
            CREATE TABLE perplexity_search_runs(
                run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                search_type TEXT, status TEXT, started_at TEXT, error_class TEXT
            );
            CREATE TABLE perplexity_search_sources(
                run_id TEXT, position INTEGER, url TEXT, title TEXT,
                snippet TEXT, source_date TEXT, last_updated TEXT
            );
        """)
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES(?,?,?,?,?,?,?)",
            ("PX-OK", "AUD-NYT", '["seguro para família"]', "FAST", "SUCCESS",
             "2026-10-25T11:30:24+00:00", None),
        )
        for index in range(10):
            url = (
                "javascript:alert(1)" if index == 9
                else f"https://example.org/policy-{index}?region=pt&country=br"
            )
            con.execute(
                "INSERT INTO perplexity_search_sources VALUES(?,?,?,?,?,?,?)",
                ("PX-OK", index + 1, url, f"Title {index}", "evidence " * 95,
                 "2026-10-01", "2026-10-23"),
            )
        if second_failed:
            con.execute(
                "INSERT INTO perplexity_search_runs VALUES(?,?,?,?,?,?,?)",
                ("PX-FAIL", "AUD-NYT", '["alaska"]', "FAST", "NETWORK_ERROR",
                 "2026-10-25T11:36:00+00:00", "NETWORK"),
            )
    return path


def test_nytimes_geo_renders_materialized_current_run_and_safe_source_details(tmp_path):
    db = _db(tmp_path)
    before = db.read_bytes()
    html = geo_body(db, "AUD-NYT")
    assert "Perplexity Search API realizada com sucesso" in html
    assert "10 fonte(s) observada(s) e materializada(s)" in html
    assert html.count("Abrir fonte</a>") == 9
    assert "href=\"https://example.org/policy-0?region=pt&amp;country=br\"" in html
    assert 'href="javascript:' not in html
    assert "2026-10-01" in html and "2026-10-23" in html
    assert "trecho abreviado; íntegro no audit.db" in html
    assert db.read_bytes() == before


def test_nytimes_latest_failed_request_cannot_show_old_success_as_current(tmp_path):
    db = _db(tmp_path, second_failed=True)
    html = geo_body(db, "AUD-NYT")
    assert "2 execução(ões) persistida(s)" in html
    assert "0 fonte(s) materializada(s) da execução atual" in html
    assert "Execução atual sem sucesso comprovado" in html
    assert "Abrir fonte</a>" not in html
    assert "10 em todas as execuções da AUD" in html


def test_cat05_advisory_distinguishes_provenance_alignment_and_topic():
    from rasai.console_search_intelligence import SearchConsoleState

    state = SearchConsoleState(
        target="https://www.nytimes.com/",
        search_queries=("alaska",),
        perplexity_draft_queries=("seguro para família",),
    )
    view = geo_configuration_view(state)
    assert view["alignment_status"] == "DIVERGENT"
    assert view["review_recommended"]
    assert view["topical_fitness"] == "NÃO VERIFICADA"
    assert view["perplexity_source"] == "RASCUNHO (SEM AUTORIZAÇÃO)"
    assert "N/D" in view["comparability"]
    state.perplexity_draft_queries = ("alaska",)
    view = geo_configuration_view(state)
    assert view["alignment_status"] == "QUERY_MATCH"
    assert view["provider_context_equivalence"] == "NÃO COMPROVADA"
    assert not view["review_recommended"]
    state.search_queries = ("alaska", "travel")
    state.perplexity_draft_queries = ("travel", "alaska")
    assert geo_configuration_view(state)["review_recommended"]


@pytest.mark.parametrize("answer,expected_called,expected_px", [
    ("V", False, None),
    ("N", True, ()),
    ("C", True, ("seguro para família",)),
])
def test_prepaid_comparability_gate_requires_explicit_choice_without_billing(
    monkeypatch, answer, expected_called, expected_px,
):
    from rasai.console_catalog_plan import _PLANS, set_selected_catalog_ids
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai.console_perplexity_run_gate import install

    state = SearchConsoleState(
        target="https://www.nytimes.com/", search_queries=("alaska",),
        perplexity_queries=("seguro para família",),
    )
    _PLANS.clear()
    set_selected_catalog_ids(state, ["CAT-05"])
    captured = []
    module = ModuleType("standalone_test_console")
    module.run_audit_from_console = lambda st: captured.append(
        tuple(st.perplexity_queries)
    ) or 0
    install(module)
    monkeypatch.setattr("builtins.input", lambda prompt="": answer)
    try:
        assert module.run_audit_from_console(state) == 0
        assert (len(captured) == 1) is expected_called
        if expected_called:
            assert captured == [expected_px]
        assert state.perplexity_queries == ("seguro para família",)
    finally:
        _PLANS.clear()


@pytest.mark.parametrize("status,expected", [
    ("COMPLETE", "CONCLUÍDA"),
    ("COMPLETE_WITH_LIMITATIONS", "CONCLUÍDA COM LIMITAÇÕES"),
])
def test_viewing_reports_after_complete_never_restores_running(status, expected):
    for operation in ("LOCAL:DONE", "LOCAL:OPEN_REPORT", "LOCAL:OPEN_AUDIT_FOLDER"):
        state = SimpleNamespace(status=status, operation=operation)
        complete = SimpleNamespace(
            overall_exact=True, overall_percent=100.0,
            current_status="EM EXECUÇÃO",
        )
        assert _public_stage_status(state, complete) == expected
