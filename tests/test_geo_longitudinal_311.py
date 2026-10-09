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
    from rasai.geo_longitudinal_html_311 import render_geo_longitudinal_html
    first = audit(tmp_path, "AUD-WITH-GEO")
    second = tmp_path / "AUD-LEGACY-NO-DATABASE"
    second.mkdir()
    preview = build_geo_longitudinal_preview([first, second])
    html = render_geo_longitudinal_html(preview)
    assert "<th>Motivo verificável</th>" in html
    assert "AUD-LEGACY-NO-DATABASE" in html
    assert "AUD_DATABASE_MISSING" in html
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
