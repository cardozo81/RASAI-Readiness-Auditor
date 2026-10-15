"""#311: read-only longitudinal GEO inventory, never a provider or CONS mutation."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from rasai.geo_longitudinal import build_geo_longitudinal_preview, main


def audit(
    tmp_path, aid, *, query="seguro de vida", url="https://example.org/seguro",
    scope_country="BR", scope_language="pt-BR", scope_device="mobile",
    scope_region="São Paulo", engine="google", mode="web",
    timestamp="2026-10-09T10:00:00Z", status="EXACT_URL_OBSERVED",
    version="RASAI-GEO-OBSERVATION-5", completion="COMPLETE",
    overlap_status="DESCRIPTIVE_ONLY", result_count=1,
):
    root = tmp_path / aid
    root.mkdir()
    projection = {
        "audit_id": aid, "contract_version": version,
        "perplexity_run_id": f"PX-{aid}", "search_status": "SUCCESS",
        "serp_observation_id": f"SERP-{aid}", "search_type": mode,
        "queries": [query],
        "target_observation": {
            "status": status, "query": query, "target_url": url,
            "evidence_run_id": f"PX-{aid}",
        },
        "comparability": {
            "perplexity_context": {
                "started_at": timestamp, "search_type": mode,
                "geography_language_device": None,
            },
            "serp_context": {
                "engine": engine, "country": scope_country,
                "region": scope_region, "language": scope_language,
                "device": scope_device,
                "collected_at": "2026-10-09T10:05:00Z",
            },
        },
        "descriptive_overlap": {
            "status": overlap_status, "serp_denominator": 3,
            "perplexity_denominator": 2, "common_urls": result_count,
        },
    }
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript("""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT
            );
            CREATE TABLE geo_observation_runs (
                analysis_id TEXT, audit_id TEXT, contract_version TEXT,
                projection_json TEXT, created_at TEXT,
                perplexity_run_id TEXT, serp_observation_id TEXT, input_sha256 TEXT
            );
            CREATE TABLE perplexity_search_runs (
                run_id TEXT PRIMARY KEY, audit_id TEXT, query_json TEXT,
                search_type TEXT, status TEXT, started_at TEXT
            );
            CREATE TABLE serp_observations (
                observation_id TEXT, audit_id TEXT, query TEXT, collected_at TEXT,
                data_mode TEXT, observation_status TEXT, engine TEXT,
                country TEXT, region TEXT, language TEXT, device TEXT
            );
        """)
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)", (aid, "COMPLETED", completion)
        )
        con.execute(
            "INSERT INTO geo_observation_runs VALUES (?,?,?,?,?,?,?,?)",
            (f"GEO-{aid}", aid, version, json.dumps(projection), timestamp,
             f"PX-{aid}", f"SERP-{aid}", "a" * 64),
        )
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            (f"PX-{aid}", aid, json.dumps([query]), mode, "SUCCESS", timestamp),
        )
        con.execute(
            "INSERT INTO serp_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (f"SERP-{aid}", aid, query, "2026-10-09T10:05:00Z", "OBSERVED_API",
             "OBSERVED", engine, scope_country, scope_region, scope_language,
             scope_device),
        )
    return root


def _v8_physical_sources(root):
    """Persist the exact Search/SERP URL sets attributed to a GEO v8 snapshot."""
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE perplexity_search_sources(run_id TEXT, url TEXT);
            CREATE TABLE serp_results(observation_id TEXT, url TEXT);
            CREATE TABLE audit_targets(audit_id TEXT, input_url TEXT);
        """)
        con.execute(
            "INSERT INTO audit_targets VALUES (?,?)",
            (root.name, "https://example.org/seguro"),
        )
        for url in (
            "https://example.org/seguro",
            "https://external-only.org/other",
        ):
            con.execute(
                "INSERT INTO perplexity_search_sources VALUES (?,?)",
                (f"PX-{root.name}", url),
            )
        for url in (
            "https://example.org/seguro",
            "https://serp-only.org/one",
            "https://serp-only.org/two",
        ):
            con.execute(
                "INSERT INTO serp_results VALUES (?,?)",
                (f"SERP-{root.name}", url),
            )
        projection = json.loads(con.execute(
            "SELECT projection_json FROM geo_observation_runs"
        ).fetchone()[0])
        projection.update(
            source_count=2, serp_url_count=3, perplexity_url_count=2,
            url_overlap_count=1,
        )
        projection["descriptive_overlap"].update(
            serp_denominator=3, perplexity_denominator=2,
            common_urls=1, serp_only_count=2, perplexity_only_count=1,
            serp_overlap_rate=0.3333, perplexity_overlap_rate=0.5,
            jaccard_url_rate=0.25,
        )
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=?",
            (json.dumps(projection),),
        )


@pytest.mark.parametrize(
    ("field", "kind", "expected_reason"),
    [
        ("query", "oversized_text", "GEO_SOURCE_PROVENANCE_UNVERIFIED"),
        ("query", "binary_json", "GEO_SOURCE_PROVENANCE_UNVERIFIED"),
        ("projection", "oversized_text", "GEO_PROJECTION_INVALID"),
        ("projection", "binary_json", "GEO_PROJECTION_INVALID"),
    ],
)
def test_v8_large_or_binary_json_abstains_without_decoding_unbounded_evidence(
    tmp_path, field, kind, expected_reason,
):
    altered = audit(tmp_path, "AUD-V8-UNBOUNDED", version="RASAI-GEO-OBSERVATION-8")
    stable = audit(tmp_path, "AUD-V8-STABLE", version="RASAI-GEO-OBSERVATION-8")
    for root in (altered, stable):
        _v8_physical_sources(root)
    db = altered / "audit.db"
    with sqlite3.connect(db) as con:
        table, column = (
            ("perplexity_search_runs", "query_json") if field == "query"
            else ("geo_observation_runs", "projection_json")
        )
        original = con.execute(f"SELECT {column} FROM {table}").fetchone()[0]
        assert isinstance(original, str)
        if kind == "oversized_text":
            budget = 16 * 1024 if field == "query" else 4 * 1024 * 1024
            value = " " * (budget + 1) + original
        else:
            value = original.encode("utf-8")
        # Both mutation classes are valid inputs to a permissive json.loads.
        assert json.loads(value) == json.loads(original)
        con.execute(f"UPDATE {table} SET {column}=?", (value,))
    before = {root.name: (root / "audit.db").read_bytes()
              for root in (altered, stable)}
    preview = build_geo_longitudinal_preview([altered, stable])
    assert preview["audits_eligible"] == 1
    assert {"audit_id": altered.name, "reason": expected_reason} in preview["excluded"]
    assert preview["timelines"][0]["observations"][0]["audit_id"] == stable.name
    assert preview["provider_requests"] == preview["audit_writes"] == 0
    assert all((root / "audit.db").read_bytes() == before[root.name]
               for root in (altered, stable))


@pytest.mark.parametrize(
    "duplicate_site",
    ("root_audit_id", "nested_target_query", "nested_serp_denominator"),
)
def test_v8_duplicate_snapshot_json_keys_refuse_longitudinal_observation(
    tmp_path, duplicate_site,
):
    """#311: last-key-wins in physical GEO v8 JSON cannot prove provenance."""
    altered = audit(
        tmp_path, "AUD-V8-AMBIGUOUS", version="RASAI-GEO-OBSERVATION-8",
    )
    intact = audit(
        tmp_path, "AUD-V8-INTACT", version="RASAI-GEO-OBSERVATION-8",
    )
    for root in (altered, intact):
        _v8_physical_sources(root)
    db = altered / "audit.db"
    with sqlite3.connect(db) as con:
        raw = con.execute(
            "SELECT projection_json FROM geo_observation_runs"
        ).fetchone()[0]
        if duplicate_site == "root_audit_id":
            invalid = '{"audit_id":"AUD-FORGED",' + raw[1:]
        elif duplicate_site == "nested_target_query":
            invalid = raw.replace(
                '"target_observation": {',
                '"target_observation": {"query": "forged-query", ',
                1,
            )
        else:
            invalid = raw.replace(
                '"descriptive_overlap": {',
                '"descriptive_overlap": {"serp_denominator": 999, ',
                1,
            )
        assert invalid != raw
        # The formerly permissive decoder resolves to the apparently
        # consistent *last* key, hiding the forged earlier assertion.
        assert json.loads(invalid) == json.loads(raw)
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=?",
            (invalid,),
        )
    before = {root.name: (root / "audit.db").read_bytes()
              for root in (altered, intact)}
    projection = build_geo_longitudinal_preview([altered, intact])
    assert projection["audits_eligible"] == 1
    assert projection["excluded"] == [{
        "audit_id": altered.name, "reason": "GEO_PROJECTION_INVALID",
    }]
    assert projection["timelines"][0]["observations"][0]["audit_id"] == intact.name
    assert projection["timelines"][0]["trend_rate"] is None
    assert projection["provider_requests"] == projection["audit_writes"] == 0
    assert all((root / "audit.db").read_bytes() == before[root.name]
               for root in (altered, intact))


def test_v8_source_observation_counts_are_reconciled_against_physical_sets(tmp_path):
    first = audit(tmp_path, "AUD-V8-ONE", version="RASAI-GEO-OBSERVATION-8")
    second = audit(tmp_path, "AUD-V8-TWO", version="RASAI-GEO-OBSERVATION-8")
    for root in (first, second):
        _v8_physical_sources(root)
    before = [(path / "audit.db").read_bytes() for path in (first, second)]
    preview = build_geo_longitudinal_preview([first, second])
    assert preview["audits_eligible"] == 2
    assert preview["timelines"][0]["trend_conclusion"] == "N/D"
    assert [row["url_intersection_observed"]
            for row in preview["timelines"][0]["observations"]] == [1, 1]
    assert [(path / "audit.db").read_bytes() for path in (first, second)] == before


@pytest.mark.parametrize(
    ("origin", "invalid_url"),
    [
        ("perplexity", "javascript:alert(1)"),
        ("perplexity", " https://external-only.org/other"),
        ("serp", "https://user:private@serp-only.org/two"),
        ("serp", "not a valid URL"),
    ],
)
def test_v8_invalid_physical_member_cannot_disappear_from_consistent_denominator(
    tmp_path, origin, invalid_url,
):
    """#311: even self-consistent forged overlap cannot omit invalid source."""
    from rasai.geo_observation import _canonical_url

    bad = audit(tmp_path, "AUD-V8-BAD-SAMPLE", version="RASAI-GEO-OBSERVATION-8")
    good = audit(tmp_path, "AUD-V8-GOOD-SAMPLE", version="RASAI-GEO-OBSERVATION-8")
    for root in (bad, good):
        _v8_physical_sources(root)
    db = bad / "audit.db"
    with sqlite3.connect(db) as con:
        if origin == "perplexity":
            con.execute(
                "UPDATE perplexity_search_sources SET url=? WHERE url=?",
                (invalid_url, "https://external-only.org/other"),
            )
        else:
            con.execute(
                "UPDATE serp_results SET url=? WHERE url=?",
                (invalid_url, "https://serp-only.org/two"),
            )
        # Recalculate all persisted metrics as if malformed observations
        # could be dropped; without the new guard this matches the reader.
        px_rows = [row[0] for row in con.execute(
            "SELECT url FROM perplexity_search_sources"
        )]
        serp_rows = [row[0] for row in con.execute(
            "SELECT url FROM serp_results"
        )]
        px = {_canonical_url(url) for url in px_rows} - {""}
        serp = {_canonical_url(url) for url in serp_rows} - {""}
        common = len(px & serp)
        snapshot = json.loads(con.execute(
            "SELECT projection_json FROM geo_observation_runs"
        ).fetchone()[0])
        snapshot.update(
            source_count=len(px_rows),
            serp_url_count=len(serp),
            perplexity_url_count=len(px),
            url_overlap_count=common,
        )
        snapshot["descriptive_overlap"].update(
            serp_denominator=len(serp),
            perplexity_denominator=len(px),
            common_urls=common,
            serp_only_count=len(serp - px),
            perplexity_only_count=len(px - serp),
            serp_overlap_rate=round(common / len(serp), 4),
            perplexity_overlap_rate=round(common / len(px), 4),
            jaccard_url_rate=round(common / len(px | serp), 4),
        )
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=?",
            (json.dumps(snapshot),),
        )
    originals = {root.name: (root / "audit.db").read_bytes()
                 for root in (bad, good)}
    projection = build_geo_longitudinal_preview([bad, good])
    assert projection["audits_requested"] == 2
    assert projection["audits_eligible"] == 1
    assert projection["excluded"] == [{
        "audit_id": bad.name,
        "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
    }]
    assert len(projection["timelines"]) == 1
    assert projection["timelines"][0]["observations"][0]["audit_id"] == good.name
    assert projection["timelines"][0]["trend_rate"] is None
    assert projection["provider_requests"] == projection["audit_writes"] == 0
    assert all((root / "audit.db").read_bytes() == originals[root.name]
               for root in (bad, good))


@pytest.mark.parametrize("oversized_ledger", ["perplexity", "serp"])
def test_v8_over_budget_physical_source_sets_abstain_even_with_correct_counters(
    tmp_path, oversized_ledger,
):
    large = audit(tmp_path, "AUD-V8-OVERSIZED", version="RASAI-GEO-OBSERVATION-8")
    stable = audit(tmp_path, "AUD-V8-STABLE", version="RASAI-GEO-OBSERVATION-8")
    for root in (large, stable):
        _v8_physical_sources(root)
    with sqlite3.connect(large / "audit.db") as con:
        if oversized_ledger == "perplexity":
            table, id_column, id_value, added = (
                "perplexity_search_sources", "run_id", f"PX-{large.name}", 499,
            )
        else:
            table, id_column, id_value, added = (
                "serp_results", "observation_id", f"SERP-{large.name}", 498,
            )
        con.executemany(
            f"INSERT INTO {table} ({id_column},url) VALUES (?,?)",
            [(id_value, f"https://excess-{i}.example.org/item") for i in range(added)],
        )
        px = {r[0] for r in con.execute(
            "SELECT url FROM perplexity_search_sources"
        )}
        serp = {r[0] for r in con.execute("SELECT url FROM serp_results")}
        both = len(px & serp)
        assert both == 1
        assert max(len(px), len(serp)) == 501
        projection = json.loads(con.execute(
            "SELECT projection_json FROM geo_observation_runs"
        ).fetchone()[0])
        projection.update(
            source_count=len(px), serp_url_count=len(serp),
            perplexity_url_count=len(px), url_overlap_count=both,
        )
        projection["descriptive_overlap"].update(
            serp_denominator=len(serp), perplexity_denominator=len(px),
            common_urls=both, serp_only_count=len(serp - px),
            perplexity_only_count=len(px - serp),
            serp_overlap_rate=round(both / len(serp), 4),
            perplexity_overlap_rate=round(both / len(px), 4),
            jaccard_url_rate=round(both / len(serp | px), 4),
        )
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=?",
            (json.dumps(projection),),
        )
    original = [(root / "audit.db").read_bytes() for root in (large, stable)]
    output = build_geo_longitudinal_preview([large, stable])
    assert output["audits_eligible"] == 1
    assert output["excluded"] == [{
        "audit_id": large.name, "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
    }]
    assert [(root / "audit.db").read_bytes() for root in (large, stable)] == original


@pytest.mark.parametrize(
    "forgery",
    ("foreign_target", "false_alternative_state", "missing_target_source", "duplicate_target"),
)
def test_v8_target_claim_must_match_physical_aud_and_search_sources(
    tmp_path, forgery,
):
    altered = audit(tmp_path, "AUD-V8-TARGET-FORGED", version="RASAI-GEO-OBSERVATION-8")
    stable = audit(tmp_path, "AUD-V8-TARGET-STABLE", version="RASAI-GEO-OBSERVATION-8")
    for root in (altered, stable):
        _v8_physical_sources(root)
    with sqlite3.connect(altered / "audit.db") as con:
        snapshot = json.loads(con.execute(
            "SELECT projection_json FROM geo_observation_runs"
        ).fetchone()[0])
        if forgery == "foreign_target":
            # An exact Search URL is still not the audited customer's URL.
            snapshot["target_observation"]["target_url"] = "https://external-only.org/other"
        elif forgery == "false_alternative_state":
            # An exact Search hit cannot be relabeled as merely alternative.
            snapshot["target_observation"]["status"] = "DOMAIN_ALTERNATIVE_OBSERVED"
        elif forgery == "duplicate_target":
            # Two persisted target rows cannot prove a unique AUD target.
            con.execute(
                "INSERT INTO audit_targets VALUES (?, ?)",
                (altered.name, "https://example.org/seguro"),
            )
        else:
            # Keep all overlap metrics physically correct while inventing
            # an EXACT_URL_OBSERVED state for a source set missing the URL.
            con.execute(
                "UPDATE perplexity_search_sources SET url=? WHERE url=?",
                ("https://unrelated.org/missing-target", "https://example.org/seguro"),
            )
            snapshot["url_overlap_count"] = 0
            snapshot["descriptive_overlap"].update(
                common_urls=0, serp_only_count=3, perplexity_only_count=2,
                serp_overlap_rate=0.0, perplexity_overlap_rate=0.0,
                jaccard_url_rate=0.0,
            )
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=?",
            (json.dumps(snapshot),),
        )
    originals = {root.name: (root / "audit.db").read_bytes()
                 for root in (altered, stable)}
    result = build_geo_longitudinal_preview([altered, stable])
    assert result["audits_eligible"] == 1
    assert result["excluded"] == [{
        "audit_id": altered.name, "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
    }]
    assert result["timelines"][0]["observations"][0]["audit_id"] == stable.name
    assert all((root / "audit.db").read_bytes() == originals[root.name]
               for root in (altered, stable))


def test_v8_source_drift_and_tampered_overlap_abstain_without_rewrite(tmp_path):
    drift = audit(tmp_path, "AUD-V8-DRIFT", version="RASAI-GEO-OBSERVATION-8")
    forged = audit(tmp_path, "AUD-V8-FORGED", version="RASAI-GEO-OBSERVATION-8")
    stable = audit(tmp_path, "AUD-V8-STABLE", version="RASAI-GEO-OBSERVATION-8")
    for source in (drift, forged, stable):
        _v8_physical_sources(source)
    with sqlite3.connect(drift / "audit.db") as con:
        con.execute(
            "UPDATE perplexity_search_sources SET url=? WHERE url=?",
            ("https://serp-only.org/one", "https://external-only.org/other"),
        )
    with sqlite3.connect(forged / "audit.db") as con:
        payload = json.loads(con.execute(
            "SELECT projection_json FROM geo_observation_runs"
        ).fetchone()[0])
        payload["descriptive_overlap"]["common_urls"] = 2
        con.execute(
            "UPDATE geo_observation_runs SET projection_json=?", (json.dumps(payload),)
        )
    original = [(root / "audit.db").read_bytes() for root in (drift, forged, stable)]
    output = build_geo_longitudinal_preview([drift, forged, stable])
    assert output["audits_eligible"] == 1
    assert {row["audit_id"]: row["reason"] for row in output["excluded"]} == {
        "AUD-V8-DRIFT": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
        "AUD-V8-FORGED": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
    }
    assert [(root / "audit.db").read_bytes()
            for root in (drift, forged, stable)] == original


def test_corrupted_projection_context_is_not_a_cons_runtime_exception(tmp_path):
    corrupted = audit(tmp_path, "AUD-BAD-CONTEXT")
    stable = audit(tmp_path, "AUD-VALID-CONTEXT")
    for broken in (None, [], "corrupt", 7):
        with sqlite3.connect(corrupted / "audit.db") as con:
            payload = json.loads(con.execute(
                "SELECT projection_json FROM geo_observation_runs"
            ).fetchone()[0])
            payload["comparability"] = broken
            con.execute(
                "UPDATE geo_observation_runs SET projection_json=?", (json.dumps(payload),)
            )
        original = (corrupted / "audit.db").read_bytes()
        output = build_geo_longitudinal_preview([corrupted, stable])
        assert output["audits_eligible"] == 1
        assert output["excluded"] == [{
            "audit_id": corrupted.name,
            "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
        }]
        assert (corrupted / "audit.db").read_bytes() == original


def test_two_comparable_provenance_records_stay_observational_not_trend(tmp_path):
    older = audit(tmp_path, "AUD-ONE", timestamp="2026-10-09T10:00:00Z")
    newer = audit(tmp_path, "AUD-TWO", timestamp="2026-10-09T11:00:00Z", result_count=0,
                  status="TARGET_NOT_IN_RETURNED_SOURCES")
    before = [sha256((root / "audit.db").read_bytes()).hexdigest()
              for root in (older, newer)]
    result = build_geo_longitudinal_preview([newer, older])
    assert result["audits_eligible"] == 2
    assert result["excluded"] == []
    assert result["observation_coverage"] == {
        "distinct_observed_scope_cohorts": 1,
        "single_observation_cohorts": 0,
        "multi_observation_cohorts_unverified_trend": 1,
        "eligible_auds_in_multi_observation_cohorts": 2,
        "excluded_auds_by_reason": {},
        "market_device_intent_sampling_equivalence_proven": False,
        "calibrated_geo_trend_cohorts": 0,
        "reason_counts_are_eligibility_only": True,
    }
    assert result["provider_requests"] == 0 and result["audit_writes"] == 0
    assert len(result["timelines"]) == 1
    timeline = result["timelines"][0]
    assert timeline["status"] == "OBSERVATIONAL_SEQUENCE_ONLY"
    assert timeline["trend_rate"] is None and timeline["trend_conclusion"] == "N/D"
    assert [x["audit_id"] for x in timeline["observations"]] == ["AUD-ONE", "AUD-TWO"]
    assert [x["url_intersection_observed"] for x in timeline["observations"]] == [1, 0]
    assert [sha256((root / "audit.db").read_bytes()).hexdigest()
            for root in (older, newer)] == before


def test_mixed_query_url_locale_device_and_mode_form_separate_groups(tmp_path):
    baseline = audit(tmp_path, "AUD-BASE")
    alt_query = audit(tmp_path, "AUD-Q", query="previdencia")
    alt_url = audit(tmp_path, "AUD-U", url="https://www.example.org/seguro")
    alt_region = audit(tmp_path, "AUD-R", scope_region="Rio de Janeiro")
    alt_device = audit(tmp_path, "AUD-D", scope_device="desktop")
    alt_mode = audit(tmp_path, "AUD-M", mode="fast")
    result = build_geo_longitudinal_preview([
        baseline, alt_query, alt_url, alt_region, alt_device, alt_mode,
    ])
    assert result["audits_eligible"] == 6
    assert len(result["timelines"]) == 6
    assert result["observation_coverage"]["single_observation_cohorts"] == 6
    assert result["observation_coverage"]["multi_observation_cohorts_unverified_trend"] == 0
    assert result["observation_coverage"]["eligible_auds_in_multi_observation_cohorts"] == 0
    assert all(x["status"] == "SINGLE_OBSERVATION" for x in result["timelines"])
    assert all(x["trend_rate"] is None for x in result["timelines"])


def test_legacy_partial_missing_scope_and_censored_sources_abstain(tmp_path):
    legacy = audit(tmp_path, "AUD-LEGACY", version="RASAI-GEO-OBSERVATION-4")
    partial = audit(tmp_path, "AUD-PARTIAL", completion="PARTIAL_RETRYABLE")
    unknown_scope = audit(tmp_path, "AUD-LOCALE", scope_country="")
    censored = audit(tmp_path, "AUD-CENSORED", overlap_status="NOT_COMPARABLE")
    result = build_geo_longitudinal_preview([legacy, partial, unknown_scope, censored])
    assert result["audits_eligible"] == 0
    reasons = {x["audit_id"]: x["reason"] for x in result["excluded"]}
    assert reasons["AUD-LEGACY"] == "GEO_LEGACY_OR_UNSUPPORTED_VERSION"
    assert reasons["AUD-PARTIAL"] == "AUD_COMPLETION_NOT_COMPLETE"
    assert reasons["AUD-LOCALE"] == "SERP_SCOPE_INCOMPLETE"
    assert reasons["AUD-CENSORED"] == "URL_DENOMINATOR_OR_COMPARABILITY_UNPROVEN"
    coverage = result["observation_coverage"]
    assert coverage["distinct_observed_scope_cohorts"] == 0
    assert coverage["excluded_auds_by_reason"] == {
        "AUD_COMPLETION_NOT_COMPLETE": 1,
        "GEO_LEGACY_OR_UNSUPPORTED_VERSION": 1,
        "SERP_SCOPE_INCOMPLETE": 1,
        "URL_DENOMINATOR_OR_COMPARABILITY_UNPROVEN": 1,
    }
    assert coverage["calibrated_geo_trend_cohorts"] == 0


def test_invalid_denominator_and_unmatched_source_instant_abstain(tmp_path):
    invalid = audit(tmp_path, "AUD-COUNT", result_count=8)
    far = audit(tmp_path, "AUD-TOO-OLD", timestamp="2026-10-07T10:00:00Z")
    out = build_geo_longitudinal_preview([invalid, far])
    assert out["audits_eligible"] == 0
    why = {x["audit_id"]: x["reason"] for x in out["excluded"]}
    assert why["AUD-COUNT"] == "URL_DENOMINATOR_INVALID"
    assert why["AUD-TOO-OLD"] == "SOURCE_TIME_WINDOW_NOT_ELIGIBLE"


def test_readonly_cli_json_and_duplicate_guard(tmp_path, capsys):
    source1 = audit(tmp_path, "AUD-FIRST")
    source2 = audit(tmp_path, "AUD-SECOND")
    assert main([str(source1), str(source2)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["contract_version"] == "RASAI-GEO-LONGITUDINAL-ADVISORY-001"
    assert output["audits_requested"] == 2
    with pytest.raises(ValueError, match="duplicate"):
        build_geo_longitudinal_preview([source1, source1])
    with pytest.raises(ValueError, match="2..100"):
        build_geo_longitudinal_preview([source1])



def test_tampered_snapshot_source_identity_and_unobserved_serp_abstain(tmp_path):
    source = audit(tmp_path, "AUD-SOURCE")
    normal = audit(tmp_path, "AUD-NORMAL")
    with sqlite3.connect(source / "audit.db") as con:
        con.execute(
            "UPDATE geo_observation_runs SET perplexity_run_id='PX-SPOOF'"
        )
    result = build_geo_longitudinal_preview([source, normal])
    assert result["audits_eligible"] == 1
    assert result["excluded"][0]["reason"] == "GEO_SOURCE_PROVENANCE_UNVERIFIED"

    source2 = audit(tmp_path, "AUD-SYNTHETIC")
    with sqlite3.connect(source2 / "audit.db") as con:
        con.execute("UPDATE serp_observations SET data_mode='SYNTHETIC'")
    result = build_geo_longitudinal_preview([source2, normal])
    assert result["audits_eligible"] == 1
    assert result["excluded"][0]["reason"] == "GEO_SOURCE_PROVENANCE_UNVERIFIED"


def test_duplicate_same_audit_serp_source_cannot_be_selected_arbitrarily(tmp_path):
    conflicted = audit(tmp_path, "AUD-DUPLICATE-SERP")
    reference = audit(tmp_path, "AUD-UNIQUE-SERP")
    with sqlite3.connect(conflicted / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT observation_id, audit_id, query, collected_at, data_mode, "
            "observation_status, engine, ?, region, language, device "
            "FROM serp_observations WHERE audit_id=?",
            ("US", conflicted.name),
        )
    original = [(p / "audit.db").read_bytes() for p in (conflicted, reference)]
    result = build_geo_longitudinal_preview([conflicted, reference])
    assert result["audits_eligible"] == 1
    assert result["excluded"] == [
        {"audit_id": conflicted.name, "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED"}
    ]
    assert result["timelines"][0]["observations"][0]["audit_id"] == reference.name
    assert [(p / "audit.db").read_bytes() for p in (conflicted, reference)] == original


def test_same_serp_id_but_foreign_audit_row_does_not_shadow_source(tmp_path):
    source = audit(tmp_path, "AUD-PROVEN-SERP")
    other = audit(tmp_path, "AUD-SECOND-SERP")
    with sqlite3.connect(source / "audit.db") as con:
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT observation_id, ?, query, collected_at, data_mode, "
            "observation_status, engine, ?, region, language, device "
            "FROM serp_observations WHERE audit_id=?",
            ("AUD-FOREIGN", "US", source.name),
        )
    original = [(p / "audit.db").read_bytes() for p in (source, other)]
    result = build_geo_longitudinal_preview([source, other])
    assert result["audits_eligible"] == 2
    assert result["excluded"] == []
    assert [(p / "audit.db").read_bytes() for p in (source, other)] == original


def test_mismatched_query_and_locale_against_source_abstains(tmp_path):
    first = audit(tmp_path, "AUD-MISMATCH")
    second = audit(tmp_path, "AUD-CLEAN")
    with sqlite3.connect(first / "audit.db") as con:
        con.execute("UPDATE serp_observations SET country='PT'")
    result = build_geo_longitudinal_preview([first, second])
    assert result["audits_eligible"] == 1
    assert result["excluded"][0]["reason"] == "GEO_SOURCE_PROVENANCE_UNVERIFIED"



def test_public_geo_longitudinal_entrypoint_bypasses_audit_installers(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint
    first = audit(tmp_path, "AUD-CONSOLE-1")
    second = audit(tmp_path, "AUD-CONSOLE-2")
    def no_audit_runtime():
        raise AssertionError("GEO history must never activate audit runtime")
    monkeypatch.setattr(entrypoint, "_install_audit_runtime", no_audit_runtime)
    result = entrypoint.main(["geo-longitudinal", str(first), str(second)])
    assert result == 0
    out = json.loads(capsys.readouterr().out)
    assert out["audits_eligible"] == 2
    assert out["provider_requests"] == 0
    alias = entrypoint.main(["geo-history", str(first), str(second)])
    assert alias == 0
    capsys.readouterr()



def test_readonly_diagnostic_distinguishes_audit_lifecycle_from_identity(tmp_path):
    foreign = audit(tmp_path, "AUD-FOREIGN")
    lifecycle = audit(tmp_path, "AUD-LIFECYCLE")
    completion = audit(tmp_path, "AUD-INCOMPLETE", completion="PARTIAL")
    duplicate = audit(tmp_path, "AUD-DUPLICATE")
    empty = audit(tmp_path, "AUD-EMPTY")
    with sqlite3.connect(foreign / "audit.db") as con:
        con.execute("UPDATE audits SET audit_id='AUD-OTHER'")
    with sqlite3.connect(lifecycle / "audit.db") as con:
        con.execute("UPDATE audits SET status='RUNNING'")
    with sqlite3.connect(duplicate / "audit.db") as con:
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)",
            ("AUD-OTHER", "COMPLETED", "COMPLETE"),
        )
    with sqlite3.connect(empty / "audit.db") as con:
        con.execute("DELETE FROM audits")
    folders = [foreign, lifecycle, completion, duplicate, empty]
    hashes = [(root / "audit.db").read_bytes() for root in folders]
    output = build_geo_longitudinal_preview(folders)
    reasons = {row["audit_id"]: row["reason"] for row in output["excluded"]}
    assert reasons == {
        "AUD-FOREIGN": "AUD_IDENTITY_MISMATCH",
        "AUD-LIFECYCLE": "AUD_LIFECYCLE_NOT_COMPLETED",
        "AUD-INCOMPLETE": "AUD_COMPLETION_NOT_COMPLETE",
        "AUD-DUPLICATE": "AUD_MULTIPLE_METADATA_ROWS",
        "AUD-EMPTY": "AUD_METADATA_ROW_MISSING",
    }
    assert output["audits_eligible"] == 0
    assert output["provider_requests"] == output["audit_writes"] == 0
    assert [(root / "audit.db").read_bytes() for root in folders] == hashes


def test_readonly_diagnostic_identifies_missing_legacy_tables_and_columns(tmp_path):
    metadata_missing = audit(tmp_path, "AUD-NO-AUDITS")
    metadata_legacy = audit(tmp_path, "AUD-LEGACY-META")
    geo_missing = audit(tmp_path, "AUD-NO-GEO")
    geo_legacy = audit(tmp_path, "AUD-LEGACY-GEO")
    with sqlite3.connect(metadata_missing / "audit.db") as con:
        con.execute("DROP TABLE audits")
    with sqlite3.connect(metadata_legacy / "audit.db") as con:
        con.execute("ALTER TABLE audits DROP COLUMN completion_status")
    with sqlite3.connect(geo_missing / "audit.db") as con:
        con.execute("DROP TABLE geo_observation_runs")
    with sqlite3.connect(geo_legacy / "audit.db") as con:
        con.execute("ALTER TABLE geo_observation_runs DROP COLUMN input_sha256")
    roots = [metadata_missing, metadata_legacy, geo_missing, geo_legacy]
    before = [sha256((root / "audit.db").read_bytes()).hexdigest() for root in roots]
    output = build_geo_longitudinal_preview(roots)
    reasons = {row["audit_id"]: row["reason"] for row in output["excluded"]}
    assert reasons == {
        "AUD-NO-AUDITS": "AUD_METADATA_TABLE_MISSING",
        "AUD-LEGACY-META": "AUD_METADATA_SCHEMA_UNSUPPORTED",
        "AUD-NO-GEO": "GEO_SNAPSHOT_TABLE_MISSING",
        "AUD-LEGACY-GEO": "GEO_SNAPSHOT_SCHEMA_UNSUPPORTED",
    }
    assert [sha256((root / "audit.db").read_bytes()).hexdigest()
            for root in roots] == before


def test_corrupt_sqlite_remains_explicit_technical_read_failure(tmp_path):
    corrupted = tmp_path / "AUD-CORRUPTED"
    corrupted.mkdir()
    (corrupted / "audit.db").write_bytes(b"not a valid sqlite database")
    good = audit(tmp_path, "AUD-GOOD")
    result = build_geo_longitudinal_preview([corrupted, good])
    assert result["audits_eligible"] == 1
    assert result["excluded"] == [{
        "audit_id": "AUD-CORRUPTED", "reason": "AUD_SCHEMA_OR_READ_ERROR",
    }]


def test_v5_v6_methodology_versions_never_share_a_longitudinal_group(tmp_path):
    old = audit(tmp_path, "AUD-OLD-METHOD", version="RASAI-GEO-OBSERVATION-5")
    current = audit(tmp_path, "AUD-NEW-METHOD", version="RASAI-GEO-OBSERVATION-6")
    result = build_geo_longitudinal_preview([old, current])
    assert result["audits_eligible"] == 2
    assert result["excluded"] == []
    assert len(result["timelines"]) == 2
    assert {x["method_version"] for x in result["timelines"]} == {
        "RASAI-GEO-OBSERVATION-5", "RASAI-GEO-OBSERVATION-6",
    }
    assert all(x["status"] == "SINGLE_OBSERVATION" for x in result["timelines"])
    assert all(x["trend_conclusion"] == "N/D" for x in result["timelines"])
    assert result["audit_writes"] == result["provider_requests"] == 0


def test_v7_longitudinal_selects_latest_snapshot_by_utc_not_lexical_string(tmp_path):
    first = audit(
        tmp_path, "AUD-V7-MULTI",
        version="RASAI-GEO-OBSERVATION-7",
    )
    second = audit(
        tmp_path, "AUD-V7-OTHER",
        version="RASAI-GEO-OBSERVATION-7",
    )
    db = first / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE geo_observation_runs SET created_at=? "
            "WHERE audit_id=?",
            ("2026-10-09T11:30:00+00:00", first.name),
        )
        payload = con.execute(
            "SELECT audit_id,contract_version,projection_json,"
            "perplexity_run_id,serp_observation_id,input_sha256 "
            "FROM geo_observation_runs WHERE audit_id=?", (first.name,),
        ).fetchone()
        con.execute(
            "INSERT INTO geo_observation_runs VALUES (?,?,?,?,?,?,?,?)",
            ("GEO-PHYSICALLY-NEWER", payload[0], payload[1],
             payload[2], "2026-10-09T09:00:00-03:00",
             payload[3], payload[4], payload[5]),
        )
    before = [sha256((root / "audit.db").read_bytes()).hexdigest()
              for root in (first, second)]
    result = build_geo_longitudinal_preview([first, second])
    assert result["audits_eligible"] == 2
    assert result["excluded"] == []
    timeline = result["timelines"][0]
    selected = {x["audit_id"]: x for x in timeline["observations"]}
    assert selected[first.name]["observation_id"] == "GEO-PHYSICALLY-NEWER"
    assert timeline["method_version"] == "RASAI-GEO-OBSERVATION-7"
    assert timeline["trend_rate"] is None
    assert [sha256((root / "audit.db").read_bytes()).hexdigest()
            for root in (first, second)] == before


@pytest.mark.parametrize(
    "second_clock",
    ["2026-10-09T09:00:00-03:00", "2026-10-09", None],
)
def test_longitudinal_abstains_on_tied_or_unverifiable_snapshot_clocks(
    tmp_path, second_clock,
):
    original = audit(
        tmp_path, "AUD-UNPROVEN", version="RASAI-GEO-OBSERVATION-7",
        timestamp="2026-10-09T12:00:00Z",
    )
    stable = audit(
        tmp_path, "AUD-STABLE", version="RASAI-GEO-OBSERVATION-7",
    )
    db = original / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "INSERT INTO geo_observation_runs "
            "SELECT ?, audit_id, contract_version, projection_json, ?, "
            "perplexity_run_id, serp_observation_id, input_sha256 "
            "FROM geo_observation_runs WHERE audit_id=?",
            ("GEO-SECOND", second_clock, original.name),
        )
    before = [sha256((root / "audit.db").read_bytes()).hexdigest()
              for root in (original, stable)]
    outcome = build_geo_longitudinal_preview([original, stable])
    assert outcome["audits_eligible"] == 1
    assert outcome["excluded"] == [{
        "audit_id": original.name,
        "reason": "GEO_SNAPSHOT_CHRONOLOGY_UNVERIFIABLE",
    }]
    assert outcome["provider_requests"] == outcome["audit_writes"] == 0
    assert [sha256((root / "audit.db").read_bytes()).hexdigest()
            for root in (original, stable)] == before


def test_v7_and_v8_url_identity_methodology_never_share_longitudinal_series(tmp_path):
    earlier = audit(
        tmp_path, "AUD-METHOD-007", version="RASAI-GEO-OBSERVATION-7",
    )
    later = audit(
        tmp_path, "AUD-METHOD-008", version="RASAI-GEO-OBSERVATION-8",
    )
    _v8_physical_sources(later)
    before = [p.joinpath("audit.db").read_bytes() for p in (earlier, later)]
    comparison = build_geo_longitudinal_preview([earlier, later])
    assert comparison["audits_eligible"] == 2
    assert comparison["excluded"] == []
    assert {x["method_version"] for x in comparison["timelines"]} == {
        "RASAI-GEO-OBSERVATION-7", "RASAI-GEO-OBSERVATION-8",
    }
    assert len(comparison["timelines"]) == 2
    assert all(x["status"] == "SINGLE_OBSERVATION" for x in comparison["timelines"])
    assert all(x["trend_conclusion"] == "N/D" for x in comparison["timelines"])
    assert comparison["provider_requests"] == comparison["audit_writes"] == 0
    assert [p.joinpath("audit.db").read_bytes() for p in (earlier, later)] == before


@pytest.mark.parametrize(
    ("later_status", "later_instant", "expected_reason"),
    [
        ("AUTH_ERROR", "2026-10-09T09:00:00-03:00", "GEO_LATEST_SEARCH_NOT_SUCCESSFUL"),
        ("SUCCESS", "2026-10-09T09:00:00-03:00", "GEO_SNAPSHOT_NOT_FROM_LATEST_SEARCH"),
        ("SUCCESS", "2026-10-09T10:00:00Z", "GEO_SEARCH_CHRONOLOGY_UNVERIFIABLE"),
        ("SUCCESS", "2026-10-09", "GEO_SEARCH_CHRONOLOGY_UNVERIFIABLE"),
    ],
)
def test_longitudinal_never_promotes_stale_geo_success_after_later_search(
    tmp_path, later_status, later_instant, expected_reason,
):
    source = audit(tmp_path, "AUD-SUPERSEDED")
    control = audit(tmp_path, "AUD-CURRENT")
    with sqlite3.connect(source / "audit.db") as con:
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            ("PX-NEXT", source.name, '["seguro de vida"]', "web",
             later_status, later_instant),
        )
    original = {
        path.name: (path / "audit.db").read_bytes()
        for path in (source, control)
    }
    result = build_geo_longitudinal_preview([source, control])
    assert result["audits_eligible"] == 1
    assert result["excluded"] == [
        {"audit_id": source.name, "reason": expected_reason}
    ]
    assert len(result["timelines"]) == 1
    assert result["timelines"][0]["observations"][0]["audit_id"] == control.name
    assert result["audit_writes"] == result["provider_requests"] == 0
    assert all((path / "audit.db").read_bytes() == original[path.name]
               for path in (source, control))


def test_longitudinal_keeps_current_success_when_older_failed_search_exists(
    tmp_path,
):
    source = audit(tmp_path, "AUD-RECOVERED")
    control = audit(tmp_path, "AUD-PAIR")
    with sqlite3.connect(source / "audit.db") as con:
        con.execute(
            "INSERT INTO perplexity_search_runs VALUES (?,?,?,?,?,?)",
            ("PX-OLDER-FAIL", source.name, '["seguro de vida"]',
             "web", "NETWORK_ERROR", "2026-10-09T09:59:59+00:00"),
        )
    before = [path.joinpath("audit.db").read_bytes() for path in (source, control)]
    outcome = build_geo_longitudinal_preview([source, control])
    assert outcome["audits_eligible"] == 2
    assert outcome["excluded"] == []
    assert outcome["timelines"][0]["status"] == "OBSERVATIONAL_SEQUENCE_ONLY"
    assert [path.joinpath("audit.db").read_bytes() for path in (source, control)] == before


def test_html_companion_is_escaped_observational_and_never_writes_aud_or_cons(
    tmp_path, capsys, monkeypatch,
):
    from rasai import entrypoint
    left = audit(
        tmp_path, "AUD-HTML-LEFT",
        query="seguro <img src=x onerror=alert(1)>",
        scope_region="São Paulo <script>unexpected()</script>",
    )
    right = audit(
        tmp_path, "AUD-HTML-RIGHT",
        query="seguro <img src=x onerror=alert(1)>",
        scope_region="São Paulo <script>unexpected()</script>",
    )
    before = [
        (path / "audit.db").read_bytes() for path in (left, right)
    ]
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("HTML read-only mode must not install audit runtime"),
    )
    assert entrypoint.main([
        "geo-longitudinal", "--format", "html", str(left), str(right),
    ]) == 0
    html = capsys.readouterr().out
    assert html.startswith("<!doctype html>")
    assert "<h1>Inventário GEO longitudinal" in html
    assert "AUD-HTML-LEFT" in html and "AUD-HTML-RIGHT" in html
    assert "OBSERVATIONAL_SEQUENCE_ONLY" in html
    assert "tendência: <strong>N/D</strong>" in html
    assert "Cobertura observacional e abstenções" in html
    assert "coortes com duas ou mais observações: 1" in html
    assert "Coortes com tendência GEO calibrada: N/D" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;script&gt;unexpected()&lt;/script&gt;" in html
    assert "<script>unexpected()</script>" not in html
    assert "não significa citação" in html
    assert [path.joinpath("audit.db").read_bytes() for path in (left, right)] == before
    assert all(not (path / "report-catalog").exists() for path in (left, right))
    assert not list(tmp_path.glob("CONS-*"))


def test_html_companion_explicitly_shows_rejected_and_empty_groups(
    tmp_path, capsys,
):
    from rasai.geo_longitudinal_html import render_geo_longitudinal_html
    first = audit(tmp_path, "AUD-WITH-GEO")
    second = tmp_path / "AUD-LEGACY-NO-DATABASE"
    second.mkdir()
    preview = build_geo_longitudinal_preview([first, second])
    html = render_geo_longitudinal_html(preview)
    assert "<th>Motivo verificável</th>" in html
    assert "AUD-LEGACY-NO-DATABASE" in html
    assert "AUD_DATABASE_MISSING" in html
    assert "Cobertura observacional e abstenções" in html
    assert "<th>Quantidade de AUDs</th>" in html
    assert "SINGLE_OBSERVATION" in html
    assert "tendência: <strong>N/D</strong>" in html
    assert "provider_requests" not in html  # does not invent commercial measurements
    assert main(["--format", "json", str(first), str(second)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_requests"] == payload["audit_writes"] == 0
    assert payload["audits_eligible"] == 1

    fake = dict(preview)
    fake["timelines"] = []
    fake["excluded"] = [
        {"audit_id": "<img src=x onerror=alert(1)>", "reason": "<script>unsafe</script>"}
    ]
    empty_html = render_geo_longitudinal_html(fake)
    assert "Nenhuma coorte GEO longitudinal elegível" in empty_html
    assert "<script>unsafe</script>" not in empty_html
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in empty_html
    assert "&lt;img src=x onerror=alert(1)&gt;" in empty_html


def test_v8_rejects_cross_aud_duplicate_serp_id_even_when_url_totals_match(
    tmp_path,
):
    ambiguous = audit(
        tmp_path, "AUD-V8-FOREIGN-ID", version="RASAI-GEO-OBSERVATION-8",
    )
    stable = audit(
        tmp_path, "AUD-V8-UNIQUE-ID", version="RASAI-GEO-OBSERVATION-8",
    )
    for aud in (ambiguous, stable):
        _v8_physical_sources(aud)
    with sqlite3.connect(ambiguous / "audit.db") as con:
        # Foreign metadata reuses exactly the same observation_id. Its
        # result duplicates an existing URL, so distinct URL totals alone
        # cannot detect the cross-AUD attribution ambiguity.
        con.execute(
            "INSERT INTO serp_observations "
            "SELECT observation_id, 'AUD-FOREIGN', query, collected_at, "
            "data_mode, observation_status, engine, country, region, "
            "language, device FROM serp_observations WHERE audit_id=?",
            (ambiguous.name,),
        )
        con.execute(
            "INSERT INTO serp_results VALUES (?,?)",
            (f"SERP-{ambiguous.name}", "https://example.org/seguro"),
        )
    before = {
        aud.name: (aud / "audit.db").read_bytes()
        for aud in (ambiguous, stable)
    }
    result = build_geo_longitudinal_preview([ambiguous, stable])
    assert result["audits_eligible"] == 1
    assert result["excluded"] == [{
        "audit_id": ambiguous.name,
        "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED",
    }]
    assert result["timelines"][0]["observations"][0]["audit_id"] == stable.name
    assert result["timelines"][0]["trend_conclusion"] == "N/D"
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert all((aud / "audit.db").read_bytes() == before[aud.name]
               for aud in (ambiguous, stable))


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_longitudinal_rejects_unsealed_sqlite_sidecars_before_read(
    tmp_path, suffix,
):
    unsealed = audit(tmp_path, "AUD-GEO-UNSEALED")
    stable = audit(tmp_path, "AUD-GEO-SEALED")
    sidecar = unsealed / ("audit.db" + suffix)
    sidecar.write_bytes(b"simulated-incomplete-transaction")
    before = [(aud / "audit.db").read_bytes() for aud in (unsealed, stable)]
    preview = build_geo_longitudinal_preview([unsealed, stable])
    assert preview["audits_eligible"] == 1
    assert preview["excluded"] == [{
        "audit_id": unsealed.name,
        "reason": "AUD_SQLITE_SNAPSHOT_UNVERIFIED",
    }]
    assert preview["timelines"][0]["observations"][0]["audit_id"] == stable.name
    assert preview["timelines"][0]["trend_conclusion"] == "N/D"
    assert [(aud / "audit.db").read_bytes()
            for aud in (unsealed, stable)] == before
    assert sidecar.read_bytes() == b"simulated-incomplete-transaction"


def test_longitudinal_abstains_when_db_changes_between_snapshot_and_source_reads(
    tmp_path, monkeypatch,
):
    from rasai import geo_longitudinal as module
    moving = audit(tmp_path, "AUD-MOVING-SOURCE")
    stable = audit(tmp_path, "AUD-STABLE-SOURCE")
    original = (moving / "audit.db").read_bytes()
    real = module._one_unsealed

    def physical_change_after_source_reads(root):
        result = real(root)
        if root.name == moving.name:
            with (root / "audit.db").open("ab") as stream:
                stream.write(b"physical-bytes-changed")
        return result

    monkeypatch.setattr(module, "_one_unsealed", physical_change_after_source_reads)
    output = build_geo_longitudinal_preview((moving, stable))
    assert output["audits_eligible"] == 1
    assert output["excluded"] == [
        {"audit_id": moving.name, "reason": "AUD_SOURCE_CHANGED_DURING_READ"}
    ]
    assert output["timelines"][0]["observations"][0]["audit_id"] == stable.name
    assert (moving / "audit.db").read_bytes() == original + b"physical-bytes-changed"


def test_longitudinal_abstains_on_new_wal_after_independent_source_reads(
    tmp_path, monkeypatch,
):
    from rasai import geo_longitudinal as module
    moving = audit(tmp_path, "AUD-SIDECAR-DURING-READ")
    stable = audit(tmp_path, "AUD-UNCHANGED")
    original = (moving / "audit.db").read_bytes()
    real = module._one_unsealed

    def sidecar_after_source_reads(root):
        result = real(root)
        if root.name == moving.name:
            (root / "audit.db-wal").write_bytes(b"pending-transaction")
        return result

    monkeypatch.setattr(module, "_one_unsealed", sidecar_after_source_reads)
    output = build_geo_longitudinal_preview((moving, stable))
    assert output["audits_eligible"] == 1
    assert output["excluded"][0] == {
        "audit_id": moving.name, "reason": "AUD_SOURCE_CHANGED_DURING_READ",
    }
    assert (moving / "audit.db").read_bytes() == original
    assert (moving / "audit.db-wal").read_bytes() == b"pending-transaction"


def test_longitudinal_rejects_source_over_hash_budget_without_querying_sqlite(
    tmp_path, monkeypatch,
):
    from rasai import geo_longitudinal as module
    large = audit(tmp_path, "AUD-OVER-BYTE-BUDGET")
    stable = audit(tmp_path, "AUD-IN-BUDGET")
    db = large / "audit.db"
    # Create a source larger than the intact companion regardless of
    # audit-ID length or SQLite page-allocation details on each OS.
    with db.open("ab") as stream:
        stream.write(b"over-budget-physical-source" * 1000)
    original = db.read_bytes()
    stable_size = (stable / "audit.db").stat().st_size
    assert len(original) > stable_size
    old_limit = module._MAX_AUD_DB_HASH_BYTES
    monkeypatch.setattr(module, "_MAX_AUD_DB_HASH_BYTES", stable_size)
    try:
        result = build_geo_longitudinal_preview((large, stable))
    finally:
        monkeypatch.setattr(module, "_MAX_AUD_DB_HASH_BYTES", old_limit)
    assert result["audits_eligible"] == 1
    assert result["excluded"][0] == {
        "audit_id": large.name, "reason": "AUD_SOURCE_BYTES_UNVERIFIABLE",
    }
    assert db.read_bytes() == original


def test_longitudinal_no_mutation_of_eligible_sources_after_hash_seal(tmp_path):
    left = audit(tmp_path, "AUD-SEALED-LEFT")
    right = audit(tmp_path, "AUD-SEALED-RIGHT")
    original = [(db / "audit.db").read_bytes() for db in (left, right)]
    value = build_geo_longitudinal_preview((left, right))
    assert value["audits_eligible"] == 2
    assert value["excluded"] == []
    assert [(db / "audit.db").read_bytes() for db in (left, right)] == original
    assert all(not list(db.glob("audit.db-*")) for db in (left, right))


def test_v8_extreme_overlap_integer_abstains_without_float_overflow(tmp_path):
    invalid = audit(tmp_path, "AUD-V8-RATE-INVALID", version="RASAI-GEO-OBSERVATION-8")
    valid = audit(tmp_path, "AUD-V8-RATE-VALID", version="RASAI-GEO-OBSERVATION-8")
    for root in (invalid, valid):
        _v8_physical_sources(root)
    db = invalid / "audit.db"
    with sqlite3.connect(db) as con:
        raw = con.execute("SELECT projection_json FROM geo_observation_runs").fetchone()[0]
        projection = json.loads(raw)
        projection["descriptive_overlap"]["serp_overlap_rate"] = 10 ** 400
        con.execute("UPDATE geo_observation_runs SET projection_json=?", (
            json.dumps(projection), 
        ))
    original = db.read_bytes()
    result = build_geo_longitudinal_preview((invalid, valid))
    assert result["audits_eligible"] == 1
    assert {"audit_id": invalid.name, "reason": "GEO_SOURCE_PROVENANCE_UNVERIFIED"} in result["excluded"]
    assert db.read_bytes() == original
