"""Issue #319: distinguish external Search API from generative usage.

All evidence is disposable SQLite in tmp_path; no network, browser, paid API.
"""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
import sqlite3
from unittest.mock import patch

from rasai.console_cost import ActualUsage
from rasai.console_search_intelligence import SearchConsoleState
from rasai.console_search_usage import SearchUsage, read_perplexity_search_usage


def _fixture(tmp_path: Path, *, corrupt: bool = False, source_table: bool = True) -> Path:
    root = tmp_path / "AUD-319"
    root.mkdir()
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript(
            """
            CREATE TABLE ai_provider_attempts(
                attempt_id TEXT PRIMARY KEY,audit_id TEXT,operation TEXT,
                semantic_contract_version TEXT,status TEXT
            );
            CREATE TABLE perplexity_search_runs(
                run_id TEXT PRIMARY KEY,audit_id TEXT,attempt_id TEXT,
                started_at TEXT,query_json TEXT,
                native_usage_unit TEXT,native_usage_quantity REAL,
                estimated_cost REAL,cost_currency TEXT
            );
            INSERT INTO ai_provider_attempts VALUES
              ('AI-1','AUD-319','AI:SEMANTIC','RASAI-SEMANTIC-1','SUCCESS'),
              ('PX-1','AUD-319','SEARCH_INTELLIGENCE','RASAI-PERPLEXITY-SEARCH-1','SUCCESS'),
              ('PX-2','AUD-OTHER','SEARCH_INTELLIGENCE','RASAI-PERPLEXITY-SEARCH-1','SUCCESS');
            """
        )
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "RUN-319","AUD-319","PX-1","2026-10-13T10:00:00Z",
                '{"invalid":1}' if corrupt else '["consulta 1", "consulta 2"]',
                "PERPLEXITY_SEARCH_REQUEST",1,0.001,"USD",
            ),
        )
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "RUN-OTHER","AUD-OTHER","PX-2","2026-10-13T10:01:00Z",
                '["consulta alheia"]',"PERPLEXITY_SEARCH_REQUEST",1,0.009,"USD",
            ),
        )
        if source_table:
            con.executescript(
                """
                CREATE TABLE perplexity_search_sources(
                    run_id TEXT,position INTEGER,url TEXT
                );
                INSERT INTO perplexity_search_sources VALUES
                  ('RUN-319',1,'https://example.test/1'),
                  ('RUN-319',2,'https://example.test/2'),
                  ('RUN-OTHER',1,'https://example.test/other');
                """
            )
    return root


def test_search_usage_uses_only_matching_aud_and_exact_search_contract(tmp_path) -> None:
    root = _fixture(tmp_path)
    db = root / "audit.db"
    before = sha256(db.read_bytes()).hexdigest()
    result = read_perplexity_search_usage(root, "AUD-319")
    assert isinstance(result, SearchUsage)
    assert result.runs == 1
    assert result.requests == 1
    assert result.queries == 2
    assert result.sources == 2
    assert result.envelope_attempts == 1
    assert result.envelope_successes == 1
    assert result.estimated_costs == (("USD", 0.001),)
    assert result.unpriced_runs == 0
    assert sha256(db.read_bytes()).hexdigest() == before
    assert read_perplexity_search_usage(root, "AUD-NOT-FOUND") is None


def test_missing_and_corrupt_query_evidence_never_becomes_zero(tmp_path) -> None:
    root = _fixture(tmp_path, corrupt=True, source_table=False)
    result = read_perplexity_search_usage(root, "AUD-319")
    assert result is not None
    assert result.queries is None
    assert result.sources is None
    assert result.requests == 1
    assert read_perplexity_search_usage(None, "AUD-319") is None
    assert read_perplexity_search_usage(root, "") is None


def test_console_separates_search_attempts_and_cost_without_repricing(tmp_path) -> None:
    from rasai import interactive_console as console

    root = _fixture(tmp_path)
    state = SearchConsoleState(audit_id="AUD-319")
    usage = ActualUsage(
        ai_attempts=2,ai_successes=2,
        input_tokens=100,cached_input_tokens=0,output_tokens=35,
        reasoning_tokens=0,total_tokens=135,
        costs=(("USD",0.021),),unpriced_ai_attempts=0,
        web_external_calls=0,web_services=(),
        native_usage=(("PERPLEXITY_SEARCH_REQUEST",1.0),),
    )
    output = StringIO()
    with patch("rasai.interactive_console.artifact_status",return_value=(root,None)), patch(
        "rasai.interactive_console.actual_usage",return_value=usage
    ), patch(
        "rasai.interactive_console.actual_m23_usage",return_value=None
    ), patch(
        "rasai.interactive_console.load_collection_coverage",return_value=None
    ), redirect_stdout(output):
        console._render_actual_usage(state)
    visible = output.getvalue()
    assert "IA GENERATIVA" in visible
    assert "Tentativas IA       : 1 (sucesso: 1)" in visible
    assert "SEARCH INTELLIGENCE EXTERNA" in visible
    assert "Tentativas Search   : 1" in visible
    assert "Requests Search     : 1" in visible
    assert "Queries Search      : 2" in visible
    assert "Fontes Search       : 2" in visible
    assert "Custo Search        : USD 0.00100000" in visible
    assert "Custo IA sem Search : USD 0.02000000" in visible
    assert "Custo IA + pesquisa" in visible
    assert "Tokens total" in visible
    assert "Uso nativo IA       : 1 requisição de busca Perplexity" not in visible


def test_no_search_keeps_original_generative_console_semantics(tmp_path) -> None:
    from rasai import interactive_console as console

    state = SearchConsoleState(audit_id="AUD-319")
    usage = ActualUsage(
        ai_attempts=1,ai_successes=1,
        input_tokens=100,cached_input_tokens=0,
        output_tokens=20,reasoning_tokens=0,total_tokens=120,
        costs=(("USD",0.02),),unpriced_ai_attempts=0,
        web_external_calls=0,web_services=(),
    )
    output = StringIO()
    with patch("rasai.interactive_console.artifact_status",return_value=(tmp_path,None)), patch(
        "rasai.interactive_console.actual_usage",return_value=usage
    ), patch(
        "rasai.interactive_console.actual_m23_usage",return_value=None
    ), patch(
        "rasai.interactive_console.load_collection_coverage",return_value=None
    ), redirect_stdout(output):
        console._render_actual_usage(state)
    visible = output.getvalue()
    assert "Tentativas IA       : 1 (sucesso: 1)" in visible
    assert "Custo IA estimado" in visible
    assert "SEARCH INTELLIGENCE EXTERNA" not in visible
