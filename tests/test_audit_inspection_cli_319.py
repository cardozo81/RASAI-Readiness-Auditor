"""#319: isolated Windows-compatible, read-only audit attempt inventory."""
from __future__ import annotations

import json
import sqlite3

import pytest

from rasai.audit_attempt_inspection_319 import inspect_audit_attempts, main


def _fixture(tmp_path):
    root = tmp_path / "AUD-NEW-COMPLETE"
    root.mkdir()
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.executescript("""
            CREATE TABLE audits (
                audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT
            );
            CREATE TABLE ai_provider_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                operation TEXT, started_at TEXT, finished_at TEXT,
                duration_ms REAL, estimated_cost REAL, cost_currency TEXT
            );
            CREATE TABLE content_remediation_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                operation TEXT, started_at TEXT, finished_at TEXT,
                duration_ms REAL, observed_cost REAL, observed_cost_currency TEXT
            );
        """)
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)",
            (root.name, "COMPLETED", "COMPLETE"),
        )
        for i in range(7):
            # Seven sequential 10-second canonical M18 attempts.
            con.execute(
                "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)",
                (f"AI-{i}", root.name, "IMPROVEMENT_INTELLIGENCE",
                 f"2026-10-09T10:{i:02d}:00+00:00",
                 f"2026-10-09T10:{i:02d}:10+00:00",
                 10000, .01, "USD"),
            )
        con.execute(
            "INSERT INTO content_remediation_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("M20-1", root.name, "CONTENT_REMEDIATION",
             "2026-10-09T10:07:00+00:00",
             "2026-10-09T10:07:20+00:00",
             20000, .04, "USD"),
        )
        con.execute(
            "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?,?,?,?)",
            ("FOREIGN", "AUD-FOREIGN", "IMPROVEMENT_INTELLIGENCE",
             "2026-10-09T10:09:00+00:00",
             "2026-10-09T10:19:00+00:00", 600000, 9000, "USD"),
        )
    return root


def test_eight_attempts_across_both_ledgers_are_counted_once(tmp_path):
    root = _fixture(tmp_path)
    before = (root / "audit.db").read_bytes()
    out = inspect_audit_attempts(root)
    assert out["attempts_total"] == out["stage_attempts_total"] == 8
    assert out["summed_ai_attempts_ms"] == 90000
    assert out["union_active_ai_ms"] == 90000
    assert out["unknown_ai_intervals"] == 0
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert out["non_ai_stages_measured"] is False
    assert out["verified_aud_wall_duration_ms"] is None
    assert out["observed_http_request_sums_ms"] == {}
    assert out["http_request_telemetry"] == "NOT_VERIFIABLE"
    assert out["http_request_stage_wall_clock_available"] is False
    assert out["provider_observed_usd"] == .04
    assert abs(out["posthoc_estimated_usd"] - .07) < 0.000001
    assert {x["name"]: x["attempts"] for x in out["stages"]} == {
        "CONTENT_REMEDIATION": 1, "IMPROVEMENT_INTELLIGENCE": 7,
    }
    assert "não equivale à fatura" in out["caveat"]
    assert (root / "audit.db").read_bytes() == before


def test_audit_attempts_cli_never_installs_provider_runtime(tmp_path, capsys, monkeypatch):
    from rasai import entrypoint
    root = _fixture(tmp_path)
    monkeypatch.setattr(
        entrypoint, "_install_audit_runtime",
        lambda: pytest.fail("read-only CLI cannot bootstrap audit"),
    )
    assert entrypoint.main(["audit-attempts", str(root)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["attempts_total"] == 8
    assert result["provider_requests"] == 0
    assert main([str(root)]) == 0


def test_cli_missing_audit_uses_actionable_error_not_traceback(
    tmp_path, capsys,
):
    from rasai import entrypoint

    missing = tmp_path / "audits" / "AUD-NOT-PRESENT"
    for dispatch in (
        lambda: main([str(missing)]),
        lambda: entrypoint.main(["audit-attempts", str(missing)]),
    ):
        with pytest.raises(SystemExit) as caught:
            dispatch()
        assert caught.value.code == 2
        printed = capsys.readouterr()
        assert printed.out == ""
        assert "AUD audit.db missing" in printed.err
        assert "diretório audits" in printed.err
        assert "Traceback" not in printed.err
    assert not missing.exists()


def test_cli_rejects_invalid_aud_identity_without_traceback(tmp_path, capsys):
    invalid = tmp_path / "CAMINHO" / "PARA" / "NOMEDIRETORIO"
    with pytest.raises(SystemExit) as caught:
        main([str(invalid)])
    assert caught.value.code == 2
    printed = capsys.readouterr()
    assert "AUD não verificável" in printed.err
    assert "Traceback" not in printed.err
    assert not invalid.exists()


def test_unverified_or_missing_aud_fails_without_files(tmp_path):
    root = _fixture(tmp_path)
    with pytest.raises(ValueError, match="audit.db missing"):
        inspect_audit_attempts(tmp_path / "AUD-NO-DB")
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE audits SET audit_id='AUD-FOREIGN'")
    before = (root / "audit.db").read_bytes()
    with pytest.raises(ValueError, match="identity"):
        inspect_audit_attempts(root)
    assert (root / "audit.db").read_bytes() == before
    assert not (tmp_path / "AUD-NO-DB").exists()


def test_partial_aud_still_explicitly_identified_as_not_complete(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute("UPDATE audits SET completion_status='PARTIAL_RETRYABLE'")
    result = inspect_audit_attempts(root)
    assert result["source_completion_status"] == "PARTIAL_RETRYABLE"
    assert result["attempts_total"] == 8


def test_m21_http_request_sums_are_scoped_but_not_fake_stage_wall_clock(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript("""
            CREATE TABLE web_performance_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                service TEXT, duration_ms REAL
            );
        """)
        con.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
            [
                ("HTTP-1", root.name, "PAGESPEED_INSIGHTS", 20000.0),
                ("HTTP-2", root.name, "PAGESPEED_INSIGHTS", 40000.0),
                ("HTTP-3", root.name, "CRUX_API", 10000.0),
                ("FOREIGN", "AUD-FOREIGN", "PAGESPEED_INSIGHTS", 999000.0),
                ("OTHER", root.name, "UNKNOWN_SERVICE", 888000.0),
            ],
        )
    before = (root / "audit.db").read_bytes()
    out = inspect_audit_attempts(root)
    assert out["attempts_total"] == out["stage_attempts_total"] == 8
    assert out["summed_ai_attempts_ms"] == out["union_active_ai_ms"] == 90000
    assert out["observed_http_request_sums_ms"] == {
        "PAGESPEED_INSIGHTS": 60000.0, "CRUX_API": 10000.0,
    }
    assert out["http_request_telemetry"] == "OBSERVED_CUMULATIVE_REQUEST_DURATION"
    assert out["non_ai_stages_measured"] is False
    assert out["http_request_stage_wall_clock_available"] is False
    assert "não tempo físico de fase" in out["http_request_caveat"]
    assert out["provider_requests"] == out["audit_writes"] == 0
    assert (root / "audit.db").read_bytes() == before


def test_m21_incomplete_or_invalid_service_abstains_without_inventing_zero(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.executescript("""
            CREATE TABLE web_performance_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                service TEXT, duration_ms REAL
            );
        """)
        con.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
            [
                ("HTTP-1", root.name, "PAGESPEED_INSIGHTS", 20000.0),
                ("HTTP-2", root.name, "PAGESPEED_INSIGHTS", None),
                ("HTTP-3", root.name, "CRUX_API", 10000.0),
                ("HTTP-4", "AUD-FOREIGN", "CRUX_API", float("inf")),
            ],
        )
    before = (root / "audit.db").read_bytes()
    out = inspect_audit_attempts(root)
    assert out["observed_http_request_sums_ms"] == {"CRUX_API": 10000.0}
    assert "PAGESPEED_INSIGHTS" not in out["observed_http_request_sums_ms"]
    assert out["unknown_ai_intervals"] == 0
    assert out["non_ai_stages_measured"] is False
    assert (root / "audit.db").read_bytes() == before


def test_audit_total_wall_time_requires_single_complete_physically_consistent_session(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "CREATE TABLE console_execution_projections("
            "audit_id TEXT, duration_ms REAL, started_at TEXT, finished_at TEXT)"
        )
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?)",
            (root.name, 812000.0, "2026-10-09T10:00:00-03:00",
             "2026-10-09T10:13:32-03:00"),
        )
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?)",
            ("AUD-FOREIGN", 999000.0, "2026-10-09T11:00:00+00:00",
             "2026-10-09T11:16:39+00:00"),
        )
    before = (root / "audit.db").read_bytes()
    report = inspect_audit_attempts(root)
    assert report["verified_aud_wall_duration_ms"] == 812000.0
    assert report["aud_wall_clock_scope"] == "SINGLE_VERIFIED_COMPLETE_CONSOLE_SESSION"
    assert report["summed_ai_attempts_ms"] == 90000
    assert "não pode" in report["aud_wall_clock_caveat"]
    assert report["non_ai_stages_measured"] is False
    assert (root / "audit.db").read_bytes() == before
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?)",
            (root.name, 5000.0, "2026-10-09T11:00:00+00:00",
             "2026-10-09T11:00:05+00:00"),
        )
    after = inspect_audit_attempts(root)
    assert after["verified_aud_wall_duration_ms"] is None
    assert after["aud_wall_clock_scope"] == "NOT_VERIFIABLE"


@pytest.mark.parametrize("variant", ["partial", "naive", "mismatch", "negative", "nonfinite"])
def test_audit_wall_time_abstains_when_physical_or_logical_provenance_invalid(
    tmp_path, variant,
):
    root = _fixture(tmp_path)
    start, end, elapsed = (
        "2026-10-09T10:00:00+00:00", "2026-10-09T10:01:00+00:00", 60000.0,
    )
    if variant == "naive":
        start = "2026-10-09T10:00:00"
    elif variant == "mismatch":
        elapsed = 10000.0
    elif variant == "negative":
        elapsed = -10.0
    elif variant == "nonfinite":
        elapsed = float("inf")
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "CREATE TABLE console_execution_projections("
            "audit_id TEXT, duration_ms REAL, started_at TEXT, finished_at TEXT)"
        )
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?)",
            (root.name, elapsed, start, end),
        )
        if variant == "partial":
            con.execute(
                "UPDATE audits SET completion_status='PARTIAL_RETRYABLE'"
            )
    before = (root / "audit.db").read_bytes()
    outcome = inspect_audit_attempts(root)
    assert outcome["verified_aud_wall_duration_ms"] is None
    assert outcome["aud_wall_clock_scope"] == "NOT_VERIFIABLE"
    assert outcome["non_ai_stages_measured"] is False
    assert (root / "audit.db").read_bytes() == before


def test_ai_scope_cohorts_distinguish_5_in_session_and_3_after_without_losing_m20(
    tmp_path,
):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "CREATE TABLE console_execution_projections("
            "audit_id TEXT, duration_ms REAL, started_at TEXT, finished_at TEXT)"
        )
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?)",
            (root.name, 300000.0, "2026-10-09T10:00:00+00:00",
             "2026-10-09T10:05:00+00:00"),
        )
    before = (root / "audit.db").read_bytes()
    result = inspect_audit_attempts(root)
    cohorts = result["ai_attempt_execution_scope"]
    assert cohorts["status"] == "VERIFIED_PHYSICAL_WINDOW_COHORTS"
    inner = cohorts["cohorts"]["WITHIN_VERIFIED_CONSOLE_SESSION"]
    after = cohorts["cohorts"]["AFTER_VERIFIED_CONSOLE_SESSION"]
    uncertain = cohorts["cohorts"]["UNCERTAIN_TIME_OR_SCOPE"]
    before_session = cohorts["cohorts"]["BEFORE_VERIFIED_CONSOLE_SESSION"]
    assert inner["attempts"] == 5
    assert after["attempts"] == 3
    assert uncertain["attempts"] == before_session["attempts"] == 0
    assert inner["summed_ai_attempts_ms"] == 50000
    assert after["summed_ai_attempts_ms"] == 40000
    assert abs(inner["posthoc_estimated_usd"] - .05) < 1e-8
    assert abs(after["posthoc_estimated_usd"] - .02) < 1e-8
    assert abs(after["provider_observed_usd"] - .04) < 1e-8
    assert result["attempts_total"] == 8
    assert result["verified_aud_wall_duration_ms"] == 300000
    assert result["non_ai_stages_measured"] is False
    assert result["provider_requests"] == result["audit_writes"] == 0
    assert (root / "audit.db").read_bytes() == before


def test_ai_scope_unverifiable_session_never_assigns_post_aud_cost(tmp_path):
    root = _fixture(tmp_path)
    original = (root / "audit.db").read_bytes()
    out = inspect_audit_attempts(root)
    scope = out["ai_attempt_execution_scope"]
    assert scope["status"] == "AUD_WINDOW_UNVERIFIABLE"
    assert scope["cohorts"]["UNCERTAIN_TIME_OR_SCOPE"]["attempts"] == 8
    assert scope["cohorts"]["WITHIN_VERIFIED_CONSOLE_SESSION"]["attempts"] == 0
    assert scope["cohorts"]["AFTER_VERIFIED_CONSOLE_SESSION"]["attempts"] == 0
    assert (root / "audit.db").read_bytes() == original


def test_ai_scope_rejects_naive_and_cross_boundary_attempts(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "CREATE TABLE console_execution_projections("
            "audit_id TEXT, duration_ms REAL, started_at TEXT, finished_at TEXT)"
        )
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?)",
            (root.name, 300000, "2026-10-09T10:00:00+00:00",
             "2026-10-09T10:05:00+00:00"),
        )
        con.execute(
            "UPDATE ai_provider_attempts SET started_at=? WHERE attempt_id='AI-0'",
            ("2026-10-09T10:00:00",),  # naive clock cannot be classified
        )
        con.execute(
            "UPDATE ai_provider_attempts SET started_at=?,finished_at=? "
            "WHERE attempt_id='AI-1'",
            ("2026-10-09T10:04:55+00:00", "2026-10-09T10:05:05+00:00"),
        )
    original = (root / "audit.db").read_bytes()
    report = inspect_audit_attempts(root)
    scope = report["ai_attempt_execution_scope"]["cohorts"]
    assert scope["UNCERTAIN_TIME_OR_SCOPE"]["attempts"] == 2
    assert scope["WITHIN_VERIFIED_CONSOLE_SESSION"]["attempts"] == 3
    assert scope["AFTER_VERIFIED_CONSOLE_SESSION"]["attempts"] == 3
    assert scope["UNCERTAIN_TIME_OR_SCOPE"]["union_active_ai_ms"] is None
    assert "fatura" in report["ai_attempt_execution_scope"]["limitation"]
    assert report["attempts_total"] == 8
    assert (root / "audit.db").read_bytes() == original


def test_m21_duplicate_attempt_identity_abstains_per_affected_service(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        # Synthetic physical table with deliberately absent uniqueness constraint.
        con.execute(
            "CREATE TABLE web_performance_attempts("
            "attempt_id TEXT, audit_id TEXT, service TEXT, duration_ms REAL)"
        )
        con.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
            [
                ("PSI-DUP", root.name, "PAGESPEED_INSIGHTS", 20000.0),
                ("PSI-DUP", root.name, "PAGESPEED_INSIGHTS", 30000.0),
                ("CRUX-OK", root.name, "CRUX_API", 11000.0),
                ("FOREIGN", "AUD-FOREIGN", "CRUX_API", 900000.0),
            ],
        )
    before = (root / "audit.db").read_bytes()
    result = inspect_audit_attempts(root)
    assert result["observed_http_request_sums_ms"] == {"CRUX_API": 11000.0}
    assert result["http_request_stage_wall_clock_available"] is False
    assert (root / "audit.db").read_bytes() == before


def test_m21_cross_service_id_collision_refuses_both_totals(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "CREATE TABLE web_performance_attempts("
            "attempt_id TEXT, audit_id TEXT, service TEXT, duration_ms REAL)"
        )
        con.executemany(
            "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
            [
                ("COLLISION", root.name, "PAGESPEED_INSIGHTS", 20000.0),
                ("COLLISION", root.name, "CRUX_API", 10000.0),
            ],
        )
    original = (root / "audit.db").read_bytes()
    result = inspect_audit_attempts(root)
    assert result["observed_http_request_sums_ms"] == {}
    assert result["http_request_telemetry"] == "NOT_VERIFIABLE"
    assert (root / "audit.db").read_bytes() == original


def test_m21_legacy_missing_attempt_key_is_nd_not_fake_sum(tmp_path):
    root = _fixture(tmp_path)
    with sqlite3.connect(root / "audit.db") as con:
        con.execute(
            "CREATE TABLE web_performance_attempts("
            "audit_id TEXT, service TEXT, duration_ms REAL)"
        )
        con.execute(
            "INSERT INTO web_performance_attempts VALUES (?,?,?)",
            (root.name, "PAGESPEED_INSIGHTS", 12345.0),
        )
    before = (root / "audit.db").read_bytes()
    result = inspect_audit_attempts(root)
    assert result["observed_http_request_sums_ms"] == {}
    assert result["http_request_telemetry"] == "NOT_VERIFIABLE"
    assert (root / "audit.db").read_bytes() == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_audit_attempts_rejects_live_sqlite_sidecars_without_open_or_mutation(
    tmp_path, suffix,
):
    root = _fixture(tmp_path)
    db = root / "audit.db"
    sidecar = root / ("audit.db" + suffix)
    sidecar.write_bytes(b"unverified-live-transaction")
    before = db.read_bytes()
    with pytest.raises(ValueError, match="unverified WAL/SHM/journal"):
        inspect_audit_attempts(root)
    assert db.read_bytes() == before
    assert sidecar.read_bytes() == b"unverified-live-transaction"


def test_audit_attempts_detects_new_sidecar_during_secondary_timeline_read(
    tmp_path, monkeypatch,
):
    from rasai import audit_attempt_inspection_319 as module
    root = _fixture(tmp_path)
    db = root / "audit.db"
    original = db.read_bytes()
    real_timeline = module.read_audit_attempt_timeline
    sidecar = root / "audit.db-wal"

    def concurrent_uncheckpointed_writer(path, audit_id, *, sealed_source=False):
        assert sealed_source is True
        timeline = real_timeline(path, audit_id, sealed_source=sealed_source)
        sidecar.write_bytes(b"arrived-during-timeline")
        return timeline

    monkeypatch.setattr(
        module, "read_audit_attempt_timeline", concurrent_uncheckpointed_writer
    )
    with pytest.raises(ValueError, match="unverified WAL/SHM/journal"):
        module.inspect_audit_attempts(root)
    assert sidecar.read_bytes() == b"arrived-during-timeline"
    assert db.read_bytes() == original
    sidecar.unlink()


def test_inspector_refuses_duplicate_physical_ai_attempt_ids_instead_of_cost_loss(
    tmp_path,
):
    root = _fixture(tmp_path)
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        # Rebuild a synthetic legacy table without a PK, to simulate an
        # anomalous physical ledger with duplicate billable attempt IDs.
        con.execute(
            "CREATE TABLE legacy_ai AS SELECT * FROM ai_provider_attempts"
        )
        con.execute("DROP TABLE ai_provider_attempts")
        con.execute("ALTER TABLE legacy_ai RENAME TO ai_provider_attempts")
        con.execute(
            "INSERT INTO ai_provider_attempts "
            "SELECT * FROM ai_provider_attempts WHERE attempt_id='AI-0' LIMIT 1"
        )
    before = db.read_bytes()
    with pytest.raises(ValueError, match="ambiguous AI attempt_id"):
        inspect_audit_attempts(root)
    assert db.read_bytes() == before


def test_inspector_refuses_duplicate_remediation_attempt_ids(
    tmp_path,
):
    root = _fixture(tmp_path)
    db = root / "audit.db"
    with sqlite3.connect(db) as con:
        con.execute(
            "CREATE TABLE legacy_m20 AS SELECT * FROM content_remediation_attempts"
        )
        con.execute("DROP TABLE content_remediation_attempts")
        con.execute("ALTER TABLE legacy_m20 RENAME TO content_remediation_attempts")
        con.execute(
            "INSERT INTO content_remediation_attempts "
            "SELECT * FROM content_remediation_attempts LIMIT 1"
        )
    before = db.read_bytes()
    with pytest.raises(ValueError, match="ambiguous AI attempt_id"):
        inspect_audit_attempts(root)
    assert db.read_bytes() == before


def test_inspector_detects_physical_db_change_without_wal_during_second_read(
    tmp_path, monkeypatch,
):
    from rasai import audit_attempt_inspection_319 as module
    root = _fixture(tmp_path)
    db = root / "audit.db"
    original = db.read_bytes()
    real_timeline = module.read_audit_attempt_timeline

    def mutate_after_timeline(path, audit_id, *, sealed_source=False):
        result = real_timeline(path, audit_id, sealed_source=sealed_source)
        # A file replacement or out-of-band append need not create WAL/SHM.
        with db.open("ab") as stream:
            stream.write(b"changed-after-read")
        return result

    monkeypatch.setattr(
        module, "read_audit_attempt_timeline", mutate_after_timeline
    )
    with pytest.raises(ValueError, match="changed during physical inspection"):
        module.inspect_audit_attempts(root)
    assert db.read_bytes() == original + b"changed-after-read"
    assert not any(
        (root / ("audit.db" + ext)).exists()
        for ext in ("-wal", "-shm", "-journal")
    )


def test_inspector_rejects_oversized_source_without_opening_sqlite(
    tmp_path, monkeypatch,
):
    from rasai import audit_attempt_inspection_319 as module
    root = _fixture(tmp_path)
    db = root / "audit.db"
    previous = module._MAX_SOURCE_BYTES
    monkeypatch.setattr(module, "_MAX_SOURCE_BYTES", db.stat().st_size - 1)
    original = db.read_bytes()
    with pytest.raises(ValueError, match="exceeds bounded verification limit"):
        module.inspect_audit_attempts(root)
    assert db.read_bytes() == original
    assert previous > db.stat().st_size
