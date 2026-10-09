"""#311: read-only longitudinal GEO inventory, never a provider or CONS mutation."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3

import pytest

from rasai.geo_longitudinal_311 import build_geo_longitudinal_preview, main


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


def test_two_comparable_provenance_records_stay_observational_not_trend(tmp_path):
    older = audit(tmp_path, "AUD-ONE", timestamp="2026-10-09T10:00:00Z")
    newer = audit(tmp_path, "AUD-TWO", timestamp="2026-10-09T11:00:00Z", result_count=0,
                  status="TARGET_NOT_IN_RETURNED_SOURCES")
    before = [sha256((root / "audit.db").read_bytes()).hexdigest()
              for root in (older, newer)]
    result = build_geo_longitudinal_preview([newer, older])
    assert result["audits_eligible"] == 2
    assert result["excluded"] == []
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
