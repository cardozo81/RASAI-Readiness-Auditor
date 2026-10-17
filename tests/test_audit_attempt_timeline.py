"""#319 isolated ledger reconciliation; never requires a full AUD."""
from __future__ import annotations

import sqlite3

import pytest

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



def test_invalid_numeric_cost_and_duration_do_not_poison_319_projection(tmp_path):
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT PRIMARY KEY, audit_id TEXT, operation TEXT,"
            "duration_ms REAL, started_at TEXT, finished_at TEXT,"
            "estimated_cost REAL, cost_currency TEXT,"
            "observed_cost REAL, observed_cost_currency TEXT)"
        )
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("A1", "AUD-C", "IMPROVEMENT_INTELLIGENCE",
                 float("nan"), "?", "?", float("nan"), "USD", None, None),
                ("A2", "AUD-C", "DIRECTED_ANALYSIS",
                 float("inf"), "?", "?", 0.01, "USD", float("inf"), "USD"),
                ("A3", "AUD-C", "OTHER",
                 -10, "?", "?", -1.0, "USD", None, None),
            ],
        )
    before = database.read_bytes()
    result = read_audit_attempt_timeline(database, "AUD-C")
    assert result.attempts == 3
    assert result.unknown_intervals == 3
    assert result.union_active_ms is None
    assert result.summed_duration_ms == 0
    assert result.provider_observed_usd == 0
    assert result.posthoc_estimated_usd == 0
    assert result.unpriced_attempts == 3
    assert database.read_bytes() == before


def test_timeline_rejects_duplicate_ai_attempt_identity_without_undercount(
    tmp_path,
):
    import pytest
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT, audit_id TEXT, operation TEXT, "
            "started_at TEXT, finished_at TEXT, "
            "observed_cost REAL, observed_cost_currency TEXT)"
        )
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?)",
            [
                ("DUP", "AUD-SELF", "COMPETITIVE_AI",
                 "2026-10-12T10:00:00Z", "2026-10-12T10:00:02Z", .1, "USD"),
                ("DUP", "AUD-SELF", "IMPROVEMENT_INTELLIGENCE",
                 "2026-10-12T10:00:02Z", "2026-10-12T10:00:08Z", .2, "USD"),
                ("DUP", "AUD-OTHER", "DIRECTED_ANALYSIS",
                 "2026-10-12T10:00:01Z", "2026-10-12T10:01:00Z", 900, "USD"),
            ],
        )
    original = db.read_bytes()
    with pytest.raises(ValueError, match="ambiguous AI attempt_id"):
        read_audit_attempt_timeline(db, "AUD-SELF")
    assert db.read_bytes() == original


def test_timeline_same_attempt_id_in_distinct_auds_is_not_source_collision(
    tmp_path,
):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT, audit_id TEXT, operation TEXT, "
            "started_at TEXT, finished_at TEXT, "
            "observed_cost REAL, observed_cost_currency TEXT)"
        )
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?)",
            [
                ("AUD-LOCAL-ID", "AUD-A", "OTHER",
                 "2026-10-12T10:00:00Z", "2026-10-12T10:00:02Z", .01, "USD"),
                ("AUD-LOCAL-ID", "AUD-B", "OTHER",
                 "2026-10-12T10:00:00Z", "2026-10-12T10:00:02Z", 10, "USD"),
            ],
        )
    original = db.read_bytes()
    result = read_audit_attempt_timeline(db, "AUD-A")
    assert result.attempts == 1
    assert result.provider_observed_usd == .01
    assert db.read_bytes() == original


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_immutable_timeline_opt_in_abstains_before_reading_unsealed_sqlite(
    tmp_path, suffix,
):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE ai_provider_attempts(attempt_id TEXT, audit_id TEXT)")
    original = db.read_bytes()
    journal = tmp_path / ("audit.db" + suffix)
    journal.write_bytes(b"uncheckpointed")
    with pytest.raises(ValueError, match="unverified WAL/SHM/journal"):
        read_audit_attempt_timeline(db, "AUD-SELF", sealed_source=True)
    assert db.read_bytes() == original
    assert journal.read_bytes() == b"uncheckpointed"


def test_immutable_timeline_opt_in_does_not_change_normal_read_only_semantics(
    tmp_path,
):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE ai_provider_attempts("
            "attempt_id TEXT, audit_id TEXT, operation TEXT, "
            "started_at TEXT, finished_at TEXT)"
        )
        con.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?)",
            ("ID-1", "AUD-SELF", "DIRECTED_ANALYSIS",
             "2026-10-12T10:00:00Z", "2026-10-12T10:00:01Z"),
        )
    original = db.read_bytes()
    sealed = read_audit_attempt_timeline(db, "AUD-SELF", sealed_source=True)
    legacy = read_audit_attempt_timeline(db, "AUD-SELF")
    assert sealed == legacy
    assert sealed.attempts == 1
    assert db.read_bytes() == original


def test_duplicate_attempt_id_across_ai_ledgers_refuses_ambiguous_total(tmp_path):
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        for table in ("ai_provider_attempts", "content_remediation_attempts"):
            con.execute(f"CREATE TABLE {table}(attempt_id TEXT, audit_id TEXT, operation TEXT, started_at TEXT, finished_at TEXT)")
            con.execute(
                f"INSERT INTO {table} VALUES (?,?,?,?,?)",
                ("SHARED", "AUD-LOCAL", "IMPROVEMENT_INTELLIGENCE",
                 "2026-10-12T10:00:00Z", "2026-10-12T10:00:02Z"),
            )
    original = db.read_bytes()
    with pytest.raises(ValueError, match="across physical ledgers"):
        read_audit_attempt_timeline(db, "AUD-LOCAL")
    assert db.read_bytes() == original


def test_timeline_abstains_before_materializing_unbounded_attempt_population(tmp_path):
    from rasai import audit_attempt_timeline as module
    db = tmp_path / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE ai_provider_attempts(attempt_id TEXT, audit_id TEXT)")
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?)",
            ((f"ID-{index}", "AUD-MANY") for index in range(module._MAX_LEDGER_ROWS + 1)),
        )
    original = db.read_bytes()
    with pytest.raises(ValueError, match="population exceeded"):
        read_audit_attempt_timeline(db, "AUD-MANY")
    assert db.read_bytes() == original


@pytest.mark.parametrize("nonphysical_duration", [True, False])
def test_boolean_duration_never_counts_as_elapsed_milliseconds(nonphysical_duration):
    """An invalid ledger clock cannot silently become one millisecond."""
    from rasai.audit_attempt_timeline import _stage

    stage = _stage("OTHER_AI", [{
        "started_at": None, "finished_at": None,
        "duration_ms": nonphysical_duration,
        "observed_cost": None, "estimated_cost": None,
    }])
    assert stage.attempts == 1
    assert stage.unknown_intervals == 1
    assert stage.summed_duration_ms == 0
    assert stage.union_active_ms is None
    assert stage.unpriced_attempts == 1


def test_eight_physical_ai_attempts_include_content_remediation_without_extra_aud(tmp_path):
    """#319: seven general AI attempts plus one remediation equals eight, not seven."""
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.executescript("""
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
        rows = [
            (f"AI{i}", "AUD-319", "IMPROVEMENT_INTELLIGENCE", None,
             f"2026-10-08T11:{i:02d}:00+00:00",
             f"2026-10-08T11:{i:02d}:10+00:00",
             10000, .01, "USD", None, None)
            for i in range(7)
        ]
        con.executemany(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        con.execute(
            "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
            ("R1", "AUD-319", "CONTENT_REMEDIATION",
             "2026-10-08T11:07:00+00:00", "2026-10-08T11:07:10+00:00",
             10000, .02, "USD", None, None),
        )
        con.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("OTHER", "AUD-OTHER", "DIRECTED_ANALYSIS", None,
             "2026-10-08T11:08:00+00:00", "2026-10-08T11:08:10+00:00",
             10000, .99, "USD", None, None),
        )
    original = database.read_bytes()
    result = read_audit_attempt_timeline(database, "AUD-319")
    assert result.attempts == 8
    assert result.summed_duration_ms == 80000
    assert result.union_active_ms == 80000
    assert {stage.name: stage.attempts for stage in result.stages} == {
        "IMPROVEMENT_INTELLIGENCE": 7, "CONTENT_REMEDIATION": 1,
    }
    assert abs(result.posthoc_estimated_usd - .09) < 1e-9
    assert database.read_bytes() == original


@pytest.mark.parametrize("bad_id", [" A1", "A1 ", "A\n1", "A\t1"])
def test_noncanonical_ai_ledger_attempt_identity_refuses_cost_census(tmp_path, bad_id):
    """Never turn two physical attempt identities into the same normalized ID."""
    database = tmp_path / "audit.db"
    with sqlite3.connect(database) as con:
        con.execute(
            "CREATE TABLE ai_provider_attempts ("
            "attempt_id TEXT, audit_id TEXT, operation TEXT, "
            "started_at TEXT, finished_at TEXT, duration_ms INTEGER)"
        )
        con.execute(
            "INSERT INTO ai_provider_attempts VALUES (?, ?, ?, ?, ?, ?)",
            (bad_id, "AUD-A", "OTHER_AI", None, None, 1000),
        )
    before = database.read_bytes()
    with pytest.raises(ValueError, match="ambiguous AI attempt_id"):
        read_audit_attempt_timeline(database, "AUD-A")
    assert database.read_bytes() == before
