"""#304 offline GEO query ledger, synthetic physical SQLite only."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3

import pytest

from rasai.geo_query_ledger_304 import inspect_geo_per_query, main
from rasai import geo_query_ledger_304 as ledger


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


@pytest.mark.parametrize(
    ("origin", "malformed_url"),
    [
        ("perplexity", " https://example.org/shared"),
        ("perplexity", "javascript:payload"),
        ("serp", "https://user:secret@example.org/shared"),
        ("serp", "not-an-http-url"),
    ],
)
def test_partial_invalid_url_sample_abstains_only_affected_query(
    tmp_path, origin, malformed_url,
):
    """#304: an invalid member cannot disappear from a published denominator."""
    folder = _audit(tmp_path)
    db = folder / "audit.db"
    with sqlite3.connect(db) as con:
        if origin == "perplexity":
            con.execute(
                "UPDATE perplexity_search_sources SET url=? "
                "WHERE run_id='PX-A' AND position=0",
                (malformed_url,),
            )
        else:
            con.execute(
                "UPDATE serp_results SET url=? "
                "WHERE observation_id='SERP-0' AND position=0",
                (malformed_url,),
            )
    raw = db.read_bytes()
    result = inspect_geo_per_query(folder)
    rows = {row["query"]: row for row in result["queries"]}
    invalid = rows["seguro bradesco"]
    healthy = rows["seguro de vida"]
    assert invalid["status"] == "NOT_COMPARABLE"
    assert invalid["reason"] == (
        "EXTERNAL_SOURCE_URL_IDENTITY_UNVERIFIABLE"
        if origin == "perplexity"
        else "SERP_SOURCE_URL_IDENTITY_UNVERIFIABLE"
    )
    for key in (
        "common_urls", "serp_distinct_urls", "perplexity_distinct_urls",
        "serp_only_urls", "perplexity_only_urls", "serp_overlap_rate",
        "perplexity_overlap_rate", "jaccard_url_rate",
    ):
        assert invalid[key] is None
    assert invalid["target_url_overlap_status"] == "N/D"
    assert healthy["status"] == "DESCRIPTIVE_ONLY"
    assert healthy["serp_distinct_urls"] == 3
    assert healthy["perplexity_distinct_urls"] == 2
    assert healthy["common_urls"] == 1
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert result["source_audit_db_sha256"] == sha256(raw).hexdigest()
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert db.read_bytes() == raw


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


@pytest.mark.parametrize("mode", [
    "oversized_padded_query_array", "unverified_binary_query_json",
])
def test_search_query_json_evidence_is_bounded_before_decoding(tmp_path, mode):
    folder = _audit(tmp_path, multi=False)
    db = folder / "audit.db"
    # Both are decodable JSON in an unbounded json.loads call. The first
    # carries >16KiB of padding; the second is SQLite BLOB, not JSON TEXT.
    raw = (
        " " * (16 * 1024 + 1) + '["seguro de vida"]'
        if mode == "oversized_padded_query_array" else b'["seguro de vida"]'
    )
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE perplexity_search_runs SET query_json=? WHERE run_id='PX-A'",
            (raw,),
        )
    before = db.read_bytes()
    out = inspect_geo_per_query(folder)
    assert out["status"] == "NOT_COMPARABLE"
    assert out["reason"] == "EXTERNAL_QUERY_JSON_INVALID"
    assert out["queries"] == []
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert out["source_audit_db_sha256"] is None
    assert db.read_bytes() == before


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
    assert result["contract_version"] == "RASAI-GEO-PER-QUERY-304-ADVISORY-006"
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


def test_v3_observed_query_overlap_sealed_against_physical_db_bytes(tmp_path):
    folder = _audit(tmp_path, multi=False)
    before = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert result["source_audit_db_sha256"] == sha256(before).hexdigest()
    assert result["source_audit_db_bytes_verified"] == len(before)
    assert result["source_package_freshness_verified"] is False
    assert (folder / "audit.db").read_bytes() == before


def test_v3_change_during_immutable_projection_discards_numeric_metrics(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path, multi=False)
    original = ledger._audit_digest
    calls = {"count": 0}
    def changed_before_second_digest(path):
        calls["count"] += 1
        if calls["count"] == 2:
            with sqlite3.connect(path) as con:
                con.execute(
                    "UPDATE serp_results SET url='https://tampered.org/' "
                    "WHERE observation_id='SERP-0' AND position=0"
                )
        return original(path)
    monkeypatch.setattr(ledger, "_audit_digest", changed_before_second_digest)
    result = inspect_geo_per_query(folder)
    assert calls["count"] == 2
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "AUD_SOURCE_CHANGED_DURING_READ"
    assert result["queries"] == []
    assert result["per_query_attribution_status"] == "NOT_VERIFIED"
    assert result["aud_target_scope"] == "NO_UNIQUE_CANONICAL_TARGET"
    assert result["aud_target_exact_url"] is None
    assert result["source_audit_db_sha256"] is None
    assert result["source_audit_db_bytes_verified"] is None
    assert result["source_audit_db_integrity_guard"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "failure_type", [ValueError, OSError, sqlite3.OperationalError],
)
def test_v3_late_integrity_exception_never_leaks_projected_overlap(
    tmp_path, monkeypatch, failure_type,
):
    """#304: any exception in the second physical seal clears all rates."""
    folder = _audit(tmp_path, multi=False)
    _set_physical_aud_targets(
        folder, [(folder.name, "https://example.org/shared")]
    )
    db = folder / "audit.db"
    original_bytes = db.read_bytes()
    physical_digest = ledger._audit_digest
    calls = []

    def fail_only_after_query_projection(path):
        calls.append(path)
        if len(calls) == 2:
            raise failure_type("physical seal lost after projection")
        return physical_digest(path)

    monkeypatch.setattr(ledger, "_audit_digest", fail_only_after_query_projection)
    result = inspect_geo_per_query(folder)
    assert len(calls) == 2
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "SOURCE_SCHEMA_OR_READ_FAILURE"
    assert result["queries"] == []
    assert result["per_query_attribution_status"] == "NOT_VERIFIED"
    assert result["aud_target_scope"] == "NO_UNIQUE_CANONICAL_TARGET"
    assert result["aud_target_exact_url"] is None
    assert result["source_audit_db_sha256"] is None
    assert result["source_audit_db_bytes_verified"] is None
    assert result["source_audit_db_integrity_guard"] == "UNVERIFIED"
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert db.read_bytes() == original_bytes


def test_v3_new_sqlite_journal_during_projection_discards_overlap(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path, multi=False)
    original = ledger._audit_digest
    calls = {"count": 0}
    def journal_during_read(path):
        calls["count"] += 1
        if calls["count"] == 1:
            result = original(path)
            (folder / "audit.db-wal").write_bytes(b"uncommitted")
            return result
        return original(path)
    monkeypatch.setattr(ledger, "_audit_digest", journal_during_read)
    outcome = inspect_geo_per_query(folder)
    assert outcome["status"] == "NOT_COMPARABLE"
    assert outcome["reason"] == "AUD_SQLITE_SIDECAR_APPEARED_DURING_READ"
    assert outcome["queries"] == []
    assert outcome["per_query_attribution_status"] == "NOT_VERIFIED"
    assert outcome["aud_target_scope"] == "NO_UNIQUE_CANONICAL_TARGET"
    assert outcome["aud_target_exact_url"] is None
    assert outcome["source_audit_db_sha256"] is None
    assert outcome["source_audit_db_bytes_verified"] is None
    assert outcome["source_audit_db_integrity_guard"] == "UNVERIFIED"
    assert calls["count"] == 1


@pytest.mark.parametrize(
    "inconsistent_stream",
    ("short_read", "unexpected_growth"),
)
def test_v3_sha_stream_length_must_match_physical_aud_size(
    tmp_path, monkeypatch, inconsistent_stream,
):
    """#304: two matching partial digests cannot prove full-source integrity."""
    from io import BytesIO

    folder = _audit(tmp_path, multi=False)
    db = folder / "audit.db"
    original_open = Path.open
    with original_open(db, "rb") as src:
        source_bytes = src.read()
    injected = (
        source_bytes[:-16] if inconsistent_stream == "short_read"
        else source_bytes + b"UNEXPECTED_PHYSICAL_GROWTH"
    )
    assert len(injected) != len(source_bytes)

    observed_opens = []
    def inconsistent_reader(self, *args, **kwargs):
        if self == db and args and args[0] == "rb":
            observed_opens.append(self)
            return BytesIO(injected)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", inconsistent_reader)
    result = inspect_geo_per_query(folder)
    assert len(observed_opens) == 1
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "SOURCE_SCHEMA_OR_READ_FAILURE"
    assert result["queries"] == []
    assert result["source_audit_db_sha256"] is None
    assert result["source_audit_db_integrity_guard"] == "UNVERIFIED"
    assert result["provider_requests"] == result["audit_writes"] == 0
    with original_open(db, "rb") as src:
        assert src.read() == source_bytes


def test_v3_bounded_local_sha_budget_abstains_without_promoting_overlap(
    tmp_path, monkeypatch,
):
    folder = _audit(tmp_path, multi=False)
    original = (folder / "audit.db").read_bytes()
    monkeypatch.setattr(ledger, "_MAX_AUD_BYTES", 64)
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "SOURCE_SCHEMA_OR_READ_FAILURE"
    assert result["queries"] == []
    assert result["source_audit_db_sha256"] is None
    assert (folder / "audit.db").read_bytes() == original


def test_v4_same_exact_host_alternatives_and_competitor_hosts_are_distinct(
    tmp_path,
):
    folder = _audit(tmp_path, multi=False)
    _set_physical_aud_targets(
        folder, [("AUD-GEO304", "https://example.org/shared")]
    )
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-0", 10, "https://example.org/other-product"),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-0", 11, "https://www.example.org/shared"),
        )
        con.execute(
            "INSERT INTO perplexity_search_sources VALUES (?,?,?,?)",
            ("PX-A", 88, "https://example.org/alternative", "seguro de vida"),
        )
        con.execute(
            "INSERT INTO perplexity_search_sources VALUES (?,?,?,?)",
            ("PX-A", 89, "https://brand.org/other", "seguro de vida"),
        )
    raw = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    row = result["queries"][0]
    assert row["status"] == "DESCRIPTIVE_ONLY"
    assert row["target_url_overlap_status"] == "BOTH_SOURCE_SETS"
    assert row["serp_target_host_group"] == {
        "same_host_alternative_urls": 1,
        "other_host_distinct_urls": 3,
        "other_distinct_hosts": 3,
    }
    assert row["external_target_host_group"] == {
        "same_host_alternative_urls": 1,
        "other_host_distinct_urls": 2,
        "other_distinct_hosts": 2,
    }
    # www/apex are distinct physical hosts; no inferred redirect.
    assert row["ranking_or_generative_citation_proven"] is False
    assert row["intent_equivalence_proven"] is False
    assert (folder / "audit.db").read_bytes() == raw


def test_v4_single_query_explicitly_wrong_source_query_abstains(
    tmp_path,
):
    folder = _audit(tmp_path, multi=False)
    _set_physical_aud_targets(
        folder, [("AUD-GEO304", "https://example.org/shared")]
    )
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET query=? WHERE position=0",
            ("an unrelated search",),
        )
    raw = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "NO_QUERY_WITH_VERIFIED_SOURCE_DENOMINATORS"
    assert result["queries"][0]["reason"] == "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN"
    assert result["queries"][0]["serp_target_host_group"] is None
    assert result["queries"][0]["external_target_host_group"] is None
    assert result["queries"][0]["common_urls"] is None
    assert result["source_audit_db_sha256"] == sha256(raw).hexdigest()
    assert (folder / "audit.db").read_bytes() == raw


def test_v4_legacy_single_query_null_explicit_query_is_not_false_conflict(
    tmp_path,
):
    folder = _audit(tmp_path, multi=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET query=NULL"
        )
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["queries"][0]["serp_target_host_group"] is None
    assert result["queries"][0]["external_target_host_group"] is None


def test_v4_host_groups_are_nd_when_aud_target_is_ambiguous(tmp_path):
    folder = _audit(tmp_path, multi=False)
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    row = result["queries"][0]
    assert row["serp_target_host_group"] is None
    assert row["external_target_host_group"] is None
    assert row["target_url_overlap_status"] == "N/D"


def _provider_source_metadata(folder, *, mapped=True, with_query_column=False):
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "ALTER TABLE perplexity_search_sources "
            "ADD COLUMN source_metadata_json TEXT"
        )
        for position in (0, 1, 10, 11):
            query = "seguro bradesco" if position < 10 else "seguro de vida"
            obj = {"query": query} if mapped else {"source": "perplexity"}
            con.execute(
                "UPDATE perplexity_search_sources SET source_metadata_json=? "
                "WHERE position=?",
                (json.dumps(obj), position),
            )


def test_v5_reads_real_repository_per_result_query_metadata_only_when_explicit(
    tmp_path,
):
    folder = _audit(tmp_path, multi=True, source_query_column=False)
    _provider_source_metadata(folder)
    original = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["contract_version"] == "RASAI-GEO-PER-QUERY-304-ADVISORY-006"
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["per_query_attribution_status"] == "PHYSICALLY_ATTRIBUTABLE"
    assert len(result["queries"]) == 2
    for row in result["queries"]:
        assert row["status"] == "DESCRIPTIVE_ONLY"
        assert row["perplexity_distinct_urls"] == 2
        assert row["serp_distinct_urls"] == 3
        assert row["common_urls"] == 1
        assert row["jaccard_url_rate"] == .25
        assert row["intent_equivalence_proven"] is False
        assert row["ranking_or_generative_citation_proven"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize(
    ("mutation", "label"),
    [
        ("unlabeled", "source"),
        ("wrong-query", "query"),
        ("malformed-json", "metadata-json"),
        ("mixed-mapping", "query-row-missing"),
    ],
)
def test_v5_refuses_unverifiable_or_bad_per_source_query_metadata(
    tmp_path, mutation, label,
):
    folder = _audit(tmp_path, multi=True, source_query_column=False)
    _provider_source_metadata(folder)
    with sqlite3.connect(folder / "audit.db") as con:
        if mutation == "unlabeled":
            con.execute(
                "UPDATE perplexity_search_sources "
                "SET source_metadata_json=? WHERE position=0",
                (json.dumps({"source": "perplexity"}),),
            )
        elif mutation == "wrong-query":
            con.execute(
                "UPDATE perplexity_search_sources "
                "SET source_metadata_json=? WHERE position=0",
                (json.dumps({"query": "not a declared query"}),),
            )
        elif mutation == "malformed-json":
            con.execute(
                "UPDATE perplexity_search_sources "
                "SET source_metadata_json=? WHERE position=0",
                ('{"query": invalid json',),
            )
        elif mutation == "mixed-mapping":
            con.execute(
                "UPDATE perplexity_search_sources "
                "SET source_metadata_json=NULL WHERE position=0"
            )
    original = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["per_query_attribution_status"] == "MULTI_QUERY_SOURCE_MAPPING_MISSING"
    assert {row["reason"] for row in result["queries"]} == {
        "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN"
    }
    assert all(row["common_urls"] is None for row in result["queries"])
    assert result["source_audit_db_sha256"] == sha256(original).hexdigest()
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize("duplicate_query_json", [
    '{"query":"seguro bradesco","query":"seguro de vida"}',
    '{"query":"seguro bradesco","query":"seguro bradesco"}',
])
def test_v5_duplicate_query_keys_in_provider_metadata_cannot_assign_sources(
    tmp_path, duplicate_query_json,
):
    folder = _audit(tmp_path, multi=True, source_query_column=False)
    _provider_source_metadata(folder)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET source_metadata_json=? "
            "WHERE position=0",
            (duplicate_query_json,),
        )
    original = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["per_query_attribution_status"] == "MULTI_QUERY_SOURCE_MAPPING_MISSING"
    assert {row["reason"] for row in result["queries"]} == {
        "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN"
    }
    assert all(row["common_urls"] is None for row in result["queries"])
    assert result["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert result["source_audit_db_sha256"] == sha256(original).hexdigest()
    assert (folder / "audit.db").read_bytes() == original


def test_v5_conflict_between_column_and_provider_metadata_abstains(tmp_path):
    folder = _audit(tmp_path, multi=True, source_query_column=True)
    _provider_source_metadata(folder)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET source_metadata_json=? "
            "WHERE position=0",
            (json.dumps({"query": "seguro de vida"}),),
        )
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert all(row["common_urls"] is None for row in result["queries"])


def test_v5_single_query_metadata_cannot_override_declared_run(tmp_path):
    folder = _audit(tmp_path, multi=False, source_query_column=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "ALTER TABLE perplexity_search_sources "
            "ADD COLUMN source_metadata_json TEXT"
        )
        con.execute(
            "UPDATE perplexity_search_sources SET source_metadata_json=? "
            "WHERE position=0",
            (json.dumps({"query": "an unrelated query"}),),
        )
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["queries"][0]["common_urls"] is None


def test_v5_metadata_is_not_parsed_beyond_bounded_evidence_budget(tmp_path):
    folder = _audit(tmp_path, multi=True, source_query_column=False)
    _provider_source_metadata(folder)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET source_metadata_json=? "
            "WHERE position=0",
            (json.dumps({"query": "seguro bradesco", "noise": "x"*5000}),),
        )
    result = inspect_geo_per_query(folder)
    assert result["status"] == "NOT_COMPARABLE"
    assert all(row["common_urls"] is None for row in result["queries"])


def test_cli_optional_html_is_escaped_responsive_and_byte_read_only(
    tmp_path, capsys,
):
    folder = _audit(tmp_path)
    injection = '<img src=x onerror="alert(304)">'
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_runs SET query_json=?",
            (json.dumps([injection, "seguro de vida"]),),
        )
        con.execute(
            "UPDATE serp_observations SET query=? WHERE observation_id='SERP-0'",
            (injection,),
        )
        con.execute(
            "UPDATE perplexity_search_sources SET query=? WHERE query='seguro bradesco'",
            (injection,),
        )
    before = sha256((folder / "audit.db").read_bytes()).hexdigest()
    assert main([str(folder), "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert "<!doctype html>" in html
    assert "<html lang=\"pt-BR\">" in html
    assert "&lt;img src=x onerror=&quot;alert(304)&quot;&gt;" in html
    assert injection not in html
    assert "Comparação de conjuntos de URLs observadas" in html
    assert "N/D" in html
    assert "CSS" not in html
    assert "@media(max-width:680px)" in html
    assert "@media print" in html
    assert "URLs distintas SERP" in html
    assert "Comparabilidade externa não comprovada" in html
    assert "sem equivalência provada de país, idioma" in html
    assert "33.33%" in html
    assert "50.00%" in html
    assert sha256((folder / "audit.db").read_bytes()).hexdigest() == before
    assert list(folder.iterdir()) == [folder / "audit.db"]


def test_html_abstains_for_multiquery_unattributed_and_invalid_target(tmp_path, capsys):
    folder = _audit(tmp_path, source_query_column=False)
    raw = (folder / "audit.db").read_bytes()
    assert main([str(folder), "--format", "html"]) == 0
    html = capsys.readouterr().out
    assert "N/D - comparabilidade não demonstrada" in html
    assert "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN" in html
    assert "Comparabilidade externa não comprovada:" not in html
    assert "URLs distintas SERP" in html
    assert "33.33%" not in html
    assert (folder / "audit.db").read_bytes() == raw


def test_html_renderer_refuses_bad_contract_and_handles_untrusted_rows():
    from rasai.geo_query_ledger_html_304 import render_geo_query_ledger_html
    with pytest.raises(ValueError, match="unsupported"):
        render_geo_query_ledger_html({"contract_version": "WRONG", "queries": []})
    with pytest.raises(ValueError, match="malformed"):
        render_geo_query_ledger_html({
            "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-005",
            "status": "DESCRIPTIVE_ONLY",
            "queries": ["not a row"],
        })
    projection = {
        "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-005",
        "status": "NOT_COMPARABLE", "audit_id": "<script>alert(1)</script>",
        "source_audit_db_integrity_guard": "UNVERIFIED",
        "queries": [{
            "query": "<svg onload=alert(4)>",
            "status": "NOT_COMPARABLE",
            "reason": '<a href="javascript:alert(7)">unsafe</a>',
            "serp_distinct_urls": 999,
            "perplexity_distinct_urls": 999,
            "common_urls": 999,
            "serp_overlap_rate": 0.99,
            "target_url_exact_in_serp": True,
            "target_url_overlap_status": "BOTH_SOURCE_SETS",
            "declared_query_class": "UNCLASSIFIED",
        }],
    }
    html = render_geo_query_ledger_html(projection)
    assert "<script>" not in html
    assert "<svg onload=" not in html
    assert "javascript:alert(7)" in html  # Escaped text, never href attribute
    assert "&lt;a href=&quot;javascript:alert(7)&quot;&gt;" in html
    assert "999" not in html
    assert "99.00%" not in html
    assert "Sim (URL exata" not in html
    assert "N/D" in html


@pytest.mark.parametrize(
    ("global_status", "source_guard"),
    [
        ("NOT_COMPARABLE", "DOUBLE_SHA256_MATCH"),
        ("DESCRIPTIVE_ONLY", "UNVERIFIED"),
    ],
)
def test_html_global_source_gate_never_leaks_stale_verified_row(
    global_status, source_guard,
):
    """Rows from a failed global source gate cannot become positive evidence."""
    from rasai.geo_query_ledger_html_304 import render_geo_query_ledger_html

    projection = {
        "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-005",
        "audit_id": "AUD-GEO304",
        "status": global_status,
        "reason": "AUD_SOURCE_CHANGED_DURING_READ",
        "source_audit_db_integrity_guard": source_guard,
        "queries": [{
            "query": "seguro de vida",
            "status": "DESCRIPTIVE_ONLY",
            "serp_scope": {
                "engine": "google", "country": "BR", "region": "RS",
                "language": "pt-BR", "device": "mobile",
            },
            "serp_distinct_urls": 9876543,
            "perplexity_distinct_urls": 8765432,
            "common_urls": 7654321,
            "serp_overlap_rate": 0.9876,
            "target_url_exact_in_serp": True,
            "target_url_overlap_status": "BOTH_SOURCE_SETS",
            "declared_query_class": "UNCLASSIFIED",
        }],
    }
    html = render_geo_query_ledger_html(projection)
    assert "N/D - comparabilidade não demonstrada" in html
    assert "9876543" not in html
    assert "8765432" not in html
    assert "7654321" not in html
    assert "98.76%" not in html
    assert "Sim (URL exata" not in html
    assert "engine: google" not in html
    assert "BOTH_SOURCE_SETS" not in html
    assert "AUD_SOURCE_CHANGED_DURING_READ" in html


def test_public_cli_geo_query_ledger_and_html_do_not_bootstrap_audit_or_ai(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint
    folder = _audit(tmp_path, multi=False)
    source = folder / "audit.db"
    initial = source.read_bytes()
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("GEO per-query CLI must not install runtime"),
    )
    monkeypatch.setattr(
        entrypoint, "_activate_persisted_cli_secrets",
        lambda: pytest.fail("GEO per-query CLI must not access secrets"),
    )
    assert entrypoint.main([
        "geo-query-ledger", str(folder), "--format", "html",
    ]) == 0
    html = capsys.readouterr().out
    assert html.startswith("<!doctype html>")
    assert "Sobreposição descritiva de fontes URL" in html
    assert "N/D" in html
    assert "SCORE-GEO" in html
    assert source.read_bytes() == initial
    assert not (folder / "report-catalog").exists()
    assert not list(folder.glob("GEO-*"))
    assert entrypoint.main([
        "geo-query-report", str(folder), "--format", "json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == (
        "RASAI-GEO-PER-QUERY-304-ADVISORY-006"
    )
    assert payload["provider_requests"] == payload["audit_writes"] == 0
    assert source.read_bytes() == initial


@pytest.mark.parametrize(
    ("field", "other_value"),
    [
        ("engine", "bing"),
        ("country", "ES"),
        ("region", "Rio de Janeiro"),
        ("language", "es-ES"),
        ("device", "desktop"),
    ],
)
def test_v5_multiple_serp_scopes_for_one_query_abstain_per_query_only(
    tmp_path, field, other_value,
):
    folder = _audit(tmp_path, multi=True)
    with sqlite3.connect(folder / "audit.db") as con:
        columns = (
            "observation_id", "audit_id", "query", "collected_at",
            "observation_status", "data_mode", "engine", "country",
            "region", "language", "device",
        )
        row = dict(zip(columns, con.execute(
            "SELECT * FROM serp_observations WHERE observation_id='SERP-0'"
        ).fetchone()))
        row["observation_id"] = "SERP-SECOND-SCOPE"
        row["collected_at"] = "2026-10-10T12:01:00Z"
        row[field] = other_value
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row[key] for key in columns),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-SECOND-SCOPE", 0, "https://example.org/shared"),
        )
    original = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["per_query_attribution_status"] == "PHYSICALLY_ATTRIBUTABLE"
    first, second = result["queries"]
    assert first["query"] == "seguro bradesco"
    assert first["status"] == "NOT_COMPARABLE"
    assert first["reason"] == "AMBIGUOUS_SERP_MARKET_LANGUAGE_DEVICE_SCOPE"
    assert first["serp_scope"] is None
    assert first["common_urls"] is None
    assert first["serp_overlap_rate"] is None
    assert first["serp_observation_id"] is None
    assert first["ranking_or_generative_citation_proven"] is False
    assert second["query"] == "seguro de vida"
    assert second["status"] == "DESCRIPTIVE_ONLY"
    assert second["serp_scope"]["country"] == "BR"
    assert result["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert (folder / "audit.db").read_bytes() == original


def test_v5_two_same_scope_serp_observations_choose_closest_physical_time(
    tmp_path,
):
    folder = _audit(tmp_path, multi=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT 'SERP-CLOSER',audit_id,query,'2026-10-10T12:02:00Z',"
            "observation_status,data_mode,engine,country,region,language,device "
            "FROM serp_observations WHERE observation_id='SERP-0'"
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-CLOSER", 0, "https://example.org/shared"),
        )
    original = (folder / "audit.db").read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert result["queries"][0]["status"] == "DESCRIPTIVE_ONLY"
    assert result["queries"][0]["serp_observation_id"] == "SERP-CLOSER"
    assert result["queries"][0]["observation_gap_seconds"] == 120
    assert result["queries"][0]["serp_scope"]["country"] == "BR"
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize(
    "missing_scope",
    ["engine", "country", "region", "language", "device"],
)
def test_v6_incomplete_in_window_scope_cannot_be_hidden_by_valid_serp_sample(
    tmp_path, missing_scope,
):
    """An in-window OBSERVED_API sibling with absent scope cannot be cherry-picked away."""
    folder = _audit(tmp_path, multi=True)
    with sqlite3.connect(folder / "audit.db") as con:
        keys = (
            "observation_id", "audit_id", "query", "collected_at",
            "observation_status", "data_mode", "engine", "country",
            "region", "language", "device",
        )
        row = dict(zip(keys, con.execute(
            "SELECT * FROM serp_observations WHERE observation_id='SERP-0'"
        ).fetchone()))
        row["observation_id"] = "SERP-MISSING-SCOPE"
        row["collected_at"] = "2026-10-10T12:01:00Z"
        row[missing_scope] = None
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            tuple(row[key] for key in keys),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-MISSING-SCOPE", 0, "https://example.org/shared"),
        )
    source = folder / "audit.db"
    original = source.read_bytes()
    outcome = inspect_geo_per_query(folder)
    assert outcome["status"] == "DESCRIPTIVE_ONLY"
    assert outcome["per_query_attribution_status"] == "PHYSICALLY_ATTRIBUTABLE"
    first, second = outcome["queries"]
    assert first["status"] == "NOT_COMPARABLE"
    assert first["reason"] == "SERP_SCOPE_INCOMPLETE_ALONGSIDE_VERIFIED_SAMPLE"
    assert first["serp_observation_id"] is None
    assert first["common_urls"] is None
    assert first["jaccard_url_rate"] is None
    assert first["serp_overlap_rate"] is None
    assert first["serp_scope"] is None
    assert second["status"] == "DESCRIPTIVE_ONLY"
    assert second["common_urls"] == 1
    assert outcome["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert source.read_bytes() == original


def test_v6_out_of_window_missing_scope_does_not_poison_valid_sample(tmp_path):
    folder = _audit(tmp_path, multi=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT 'OUT-OF-WINDOW',audit_id,query,'2026-09-01T12:00:00Z',"
            "observation_status,data_mode,NULL,country,region,language,device "
            "FROM serp_observations WHERE observation_id='SERP-0'"
        )
    original = (folder / "audit.db").read_bytes()
    outcome = inspect_geo_per_query(folder)
    assert outcome["status"] == "DESCRIPTIVE_ONLY"
    assert outcome["queries"][0]["status"] == "DESCRIPTIVE_ONLY"
    assert outcome["queries"][0]["common_urls"] == 1
    assert (folder / "audit.db").read_bytes() == original


@pytest.mark.parametrize(
    "invalid_clock",
    ["2026-10-10T12:01:00", "not-a-timestamp", None],
)
def test_v7_unverifiable_serp_clock_same_query_abstains_without_cherry_pick(
    tmp_path, invalid_clock,
):
    folder = _audit(tmp_path, multi=True)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT 'UNVERIFIED-CLOCK',audit_id,query,?,"
            "observation_status,data_mode,engine,country,region,language,device "
            "FROM serp_observations WHERE observation_id='SERP-0'",
            (invalid_clock,),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("UNVERIFIED-CLOCK", 0, "https://example.org/shared"),
        )
    saved = (folder / "audit.db").read_bytes()
    outcome = inspect_geo_per_query(folder)
    assert outcome["status"] == "DESCRIPTIVE_ONLY"
    first, second = outcome["queries"]
    assert first["query"] == "seguro bradesco"
    assert first["status"] == "NOT_COMPARABLE"
    assert first["reason"] == "SERP_CHRONOLOGY_UNVERIFIABLE_FOR_QUERY"
    assert first["serp_observation_id"] is None
    assert first["common_urls"] is None
    assert first["jaccard_url_rate"] is None
    assert second["status"] == "DESCRIPTIVE_ONLY"
    assert second["common_urls"] == 1
    assert outcome["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert (folder / "audit.db").read_bytes() == saved


def test_v7_out_of_window_verified_clock_remains_excluded(tmp_path):
    folder = _audit(tmp_path, multi=False)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT 'OUT-WINDOW-VERIFIED',audit_id,query,'2026-07-01T12:00:00Z',"
            "observation_status,data_mode,engine,country,region,language,device "
            "FROM serp_observations WHERE observation_id='SERP-0'"
        )
    saved = (folder / "audit.db").read_bytes()
    outcome = inspect_geo_per_query(folder)
    assert outcome["status"] == "DESCRIPTIVE_ONLY"
    assert outcome["queries"][0]["common_urls"] == 1
    assert (folder / "audit.db").read_bytes() == saved


@pytest.mark.parametrize("raw_metadata", [
    '{"query":"seguro bradesco","elapsed_ms":NaN}',
    '{"query":"seguro bradesco","score":Infinity}',
    '{"query":"seguro bradesco","score":-Infinity}',
    '{"query":"seguro bradesco","nested":{"score":NaN}}',
    '{"query":"seguro bradesco","source":"one","source":"two"}',
    '{"query":"seguro bradesco","nested":{"id":1,"id":2}}',
])
def test_v9_per_source_query_metadata_rejects_non_json_numbers_and_ambiguous_keys(
    tmp_path, raw_metadata,
):
    """Malformed provider metadata may not certify multi-query attribution."""
    folder = _audit(tmp_path, multi=True, source_query_column=False)
    _provider_source_metadata(folder)
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET source_metadata_json=? "
            "WHERE position=0", (raw_metadata,),
        )
    before = (folder / "audit.db").read_bytes()
    evidence = inspect_geo_per_query(folder)
    assert evidence["status"] == "NOT_COMPARABLE"
    assert evidence["per_query_attribution_status"] == "MULTI_QUERY_SOURCE_MAPPING_MISSING"
    assert all(
        row["status"] == "NOT_COMPARABLE"
        and row["reason"] == "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN"
        and row["common_urls"] is None
        and row["jaccard_url_rate"] is None
        for row in evidence["queries"]
    )
    assert evidence["source_audit_db_sha256"] == sha256(before).hexdigest()
    assert evidence["source_audit_db_integrity_guard"] == "DOUBLE_SHA256_MATCH"
    assert evidence["provider_requests"] == evidence["audit_writes"] == 0
    assert (folder / "audit.db").read_bytes() == before


def test_v10_per_query_exact_hostname_overlap_is_observed_not_market_equivalence(
    tmp_path,
):
    """Physical URL sets are compared after per-query attribution, not snippets."""
    folder = _audit(tmp_path, multi=True)
    db = folder / "audit.db"
    before = db.read_bytes()
    result = inspect_geo_per_query(folder)
    assert result["contract_version"] == "RASAI-GEO-PER-QUERY-304-ADVISORY-006"
    assert result["status"] == "DESCRIPTIVE_ONLY"
    assert len(result["queries"]) == 2
    for row in result["queries"]:
        assert row["host_overlap"] == {
            "serp_distinct_hosts": 3,
            "external_distinct_hosts": 2,
            "common_hosts": 1,
            "serp_only_hosts": 2,
            "external_only_hosts": 1,
            "serp_host_overlap_rate": 0.3333,
            "external_host_overlap_rate": 0.5,
            "jaccard_host_rate": 0.25,
        }
        assert row["external_market_language_device_equivalence_proven"] is False
        assert row["ranking_or_generative_citation_proven"] is False
    assert result["source_audit_db_sha256"] == sha256(before).hexdigest()
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert db.read_bytes() == before


def test_v10_www_apex_distinct_while_url_port_does_not_change_hostname(
    tmp_path,
):
    folder = _audit(tmp_path, multi=False)
    db = folder / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE perplexity_search_sources SET url=? "
            "WHERE run_id='PX-A' AND position=1",
            ("https://www.example.org/page",),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?,?)",
            ("SERP-0", 21, "https://example.org:8443/port"),
        )
    before = db.read_bytes()
    row = inspect_geo_per_query(folder)["queries"][0]
    assert row["status"] == "DESCRIPTIVE_ONLY"
    # SERP distinct URLs increase, but example.org:8443 shares the
    # hostname example.org; www.example.org does not.
    assert row["serp_distinct_urls"] == 4
    assert row["host_overlap"] == {
        "serp_distinct_hosts": 3,
        "external_distinct_hosts": 2,
        "common_hosts": 1,
        "serp_only_hosts": 2,
        "external_only_hosts": 1,
        "serp_host_overlap_rate": 0.3333,
        "external_host_overlap_rate": 0.5,
        "jaccard_host_rate": 0.25,
    }
    assert db.read_bytes() == before


def test_v10_unproven_source_mapping_or_invalid_member_never_yields_host_rates(
    tmp_path,
):
    folder = _audit(tmp_path, multi=True, source_query_column=False)
    missing = inspect_geo_per_query(folder)
    assert all(row["host_overlap"] is None for row in missing["queries"])
    from rasai.geo_query_ledger_html_304 import render_geo_query_ledger_html
    html = render_geo_query_ledger_html(missing)
    assert "Hosts distintos SERP</td><td>N/D" in html
    assert "Interseção de hosts observados" in html
    with sqlite3.connect(folder / "audit.db") as con:
        con.execute(
            "ALTER TABLE perplexity_search_sources ADD COLUMN query TEXT"
        )
        for position in (0, 1, 10, 11):
            query = "seguro bradesco" if position < 10 else "seguro de vida"
            con.execute(
                "UPDATE perplexity_search_sources SET query=? WHERE position=?",
                (query, position),
            )
        con.execute(
            "UPDATE perplexity_search_sources SET url=? WHERE position=0",
            ("javascript:non-http",),
        )
    before = (folder / "audit.db").read_bytes()
    limited = inspect_geo_per_query(folder)
    by_query = {row["query"]: row for row in limited["queries"]}
    assert by_query["seguro bradesco"]["host_overlap"] is None
    assert by_query["seguro de vida"]["host_overlap"] is not None
    html = render_geo_query_ledger_html(limited)
    assert "Hosts distintos SERP</td><td>3</td>" in html
    assert (folder / "audit.db").read_bytes() == before


def test_v10_legacy_render_and_stale_source_never_promote_host_metrics():
    from rasai.geo_query_ledger_html_304 import render_geo_query_ledger_html
    legacy = {
        "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-005",
        "status": "DESCRIPTIVE_ONLY",
        "audit_id": "AUD-GEO304",
        "source_audit_db_integrity_guard": "DOUBLE_SHA256_MATCH",
        "queries": [{"query": "x", "status": "DESCRIPTIVE_ONLY",
                     "declared_query_class": "UNCLASSIFIED"}],
    }
    assert "Hosts distintos SERP</td><td>N/D" in render_geo_query_ledger_html(legacy)
    upgraded = {
        **legacy,
        "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-006",
        "source_audit_db_integrity_guard": "UNVERIFIED",
        "queries": [{**legacy["queries"][0], "host_overlap": {
            "common_hosts": 777,
            "serp_host_overlap_rate": 0.99,
        }}],
    }
    html = render_geo_query_ledger_html(upgraded)
    assert "777" not in html
    assert "99.00%" not in html
    assert "Hosts comuns</td><td>N/D" in html


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows SQLite may hold native handle preventing atomic os.replace",
)
def test_v11_same_length_atomic_source_replacement_before_descriptor_abstains(
    tmp_path, monkeypatch,
):
    """Matching bytes and size are insufficient if stat/open cross inodes."""
    import os

    folder = _audit(tmp_path, multi=False)
    database = folder / "audit.db"
    original_bytes = database.read_bytes()
    replacement = tmp_path / "other-sealed-audit.db"
    replacement.write_bytes(original_bytes)
    original_open = Path.open
    swaps = []

    def replaced_before_descriptor_open(self, *args, **kwargs):
        if self == database and args and args[0] == "rb":
            if not swaps:
                os.replace(replacement, database)
                swaps.append(True)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", replaced_before_descriptor_open)
    # This is a unit test of the *stat -> open* descriptor boundary.
    # Running the full ledger would add an unrelated Windows SQLite
    # sidecar gate, potentially returning before the first hash.
    with pytest.raises(ValueError, match="physical identity changed"):
        ledger._audit_digest(database)
    assert swaps == [True]
    assert database.read_bytes() == original_bytes


def test_v11_same_size_source_mtime_drift_during_hash_abstains(
    tmp_path, monkeypatch,
):
    """Physical metadata change is a seal failure even when SHA stays equal."""
    import os

    folder = _audit(tmp_path, multi=False)
    database = folder / "audit.db"
    original_bytes = database.read_bytes()
    original_open = Path.open
    updates = []

    class MutatingReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            if not updates:
                metadata = database.stat()
                os.utime(
                    database,
                    ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 30_000_000_000),
                )
                updates.append(True)
            return self.stream.read(size)

    def change_metadata_after_open(self, *args, **kwargs):
        stream = original_open(self, *args, **kwargs)
        if self == database and args and args[0] == "rb":
            return MutatingReader(stream)
        return stream

    monkeypatch.setattr(Path, "open", change_metadata_after_open)
    result = inspect_geo_per_query(folder)
    assert updates == [True]
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reason"] == "SOURCE_SCHEMA_OR_READ_FAILURE"
    assert result["queries"] == []
    assert result["source_audit_db_sha256"] is None
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert database.read_bytes() == original_bytes


def test_v11_path_inode_drift_during_hash_detected_on_windows_and_posix(
    tmp_path, monkeypatch,
):
    """Deterministic cross-platform stat/open/post-read identity mismatch."""
    from types import SimpleNamespace

    folder = _audit(tmp_path, multi=False)
    database = folder / "audit.db"
    original_bytes = database.read_bytes()
    real_stat = Path.stat
    calls = []

    def changed_path_stat(self, *args, **kwargs):
        stat = real_stat(self, *args, **kwargs)
        if self == database:
            calls.append(True)
            # First is Path.is_file(), next is the pre-open stat.
            # After the descriptor was already verified, the path points
            # at a distinct inode of the same size/mtime in the simulation.
            if len(calls) >= 3:
                return SimpleNamespace(
                    st_mode=stat.st_mode,
                    st_dev=stat.st_dev, st_ino=stat.st_ino + 1,
                    st_size=stat.st_size, st_mtime_ns=stat.st_mtime_ns,
                    st_ctime_ns=stat.st_ctime_ns,
                )
        return stat

    monkeypatch.setattr(Path, "stat", changed_path_stat)
    with pytest.raises(ValueError, match="physical identity changed"):
        ledger._audit_digest(database)
    assert len(calls) >= 3
    assert database.read_bytes() == original_bytes


def test_html_target_host_alternatives_require_verified_source_and_row(tmp_path):
    from rasai.geo_query_ledger_html_304 import render_geo_query_ledger_html

    folder = _audit(tmp_path, multi=False)
    _set_physical_aud_targets(folder, [
        ("AUD-GEO304", "https://example.org/shared"),
    ])
    projection = inspect_geo_per_query(folder)
    assert projection["status"] == "DESCRIPTIVE_ONLY"
    row = projection["queries"][0]
    assert row["serp_target_host_group"] is not None
    rendered = render_geo_query_ledger_html(projection)
    assert "Alternativas ao hostname da URL auditada" in rendered
    assert "SERP: URLs alternativas no hostname do alvo" in rendered
    assert "Search API: Hostnames distintos fora do alvo" in rendered
    assert "N/D" not in rendered.split("Alternativas ao hostname da URL auditada")[1].split("</table>")[0]

    # An unverified physical seal cannot disclose stale group counts.
    projection["source_audit_db_integrity_guard"] = "UNVERIFIED"
    masked = render_geo_query_ledger_html(projection)
    group = masked.split("Alternativas ao hostname da URL auditada")[1].split("</table>")[0]
    assert "<td>N/D</td>" in group
    assert "<td>1</td>" not in group
    # Individual abstention must also mask counts on a sealed projection.
    projection["source_audit_db_integrity_guard"] = "DOUBLE_SHA256_MATCH"
    row["status"] = "NOT_COMPARABLE"
    group = render_geo_query_ledger_html(projection).split(
        "Alternativas ao hostname da URL auditada"
    )[1].split("</table>")[0]
    assert "<td>N/D</td>" in group


def test_html_count_display_obeys_bounded_physical_geo_source_budget():
    from rasai.geo_query_ledger_html_304 import _count
    assert _count(500) == "500"
    assert _count(0) == "0"
    for invalid in (-1, 501, 10 ** 400, True, False, "7", 1.0):
        assert _count(invalid) == "N/D"
