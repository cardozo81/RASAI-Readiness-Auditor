"""#319 isolated ledger reconciliation; never requires a full AUD."""
from __future__ import annotations

import sqlite3

from rasai.audit_attempt_timeline import read_audit_attempt_timeline


def test_chronology_joins_m18_and_m20_without_double_counting(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
        CREATE TABLE ai_provider_attempts (
          attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,
          surface TEXT, started_at TEXT, finished_at TEXT, duration_ms INTEGER,
          estimated_cost REAL, cost_currency TEXT,
          observed_cost REAL, observed_cost_currency TEXT
        );
        CREATE TABLE content_remediation_attempts (
          attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,
          started_at TEXT, finished_at TEXT, duration_ms INTEGER,
          estimated_cost REAL, cost_currency TEXT,
          observed_cost REAL, observed_cost_currency TEXT
        );
    """)
    connection.executemany(
        "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("A1", "AUD-A", "IMPROVEMENT_INTELLIGENCE", None,
             "2026-10-08T11:00:00-03:00", "2026-10-08T11:02:00-03:00",
             120000, .02, "USD", None, None),
            ("A2", "AUD-A", "DIRECTED_ANALYSIS", None,
             "2026-10-08T11:01:00-03:00", "2026-10-08T11:03:00-03:00",
             120000, .03, "USD", None, None),
            ("PX", "AUD-A", "SEARCH_INTELLIGENCE", "SEARCH_API",
             "2026-10-08T11:03:00-03:00", "2026-10-08T11:03:01-03:00",
             1000, .01, "USD", None, None),
            ("OTHER", "AUD-B", "IMPROVEMENT_INTELLIGENCE", None,
             "2026-10-08T11:01:00-03:00", "2026-10-08T11:02:00-03:00",
             60000, .5, "USD", None, None),
        ],
    )
    connection.execute(
        "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("M20", "AUD-A", "CONTENT_REMEDIATION",
         "2026-10-08T11:04:00-03:00", "2026-10-08T11:04:40-03:00",
         40000, .1, "USD", .08, "USD"),
    )
    connection.commit()
    connection.close()
    outcome = read_audit_attempt_timeline(database, "AUD-A")
    assert outcome.attempts == 4
    assert outcome.summed_duration_ms == 281000
    assert outcome.union_active_ms == 221000
    assert outcome.overlapping_duration_ms == 60000
    assert abs(outcome.posthoc_estimated_usd - .06) < 1e-8
    assert abs(outcome.provider_observed_usd - .08) < 1e-8
    assert outcome.non_ai_stages_measured is False
    assert {stage.name for stage in outcome.stages} == {
        "IMPROVEMENT_INTELLIGENCE", "DIRECTED_ANALYSIS",
        "EXTERNAL_SEARCH_API", "CONTENT_REMEDIATION",
    }
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT COUNT(*) FROM ai_provider_attempts").fetchone()[0] == 4
    connection.close()


def test_missing_tables_returns_honest_empty_observation(tmp_path):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE audits(audit_id TEXT PRIMARY KEY)")
    result = read_audit_attempt_timeline(database, "AUD-NO-ATTEMPTS")
    assert result.attempts == 0
    assert result.union_active_ms == 0
    assert result.non_ai_stages_measured is False


def test_unknown_timestamps_not_falsely_summed_as_wall_time(tmp_path):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT, "
            "duration_ms INTEGER, started_at TEXT, finished_at TEXT, estimated_cost REAL, cost_currency TEXT)"
        )
        connection.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("A1", "AUD-T", "OTHER", 45000, "unknown", "unknown", .01, "USD"),
        )
    result = read_audit_attempt_timeline(database, "AUD-T")
    assert result.summed_duration_ms == 45000
    assert result.unknown_intervals == 1
    assert result.union_active_ms is None


def test_union_cannot_exceed_summed_timing_when_reported_duration_is_rounded(tmp_path):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,"
            "duration_ms INTEGER, started_at TEXT, finished_at TEXT,"
            "estimated_cost REAL, cost_currency TEXT,"
            "observed_cost REAL, observed_cost_currency TEXT)"
        )
        connection.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("A1", "AUD-T", "IMPROVEMENT_INTELLIGENCE", 122764,
                 "2026-10-08T14:16:46.503559+00:00",
                 "2026-10-08T14:18:49.285950+00:00", .02, "USD", None, None),
                ("A2", "AUD-T", "IMPROVEMENT_INTELLIGENCE", 173103,
                 "2026-10-08T14:18:49.338513+00:00",
                 "2026-10-08T14:21:42.444117+00:00", .03, "USD", None, None),
            ],
        )
    result = read_audit_attempt_timeline(database, "AUD-T")
    stage = result.stages[0]
    assert stage.observed_cost_attempts == 0
    assert stage.unknown_intervals == 0
    assert abs(stage.summed_duration_ms - stage.union_active_ms) < 0.001
    assert abs(stage.summed_duration_ms - 295887.995) < .1
    assert stage.overlapping_duration_ms == 0


def test_provider_cost_coverage_distinguishes_unavailable_from_observed_zero(tmp_path):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,"
            "duration_ms INTEGER, started_at TEXT, finished_at TEXT,"
            "observed_cost REAL, observed_cost_currency TEXT)"
        )
        connection.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)",
            [
                ("A1", "AUD-C", "WITH_OBSERVED", 1000,
                 "2026-10-08T15:00:00+00:00", "2026-10-08T15:00:01+00:00",
                 0.0, "USD"),
                ("A2", "AUD-C", "WITHOUT_OBSERVED", 1000,
                 "2026-10-08T15:00:02+00:00", "2026-10-08T15:00:03+00:00",
                 None, None),
            ],
        )
    result = read_audit_attempt_timeline(database, "AUD-C")
    stages = {row.name: row for row in result.stages}
    assert stages["WITH_OBSERVED"].observed_cost_attempts == 1
    assert stages["WITH_OBSERVED"].priced_usd_provider_observed == 0.0
    assert stages["WITHOUT_OBSERVED"].observed_cost_attempts == 0
