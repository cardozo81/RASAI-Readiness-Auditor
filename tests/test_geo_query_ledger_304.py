"""#304 offline GEO query ledger, synthetic physical SQLite only."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from rasai.geo_query_ledger_304 import inspect_geo_per_query, main


def _audit(tmp_path: Path, *, multi=True, source_query_column=True) -> Path:
    folder = tmp_path / "AUD-GEO304"
    folder.mkdir()
    db = folder / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audits (
                audit_id TEXT, status TEXT, completion_status TEXT
            );
            CREATE TABLE perplexity_search_runs (
                run_id TEXT, audit_id TEXT, query_json TEXT,
                search_type TEXT, status TEXT, started_at TEXT
            );
            CREATE TABLE perplexity_search_sources (
                run_id TEXT, position INTEGER, url TEXT
            );
            CREATE TABLE serp_observations (
                observation_id TEXT, audit_id TEXT, query TEXT,
                collected_at TEXT, observation_status TEXT, data_mode TEXT,
                engine TEXT, country TEXT, region TEXT, language TEXT, device TEXT
            );
            CREATE TABLE serp_results (
                observation_id TEXT, position INTEGER, url TEXT
            );
            INSERT INTO audits VALUES ('AUD-GEO304', 'COMPLETED', 'COMPLETE');
        """)
        if source_query_column:
            con.execute("ALTER TABLE perplexity_search_sources ADD COLUMN query TEXT")
        queries = ["seguro bradesco", "seguro de vida"] if multi else ["seguro de vida"]
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            ("PX-A", "AUD-GEO304", json.dumps(queries), "web", "SUCCESS",
             "2026-10-10T12:00:00Z"),
        )
        for index, query in enumerate(queries):
            entries = [
                "https://example.org/shared",
                "https://brand.org/branded" if query == "seguro bradesco"
                else "https://unbranded.org/vida",
            ]
            for j, url in enumerate(entries):
                if source_query_column:
                    con.execute(
                        "INSERT INTO perplexity_search_sources VALUES (?,?,?,?)",
                        ("PX-A", index*10+j, url, query),
                    )
                else:
                    con.execute(
                        "INSERT INTO perplexity_search_sources VALUES (?,?,?)",
                        ("PX-A", index*10+j, url),
                    )
            sid = "SERP-" + str(index)
            con.execute(
                "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (sid, "AUD-GEO304", query, "2026-10-10T12:10:00Z",
                 "OBSERVED", "OBSERVED_API", "google", "BR", "São Paulo",
                 "pt-BR", "mobile"),
            )
            for j, url in enumerate((
                "https://example.org/shared",
                "https://serp.example.org/page",
                "https://other.example.org/result",
            )):
                con.execute("INSERT INTO serp_results VALUES (?,?,?)", (sid, j, url))
    return folder


def test_multiquery_explicit_source_mapping_yields_separate_denominators(tmp_path):
    folder = _audit(tmp_path)
    before = sha256((folder / "audit.db").read_bytes()).hexdigest()
    result = inspect_geo_per_query(
        folder, declared_branded_queries=("seguro bradesco",),
    )
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["per_query_attribution_status"] == "PHYSICALLY_ATTRIBUTABLE"
    assert len(result["queries"]) == 2
    assert [row["declared_query_class"] for row in result["queries"]] == [
        "BRANDED_DECLARED", "UNCLASSIFIED",
    ]
    for row in result["queries"]:
        assert row["status"] == "DESCRIPTIVE_ONLY"
        assert row["perplexity_distinct_urls"] == 2
        assert row["serp_distinct_urls"] == 3
        assert row["common_urls"] == 1
        assert row["serp_only_urls"] == 2
        assert row["perplexity_only_urls"] == 1
        assert row["serp_overlap_rate"] == 0.3333
        assert row["perplexity_overlap_rate"] == 0.5
        assert row["jaccard_url_rate"] == 0.25
        assert row["observation_gap_seconds"] == 600
        assert row["serp_scope"]["country"] == "BR"
        assert row["external_market_language_device_equivalence_proven"] is False
        assert row["intent_equivalence_proven"] is False
        assert row["ranking_or_generative_citation_proven"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert sha256((folder / "audit.db").read_bytes()).hexdigest() == before
    assert not list(folder.glob("GEO-*"))


def test_multiquery_without_per_source_mapping_abstains_without_guessing(tmp_path):
    folder = _audit(tmp_path, source_query_column=False)
    raw = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["per_query_attribution_status"] == "MULTI_QUERY_SOURCE_MAPPING_MISSING"
    assert {row["reason"] for row in result["queries"]} == {
        "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN"
    }
    assert all(row["common_urls"] is None for row in result["queries"])
    assert (folder / "audit.db").read_bytes() == raw


def test_single_query_legacy_columns_allow_descriptive_only(tmp_path):
    folder = _audit(tmp_path, multi=False, source_query_column=False)
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert len(result["queries"]) == 1
    assert result["queries"][0]["perplexity_distinct_urls"] == 2
    assert result["queries"][0]["declared_query_class"] == "UNCLASSIFIED"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'",
         "AUD_NOT_COMPLETE_OR_FOREIGN"),
        ("UPDATE audits SET audit_id='AUD-OTHER'",
         "AUD_NOT_COMPLETE_OR_FOREIGN"),
        ("UPDATE perplexity_search_runs SET status='NETWORK_ERROR'",
         "EXTERNAL_SEARCH_NOT_SUCCESSFUL"),
        ("UPDATE perplexity_search_runs SET query_json='[1]'",
         "EXTERNAL_QUERY_SET_AMBIGUOUS"),
        ("UPDATE perplexity_search_runs SET query_json='[\"x\",\"x\"]'",
         "EXTERNAL_QUERY_SET_AMBIGUOUS"),
        ("UPDATE perplexity_search_sources SET query=NULL WHERE position=1",
         "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN"),
        ("UPDATE serp_observations SET language=NULL",
         "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H"),
        ("UPDATE serp_observations SET collected_at='2026-10-13T12:10:00Z'",
         "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H"),
    ],
    ids=["partial", "foreign-aud", "search-error", "malformed-query", "duplicate-query",
         "unattributed-source", "missing-serp-language", "stale-serp"],
)
def test_incomplete_provenance_never_yields_numeric_overlap(tmp_path, change, reason):
    folder = _audit(tmp_path)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(change)
    raw = (folder / "audit.db").read_bytes()
    output = inspect_geo_per_query(folder)
    all_reasons = {row["reason"] for row in output["queries"]}
    if output["queries"]:
        assert reason in all_reasons
        assert all(row["common_urls"] is None for row in output["queries"])
    else:
        assert output["reason"] == reason
    assert (folder / "audit.db").read_bytes() == raw


def test_serp_id_shared_between_auds_abstains_single_query(tmp_path):
    folder = _audit(tmp_path, multi=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("SERP-0", "AUD-FOREIGN", "seguro de vida", "2026-10-10T12:10:00Z",
             "OBSERVED", "OBSERVED_API", "google", "BR", "São Paulo",
             "pt-BR", "mobile"),
        )
    output = inspect_geo_per_query(folder)
    assert output["status"] == "NOT_COMPARABLE"
    assert output["queries"][0]["reason"] == "SERP_OBSERVATION_ID_AMBIGUOUS"
    assert output["queries"][0]["common_urls"] is None


def test_reject_ambiguous_same_time_serp_observations(tmp_path):
    folder = _audit(tmp_path, multi=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT 'SERP-TIE',audit_id,query,collected_at,"
            "observation_status,data_mode,engine,country,region,language,device "
            "FROM serp_observations LIMIT 1"
        )
    result = inspect_geo_per_query(folder)
    assert result["queries"][0]["reason"] == "AMBIGUOUS_EQUIDISTANT_SERP_OBSERVATIONS"
    assert result["queries"][0]["common_urls"] is None


def test_operator_cannot_claim_brand_on_query_missing_from_persisted_run(tmp_path):
    folder = _audit(tmp_path)
    with pytest.raises(ValueError, match="not in persisted run"):
        inspect_geo_per_query(folder, declared_branded_queries=("unrelated",))
    with pytest.raises(ValueError, match="invalid explicit"):
        inspect_geo_per_query(folder, declared_branded_queries=("x", "X"))


def test_early_refusal_missing_database_and_sqlite_sidecar(tmp_path):
    root = tmp_path / "AUD-EMPTY"
    root.mkdir()
    with pytest.raises(ValueError, match="read-only AUD database"):
        inspect_geo_per_query(root)
    folder = _audit(tmp_path)
    (folder / "audit.db-wal").write_bytes(b"pending changes")
    with pytest.raises(ValueError, match="without sidecars"):
        inspect_geo_per_query(folder)


def test_cli_offline_json_only(tmp_path, capsys):
    folder = _audit(tmp_path)
    assert main([str(folder), "--declared-branded-query", "seguro bradesco"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["queries"][0]["declared_query_class"] == "BRANDED_DECLARED"
    assert data["provider_requests"] == data["audit_writes"] == 0


def _set_physical_aud_targets(folder, targets):
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "CREATE TABLE audit_targets (audit_id TEXT, input_url TEXT)"
        )
        con.executemany(
            "INSERT INTO audit_targets VALUES (?,?)", targets
        )


def test_v2_exact_aud_target_is_visible_per_query_in_both_observed_url_sets(
    tmp_path,
):
    folder = _audit(tmp_path)
    _set_physical_aud_targets(
        folder, [("AUD-GEO304", "https://example.org/shared")]
    )
    original = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["contract_version"] == "RASAI-GEO-PER-QUERY-304-ADVISORY-002"
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["aud_target_scope"] == "SINGLE_EXACT_AUD_TARGET"
    assert result["aud_target_exact_url"] == "https://example.org/shared"
    for row in result["queries"]:
        assert row["target_url_exact_in_serp"] is True
        assert row["target_url_exact_in_perplexity"] is True
        assert row["target_url_overlap_status"] == "BOTH_SOURCE_SETS"
        assert row["ranking_or_generative_citation_proven"] is False
        assert row["intent_equivalence_proven"] is False
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize(
    ("scope", "in_serp", "in_external", "expected"),
    [
        ("both", True, True, "BOTH_SOURCE_SETS"),
        ("serp_only", True, False, "SERP_SOURCE_SET_ONLY"),
        ("external_only", False, True, "EXTERNAL_SOURCE_SET_ONLY"),
        ("neither", False, False, "NEITHER_RETURNED_SOURCE_SET"),
        ("trailing_slash", False, False, "NEITHER_RETURNED_SOURCE_SET"),
    ],
)
def test_exact_audit_url_coverage_never_infers_redirects_or_citations(
    tmp_path, scope, in_serp, in_external, expected,
):
    folder = _audit(tmp_path, multi=False)
    target = (
        "https://target.example.org/not-returned" if scope == "neither"
        else "https://example.org/shared/" if scope == "trailing_slash"
        else "https://example.org/shared"
    )
    _set_physical_aud_targets(folder, [("AUD-GEO304", target)])
    with sqlite3.connect(folder / "audit.db") as con:
        if scope == "external_only":
            con.execute(
                "UPDATE serp_results SET url=? WHERE observation_id=? AND position=0",
                ("https://serp.example.org/replacement", "SERP-0"),
            )
        elif scope == "serp_only":
            con.execute(
                "UPDATE perplexity_search_sources SET url=? WHERE run_id=? AND position=0",
                ("https://external.example.org/replacement", "PX-A"),
            )
    before = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    row = result["queries"][0]
    assert row["status"] == "DESCRIPTIVE_ONLY"
    assert row["target_url_exact_in_serp"] is in_serp
    assert row["target_url_exact_in_perplexity"] is in_external
    assert row["target_url_overlap_status"] == expected
    assert row["ranking_or_generative_citation_proven"] is False
    assert row["jaccard_url_rate"] is not None
    assert (folder / "audit.db").read_bytes() == before


@pytest.mark.parametrize(
    "aud_targets",
    [
        [],
        [
            ("AUD-GEO304", "https://example.org/shared"),
            ("AUD-GEO304", "https://example.org/shared"),
        ],
        [("AUD-FOREIGN", "https://example.org/shared")],
        [("AUD-GEO304", "javascript:alert(1)")],
    ],
    ids=["no-target", "two-target-rows", "foreign-only", "invalid-URL"],
)
def test_absent_or_ambiguous_aud_target_is_explicit_nd_not_false(
    tmp_path, aud_targets,
):
    folder = _audit(tmp_path, multi=False)
    _set_physical_aud_targets(folder, aud_targets)
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["aud_target_scope"] == "NO_UNIQUE_CANONICAL_TARGET"
    assert result["aud_target_exact_url"] is None
    row = result["queries"][0]
    assert row["target_url_exact_in_serp"] is None
    assert row["target_url_exact_in_perplexity"] is None
    assert row["target_url_overlap_status"] == "N/D"
    assert row["common_urls"] == 1


def test_target_presence_is_nd_when_per_query_source_mapping_is_absent(tmp_path):
    folder = _audit(tmp_path, source_query_column=False)
    _set_physical_aud_targets(
        folder, [("AUD-GEO304", "https://example.org/shared")]
    )
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["aud_target_scope"] == "SINGLE_EXACT_AUD_TARGET"
    assert all(
        row["target_url_exact_in_serp"] is None
        and row["target_url_exact_in_perplexity"] is None
        and row["target_url_overlap_status"] == "N/D"
        for row in result["queries"]
    )
