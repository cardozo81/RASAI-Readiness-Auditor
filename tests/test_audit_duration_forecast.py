"""#319 conservative ex-ante physical duration preview; no collector/provider use."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from rasai.audit_duration_forecast import (
    _historical_audit,
    forecast_local_duration,
    format_duration_preview,
)
from rasai.console_cost_confirmation import _render_forecast
from rasai.cost_forecast import CostForecast

from rasai.console_apdex_duration_scope import (
    NAVIGATION_FIELDS, EXPERIENCE_FIELDS, apdex_duration_scope,
)
from rasai.console_m23 import State as ApdexConsoleState


def _configured_apdex_fields(state):
    reference = ApdexConsoleState()
    for field in (*NAVIGATION_FIELDS, *EXPERIENCE_FIELDS):
        setattr(state, field, getattr(reference, field))
    return state



def _state(root: Path):
    return SimpleNamespace(
        audits_root=str(root), input_mode="URL", device="MOBILE", ai_provider="auto",
        ai_model="", content_remediation=False, web_performance=True,
        field_source="NONE", max_pages=1, web_max_pages=1,
        improvement_enabled=False,
        search_ai_competitive=False,
    )


def _audit(root: Path, index: int, *, status="COMPLETE", duration=600_000,
           completion_status="COMPLETE",
           with_stage=True, device="MOBILE", complete_config=True,
           wrong_clock=False, pages=1, web_max_pages=1,
           input_mode="URL", with_http=False, invalid_http=False,
           start_offset_minutes=0) -> Path:
    audit_id = f"AUD-DURATION-{index}"
    folder = root / audit_id
    folder.mkdir(parents=True)
    database = folder / "audit.db"
    started = (
        datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
        + timedelta(minutes=start_offset_minutes)
    )
    finished = started + timedelta(milliseconds=duration * (2 if wrong_clock else 1))
    config = {
        "input_mode": input_mode, "device": device,
        "ai_provider": "auto", "ai_model": "",
        "content_remediation": False, "web_performance": True,
        "field_source": "NONE", "max_pages": 1,
        "web_max_pages": web_max_pages,
    }
    if not complete_config:
        config.pop("field_source")
    with sqlite3.connect(database) as con:
        con.executescript(
            """
            CREATE TABLE audits (audit_id TEXT PRIMARY KEY, status TEXT, completion_status TEXT);
            CREATE TABLE pages (page_id TEXT PRIMARY KEY, audit_id TEXT);
            CREATE TABLE console_execution_projections (
                audit_id TEXT, configuration TEXT, duration_ms INTEGER,
                started_at TEXT, finished_at TEXT
            );
            CREATE TABLE ai_provider_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                operation TEXT, started_at TEXT, finished_at TEXT
            );
            CREATE TABLE web_performance_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                service TEXT, duration_ms INTEGER
            );
            """
        )
        con.execute(
            "INSERT INTO audits VALUES (?,?,?)",
            (audit_id, "COMPLETED" if status == "COMPLETE" else status, completion_status),
        )
        for page_no in range(pages):
            con.execute("INSERT INTO pages VALUES (?,?)", (f"PAGE-{page_no}", audit_id))
        con.execute(
            "INSERT INTO console_execution_projections VALUES (?,?,?,?,?)",
            (audit_id, json.dumps(config), duration,
             started.isoformat(), finished.isoformat()),
        )
        if with_stage:
            for n, low, high in ((1, 10, 30), (2, 20, 40)):
                con.execute(
                    "INSERT INTO ai_provider_attempts VALUES (?,?,?,?,?)",
                    (f"AIP-{n}", audit_id, "SEMANTIC_ANALYSIS",
                     (started + timedelta(seconds=low)).isoformat(),
                     (started + timedelta(seconds=high)).isoformat()),
                )
        if with_http:
            for aid, service, elapsed in (
                ("HTTP-1", "PAGESPEED_INSIGHTS", 30_000),
                ("HTTP-2", "PAGESPEED_INSIGHTS", 30_000),
                ("HTTP-3", "CRUX_API", 10_000),
            ):
                con.execute(
                    "INSERT INTO web_performance_attempts VALUES (?,?,?,?)",
                    (aid, audit_id, service, None if invalid_http and aid == "HTTP-2" else elapsed),
                )
    return database


def test_5_comparable_completed_runs_produce_total_and_union_ai_stage(tmp_path):
    state = _state(tmp_path)
    databases = [_audit(tmp_path, i, duration=600_000 + 1000 * i) for i in range(5)]
    digests = {str(p): sha256(p.read_bytes()).hexdigest() for p in databases}
    result = forecast_local_duration(state, target_pages=1)

    assert result.available
    assert result.sample_runs == 5
    assert result.total is not None
    assert result.total.median_ms == 602_000
    assert result.total.p25_ms == 601_000
    assert result.total.p75_ms == 603_000
    assert result.total.p90_ms >= result.total.p75_ms
    assert len(result.ai_stages) == 1
    assert result.ai_stages[0].label == "SEMANTIC_ANALYSIS"
    assert result.ai_stages[0].median_ms == 30_000  # 20s + 20s overlap by 10s
    assert all(sha256(p.read_bytes()).hexdigest() == digests[str(p)] for p in databases)
    visible = "\n".join(format_duration_preview(result))
    assert "Duracao total histor." in visible
    assert "tempo ativo" in visible
    assert "NAO devem ser somados" in visible
    assert "P90" in visible


@pytest.mark.parametrize("link_kind", ("audit_directory", "audit_db"))
def test_foreign_symlinked_audit_never_enters_duration_history(tmp_path, link_kind):
    root = tmp_path / "audits"
    root.mkdir()
    outside = tmp_path / "foreign"
    outside.mkdir()
    legitimate = [_audit(root, i) for i in range(4)]
    source = _audit(outside, 4)
    candidate = root / "AUD-DURATION-4"
    try:
        if link_kind == "audit_directory":
            candidate.symlink_to(source.parent, target_is_directory=True)
        else:
            candidate.mkdir()
            (candidate / "audit.db").symlink_to(source)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not permitted on this platform: {exc}")
    original = [sha256(db.read_bytes()).hexdigest()
                for db in (*legitimate, source)]
    result = forecast_local_duration(_state(root))
    assert _historical_audit(candidate / "audit.db", _state(root), 1) is None
    assert not result.available
    assert result.sample_runs == 4
    assert result.ai_stages == ()
    assert [sha256(db.read_bytes()).hexdigest()
            for db in (*legitimate, source)] == original


def test_retrospective_p90_loo_diagnostic_uses_only_verified_wall_times(tmp_path):
    dbs = [_audit(tmp_path, i, duration=600_000 + i * 1000) for i in range(8)]
    originals = [sha256(p.read_bytes()).hexdigest() for p in dbs]
    projection = forecast_local_duration(_state(tmp_path), target_pages=1)
    backtest = projection.total_p90_backtest
    assert projection.available and backtest is not None
    assert backtest.method == "LEAVE_ONE_OUT_RETROSPECTIVE_ONLY"
    assert backtest.evaluated_runs == 8
    # Excluding either of the two highest samples lowers the P90 cut enough
    # for those samples to miss; six earlier samples remain within bounds.
    assert backtest.within_held_out_p90 == 6
    assert backtest.observed_fraction == .75
    # All fixture runs share the same start. No completed prior cohort was
    # physically available when any other audit began.
    assert projection.forward_p90_backtest is None
    lines = "\n".join(format_duration_preview(projection))
    assert "Backtest retrospectivo LOO" in lines
    assert "6/8" in lines
    assert "nao e calibracao prospectiva ou SLA" in lines
    assert [sha256(p.read_bytes()).hexdigest() for p in dbs] == originals


def test_five_samples_cannot_be_mislabeled_as_calibrated_p90(tmp_path):
    for i in range(5):
        _audit(tmp_path, i)
    projection = forecast_local_duration(_state(tmp_path))
    assert projection.available and projection.sample_runs == 5
    assert projection.total_p90_backtest is None
    assert projection.forward_p90_backtest is None
    assert "Backtest retrospectivo" not in "\n".join(
        format_duration_preview(projection)
    )


def test_backtest_only_counts_eligible_complete_auds(tmp_path):
    for i in range(7):
        _audit(tmp_path, i, duration=600_000 + i * 1000)
    _audit(tmp_path, 7, completion_status="PARTIAL_RETRYABLE")
    report = forecast_local_duration(_state(tmp_path))
    assert report.sample_runs == 7
    assert report.total_p90_backtest is None


def test_abstains_for_insufficient_history_instead_of_extrapolating(tmp_path):
    _audit(tmp_path, 1)
    _audit(tmp_path, 2)
    forecast = forecast_local_duration(_state(tmp_path))
    assert forecast.available is False
    assert forecast.sample_runs == 2
    assert forecast.total is None and not forecast.ai_stages
    assert "N/D" in format_duration_preview(forecast)[0]


def test_rejects_incomplete_invalid_clock_schema_and_mismatched_config(tmp_path):
    _audit(tmp_path, 1, status="PARTIAL_RETRYABLE")
    _audit(tmp_path, 2, wrong_clock=True)
    _audit(tmp_path, 3, complete_config=False)
    _audit(tmp_path, 4, device="DESKTOP")
    _audit(tmp_path, 5, duration=-100)
    _audit(tmp_path, 6, pages=2)
    _audit(tmp_path, 7, web_max_pages=10)
    _audit(tmp_path, 8, input_mode="FILE")
    projection = forecast_local_duration(_state(tmp_path))
    assert projection.sample_runs == 0
    assert not projection.available


def test_omits_ai_stage_if_any_member_has_no_matching_record(tmp_path):
    for i in range(5):
        _audit(tmp_path, i, with_stage=(i != 4))
    result = forecast_local_duration(_state(tmp_path))
    assert result.available
    assert result.sample_runs == 5
    assert result.ai_stages == ()
    assert "nao possuem duracao fisica" in "\n".join(result.notes)


def test_cannot_predict_optional_unrecorded_scope(tmp_path):
    for i in range(5):
        _audit(tmp_path, i)
    state = _state(tmp_path)
    state.improvement_enabled = True
    assert not forecast_local_duration(state).available
    state.improvement_enabled = False
    state.search_ai_competitive = True
    assert not forecast_local_duration(state).available
    state.search_ai_competitive = False
    state.technical_remediation = True
    assert not forecast_local_duration(state).available


def test_historical_optional_scope_must_match_explicit_current_scope(tmp_path):
    databases = [_audit(tmp_path, i) for i in range(5)]
    baselines = [sha256(db.read_bytes()).hexdigest() for db in databases]
    for db in databases:
        with sqlite3.connect(db) as connection:
            row = connection.execute(
                "SELECT configuration FROM console_execution_projections"
            ).fetchone()
            payload = json.loads(row[0])
            payload["technical_remediation"] = True
            payload["improvement_enabled"] = False
            payload["search_ai_competitive"] = False
            connection.execute(
                "UPDATE console_execution_projections SET configuration=?",
                (json.dumps(payload),),
            )
    prepared = [sha256(db.read_bytes()).hexdigest() for db in databases]
    assert prepared != baselines  # Only the explicit fixture edit changed them.
    state = _state(tmp_path)
    assert not forecast_local_duration(state).available  # Historic scope is larger.
    state.technical_remediation = True
    confirmed = forecast_local_duration(state)
    assert confirmed.available and confirmed.sample_runs == 5
    # Both forecasts are read-only and cannot mutate the audited ledger.
    assert [sha256(db.read_bytes()).hexdigest() for db in databases] == prepared


def test_malformed_optional_scope_flags_are_not_promoted_to_comparable(tmp_path):
    databases = [_audit(tmp_path, i) for i in range(5)]
    for db in databases:
        with sqlite3.connect(db) as connection:
            row = connection.execute(
                "SELECT configuration FROM console_execution_projections"
            ).fetchone()
            payload = json.loads(row[0])
            payload["technical_remediation"] = "false"
            connection.execute(
                "UPDATE console_execution_projections SET configuration=?",
                (json.dumps(payload),),
            )
    assert not forecast_local_duration(_state(tmp_path)).available


def test_m21_http_request_totals_are_separate_from_audit_wall_clock(tmp_path):
    for i in range(5):
        _audit(tmp_path, i, with_http=True)
    forecast = forecast_local_duration(_state(tmp_path))
    assert forecast.available
    by_service = {x.label: x for x in forecast.http_request_stages}
    assert by_service["PAGESPEED_INSIGHTS"].median_ms == 60_000
    assert by_service["CRUX_API"].median_ms == 10_000
    assert forecast.total.median_ms == 600_000
    content = "\n".join(format_duration_preview(forecast))
    assert "HTTP PAGESPEED_INSIGHTS" in content
    assert "nao wall-clock" in content
    assert "NAO sao wall-clock" in content
    assert "requests HTTP medidos acima" in content
    assert "duracao wall-clock da fase = N/D" in content
    assert "Captura, Apdex, analise competitiva" in content


def test_m21_http_request_census_abstains_when_population_exceeds_limit(tmp_path):
    from rasai.audit_duration_forecast import _m21_http_request_sums

    database = tmp_path / "attempts.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE web_performance_attempts "
            "(attempt_id TEXT, audit_id TEXT, service TEXT, duration_ms REAL)"
        )
        connection.executemany(
            "INSERT INTO web_performance_attempts VALUES (?, ?, ?, ?)",
            ((f"REQ-{i}", "AUD-1", "PAGESPEED_INSIGHTS", 10)
             for i in range(10001))
        )
        assert _m21_http_request_sums(connection, "AUD-1") == {}


def test_m21_http_request_abstains_from_missing_or_invalid_cohort_timings(tmp_path):
    for i in range(5):
        _audit(tmp_path, i, with_http=i != 4, invalid_http=i == 2)
    forecast = forecast_local_duration(_state(tmp_path))
    assert forecast.available
    assert forecast.http_request_stages == ()
    assert forecast.total is not None


def test_console_monetary_preview_stays_intact_with_separate_duration_layer(tmp_path):
    for i in range(5):
        _audit(tmp_path, i)
    forecast = CostForecast(
        available=True, show_confirmation=True, currency="USD",
        success_baseline=.01, expected=.02, likely_low=.01, likely_high=.03,
        potential=.04, sample_runs=5, sample_calls=20, target_pages=1,
        confidence="MODERADA", source="test",
    )
    out = StringIO()
    with redirect_stdout(out):
        _render_forecast(forecast, state=_state(tmp_path))
    rendered = out.getvalue()
    assert "Custo esperado" in rendered
    assert "PREVISÃO DE DURAÇÃO" in rendered
    assert "Duracao total histor." in rendered
    assert "Nenhuma chamada tarifável" not in rendered  # existing verbatim disclaimer remains
    assert "A execução ainda não iniciou" in rendered



def test_forecast_rejects_physical_aud_with_foreign_lifecycle_metadata(
    tmp_path,
):
    """#319: selecting a valid row must not hide a second foreign AUD identity."""
    state = _state(tmp_path)
    dbs = [_audit(tmp_path, i, duration=600_000 + 1000 * i) for i in range(5)]
    initial = forecast_local_duration(state, target_pages=1)
    assert initial.available and initial.sample_runs == 5

    corrupted = dbs[0]
    with sqlite3.connect(corrupted) as con:
        con.execute(
            "INSERT INTO audits(audit_id,status,completion_status) "
            "VALUES ('AUD-FOREIGN-IDENTITY','COMPLETED','COMPLETE')"
        )
    originals = {str(db): sha256(db.read_bytes()).hexdigest() for db in dbs}
    assert _historical_audit(corrupted, state, 1) is None

    projection = forecast_local_duration(state, target_pages=1)
    assert projection.available is False
    assert projection.sample_runs == 4
    assert projection.total is None
    assert projection.ai_stages == ()
    assert projection.total_p90_backtest is None
    assert projection.forward_p90_backtest is None
    assert "4/5" in " ".join(projection.notes)
    assert {str(db): sha256(db.read_bytes()).hexdigest() for db in dbs} == originals


@pytest.mark.parametrize(
    ("duplicate_key", "conflicting_value"),
    [
        ("device", "DESKTOP"),
        ("input_mode", "SITEMAP"),
        ("web_max_pages", 3),
        ("content_remediation", True),
    ],
)
def test_forecast_excludes_contradictory_duplicate_config_json_keys(
    tmp_path, duplicate_key, conflicting_value,
):
    """#319: last-key-wins cannot hide ambiguous historical workload scope."""
    state = _state(tmp_path)
    databases = [_audit(tmp_path, i) for i in range(5)]
    assert forecast_local_duration(state).sample_runs == 5

    db = databases[0]
    with sqlite3.connect(db) as con:
        raw = con.execute(
            "SELECT configuration FROM console_execution_projections"
        ).fetchone()[0]
        ambiguous = (
            "{" + json.dumps(duplicate_key) + ":"
            + json.dumps(conflicting_value) + "," + raw[1:]
        )
        # The permissive decoder would silently select the original,
        # matching setting from the latter duplicate key.
        assert json.loads(ambiguous) == json.loads(raw)
        con.execute(
            "UPDATE console_execution_projections SET configuration=?",
            (ambiguous,),
        )

    hashes = {str(path): sha256(path.read_bytes()).hexdigest()
              for path in databases}
    assert _historical_audit(db, state, 1) is None
    result = forecast_local_duration(state)
    assert result.available is False
    assert result.sample_runs == 4
    assert result.total is None
    assert result.ai_stages == ()
    assert result.total_p90_backtest is None
    assert result.forward_p90_backtest is None
    assert "4/5" in " ".join(result.notes)
    assert {str(path): sha256(path.read_bytes()).hexdigest()
            for path in databases} == hashes


def test_completed_but_logically_partial_never_enters_forecast_cohort(tmp_path):
    # Lifecycle COMPLETED can coexist with a partial diagnostic outcome.
    # A status-only filter would falsely learn from this incomplete sample.
    for i in range(5):
        _audit(tmp_path, i, completion_status="PARTIAL_RETRYABLE")
    value = forecast_local_duration(_state(tmp_path))
    assert value.sample_runs == 0
    assert not value.available


def test_page_count_scoped_to_current_audit_not_foreign_records(tmp_path):
    for i in range(5):
        db = _audit(tmp_path, i)
        with sqlite3.connect(db) as con:
            con.execute(
                "INSERT INTO pages VALUES (?,?)",
                ("FOREIGN-" + str(i), "AUD-FOREIGN"),
            )
    value = forecast_local_duration(_state(tmp_path))
    assert value.sample_runs == 5
    assert value.available


def test_legacy_missing_completion_or_page_provenance_abstains(tmp_path):
    databases = [_audit(tmp_path, i) for i in range(5)]
    for path in databases:
        with sqlite3.connect(path) as con:
            con.executescript(
                "ALTER TABLE audits RENAME TO audits_old;"
                "CREATE TABLE audits(audit_id TEXT PRIMARY KEY, status TEXT);"
                "INSERT INTO audits SELECT audit_id,status FROM audits_old;"
                "DROP TABLE audits_old;"
            )
    value = forecast_local_duration(_state(tmp_path))
    assert not value.available
    assert value.sample_runs == 0



def test_stage_forecast_excludes_attempt_outside_console_wallclock(tmp_path):
    databases = [_audit(tmp_path, i) for i in range(5)]
    with sqlite3.connect(databases[2]) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET started_at=?, finished_at=? "
            "WHERE attempt_id='AIP-1'",
            ("2026-10-08T13:00:00+00:00", "2026-10-08T13:00:20+00:00"),
        )
    expected = [sha256(path.read_bytes()).hexdigest() for path in databases]
    preview = forecast_local_duration(_state(tmp_path))
    assert preview.available and preview.total is not None
    assert preview.sample_runs == 5
    assert preview.ai_stages == ()
    assert [sha256(path.read_bytes()).hexdigest() for path in databases] == expected


def test_stage_forecast_excludes_naive_and_reversed_attempt_clocks(tmp_path):
    databases = [_audit(tmp_path, i) for i in range(5)]
    with sqlite3.connect(databases[0]) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET started_at=? WHERE attempt_id='AIP-1'",
            ("2026-10-08T12:00:10",),
        )
    with sqlite3.connect(databases[1]) as con:
        con.execute(
            "UPDATE ai_provider_attempts SET started_at=?, finished_at=? "
            "WHERE attempt_id='AIP-2'",
            ("2026-10-08T12:00:35+00:00", "2026-10-08T12:00:30+00:00"),
        )
    value = forecast_local_duration(_state(tmp_path))
    assert value.available
    assert value.ai_stages == ()
    assert "relogios" in " ".join(value.notes)


def test_expanding_chronological_replay_uses_only_prior_finished_auds(tmp_path):
    databases = [
        _audit(
            tmp_path, i,
            duration=600_000 if i < 5 else 1_200_000,
            start_offset_minutes=30 * i,
        ) for i in range(8)
    ]
    baseline = {str(p): sha256(p.read_bytes()).hexdigest() for p in databases}
    result = forecast_local_duration(_state(tmp_path))
    replay = result.forward_p90_backtest
    assert result.available and replay is not None
    assert replay.method == "PAST_COMPLETED_AUDS_ONLY_EXPANDING_WINDOW"
    assert replay.min_prior_cohort == 5
    assert replay.evaluated_runs == 3
    # The 6th and 7th audits exceed P90 known before each run started;
    # the 8th falls on the prior 7-AUD P90 threshold.
    assert replay.within_prior_p90 == 1
    assert replay.observed_fraction == .3333
    assert result.total_p90_backtest is not None
    lines = "\n".join(format_duration_preview(result))
    assert "Replay cronologico P90 total" in lines
    assert "1/3" in lines
    assert "nao homologacao de SLA" in lines
    assert all(sha256(Path(path).read_bytes()).hexdigest() == digest
               for path, digest in baseline.items())


def test_chronological_replay_is_independent_of_filesystem_mtime(tmp_path):
    dbs = [
        _audit(tmp_path, i, duration=600_000,
               start_offset_minutes=25*i)
        for i in range(9)
    ]
    initial = forecast_local_duration(_state(tmp_path)).forward_p90_backtest
    assert initial is not None
    assert initial.evaluated_runs == 4
    assert initial.within_prior_p90 == 4
    for i, path in enumerate(dbs):
        # Explicitly scramble file mtimes opposite to AUD chronology.
        os.utime(path, ns=(1_650_000_000_000_000_000+i,
                           1_650_000_000_000_000_000+i))
    changed = forecast_local_duration(_state(tmp_path)).forward_p90_backtest
    assert changed == initial


def test_earlier_completion_is_required_not_just_earlier_start(tmp_path):
    for i in range(8):
        _audit(tmp_path, i, duration=600_000, start_offset_minutes=i)
    result = forecast_local_duration(_state(tmp_path))
    assert result.total_p90_backtest is not None
    # Runs overlap physically: none of them has five earlier
    # *finished* AUDs at its start, despite distinct start timestamps.
    assert result.forward_p90_backtest is None
    assert "Replay cronologico" not in "\n".join(format_duration_preview(result))


def test_one_corrupt_partial_aud_does_not_train_the_next_fold(tmp_path):
    for i in range(9):
        _audit(tmp_path, i, duration=600_000, start_offset_minutes=30*i)
    path = tmp_path / "AUD-DURATION-4" / "audit.db"
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE audits SET completion_status='PARTIAL_RETRYABLE'"
        )
    result = forecast_local_duration(_state(tmp_path))
    assert result.sample_runs == 8
    replay = result.forward_p90_backtest
    assert replay is not None and replay.evaluated_runs == 3
    assert replay.within_prior_p90 == 3


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_forecast_rejects_active_sqlite_sidecar_and_preserves_aud_bytes(
    tmp_path, suffix,
):
    sources = [_audit(tmp_path, i) for i in range(5)]
    before = {str(path): sha256(path.read_bytes()).hexdigest() for path in sources}
    original = forecast_local_duration(_state(tmp_path))
    assert original.sample_runs == 5 and original.available
    sidecar = Path(str(sources[-1]) + suffix)
    sidecar.write_bytes(b"unsealed physical transaction")
    try:
        uncertain = forecast_local_duration(_state(tmp_path))
        assert uncertain.sample_runs == 4
        assert uncertain.available is False
        assert uncertain.total is None
        assert uncertain.ai_stages == ()
        assert _historical_audit(sources[-1], _state(tmp_path), 1) is None
        assert sidecar.read_bytes() == b"unsealed physical transaction"
        assert {
            str(path): sha256(path.read_bytes()).hexdigest() for path in sources
        } == before
    finally:
        sidecar.unlink()
    recovered = forecast_local_duration(_state(tmp_path))
    assert recovered.sample_runs == 5
    assert recovered.available


def test_forecast_excludes_aud_if_journal_appears_during_projection(
    tmp_path, monkeypatch,
):
    from rasai import audit_duration_forecast as mod

    databases = [_audit(tmp_path, i) for i in range(5)]
    source = databases[4]
    original = source.read_bytes()
    reader = mod.read_audit_attempt_timeline

    def concurrent_journal(database, audit_id, *, sealed_source=False):
        assert sealed_source is True
        result = reader(database, audit_id, sealed_source=sealed_source)
        if Path(database) == source:
            Path(str(source) + "-wal").write_bytes(b"concurrent writer")
        return result

    monkeypatch.setattr(mod, "read_audit_attempt_timeline", concurrent_journal)
    projection = mod.forecast_local_duration(_state(tmp_path))
    assert projection.sample_runs == 4
    assert not projection.available
    assert source.read_bytes() == original


def test_forecast_excludes_aud_if_file_mtime_moves_during_projection(
    tmp_path, monkeypatch,
):
    from rasai import audit_duration_forecast as mod

    databases = [_audit(tmp_path, i) for i in range(5)]
    source = databases[4]
    original = source.read_bytes()
    reader = mod.read_audit_attempt_timeline

    def concurrent_metadata_change(database, audit_id, *, sealed_source=False):
        assert sealed_source is True
        result = reader(database, audit_id, sealed_source=sealed_source)
        if Path(database) == source:
            metadata = source.stat()
            os.utime(
                source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 10_000_000)
            )
        return result

    monkeypatch.setattr(mod, "read_audit_attempt_timeline", concurrent_metadata_change)
    projection = mod.forecast_local_duration(_state(tmp_path))
    assert projection.sample_runs == 4
    assert projection.total is None
    assert source.read_bytes() == original


def test_historical_duration_ai_reader_uses_sealed_snapshot_mode_only(
    tmp_path, monkeypatch,
):
    from rasai import audit_duration_forecast as mod

    paths = [_audit(tmp_path, i) for i in range(5)]
    before = {str(p): p.read_bytes() for p in paths}
    old = mod.read_audit_attempt_timeline
    seen = []

    def verified_historical_reader(db, audit_id, *, sealed_source=False):
        seen.append((Path(db), audit_id, sealed_source))
        assert sealed_source is True
        return old(db, audit_id, sealed_source=sealed_source)

    monkeypatch.setattr(
        mod, "read_audit_attempt_timeline", verified_historical_reader,
    )
    projection = forecast_local_duration(_state(tmp_path))
    assert projection.available and projection.sample_runs == 5
    assert len(seen) == 5
    assert set(p for p, _, sealed in seen if sealed) == set(paths)
    assert {str(p): p.read_bytes() for p in paths} == before
    assert all(
        not any(Path(str(p) + ext).exists()
                for ext in ("-wal", "-shm", "-journal"))
        for p in paths
    )


@pytest.mark.parametrize("non_json_token", ["NaN", "Infinity", "-Infinity"])
def test_duration_forecast_abstains_from_non_json_history_numbers(
    tmp_path, non_json_token,
):
    """Python's permissive NaN/Infinity extension cannot attest an AUD scope."""
    state = _state(tmp_path)
    databases = [_audit(tmp_path, i) for i in range(5)]
    assert forecast_local_duration(state).available
    corrupted = databases[0]
    with sqlite3.connect(corrupted) as con:
        raw = con.execute(
            "SELECT configuration FROM console_execution_projections"
        ).fetchone()[0]
        # The permissive decoder accepts even a nested foreign numeric
        # field, thereby admitting a physically non-JSON scope as training.
        bad = raw[:-1] + ',"auxiliary":{"telemetry":' + non_json_token + '}}'
        assert json.loads(bad)["auxiliary"]["telemetry"] is not None
        con.execute(
            "UPDATE console_execution_projections SET configuration=?",
            (bad,),
        )
    before = {str(p): sha256(p.read_bytes()).hexdigest() for p in databases}
    assert _historical_audit(corrupted, state, 1) is None
    result = forecast_local_duration(state)
    assert result.sample_runs == 4
    assert not result.available
    assert result.total is None
    assert result.ai_stages == ()
    assert result.http_request_stages == ()
    assert result.total_p90_backtest is None
    assert result.forward_p90_backtest is None
    assert "4/5" in " ".join(result.notes)
    assert {str(p): sha256(p.read_bytes()).hexdigest() for p in databases} == before


def test_duration_forecast_does_not_follow_symlinked_history_root(tmp_path):
    """Even an apparently complete history cannot be sourced via a linked root."""
    real_root = tmp_path / "physical"
    real_root.mkdir()
    databases = [_audit(real_root, i) for i in range(5)]
    assert forecast_local_duration(_state(real_root)).sample_runs == 5
    original = {str(db): sha256(db.read_bytes()).hexdigest() for db in databases}
    alias = tmp_path / "linked-audits"
    try:
        alias.symlink_to(real_root, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlink not permitted on this platform: {exc}")

    first = forecast_local_duration(_state(alias))
    assert first.sample_runs == 0
    assert first.total is None
    assert first.ai_stages == ()
    assert first.http_request_stages == ()
    assert first.total_p90_backtest is None
    assert first.forward_p90_backtest is None
    assert _historical_audit(alias / databases[0].parent.name / "audit.db",
                             _state(alias), 1) is None
    assert {str(db): sha256(db.read_bytes()).hexdigest() for db in databases} == original


@pytest.mark.parametrize("active_apdex", ("synthetic_apdex", "apdex_experience"))
def test_active_apdex_never_uses_legacy_history_with_unrecorded_workload(
    tmp_path, active_apdex,
):
    """Old physical console projections cannot prove Apdex cohort equality."""
    databases = [_audit(tmp_path, i) for i in range(5)]
    before = [sha256(db.read_bytes()).hexdigest() for db in databases]
    baseline = _state(tmp_path)
    assert forecast_local_duration(baseline).available
    setattr(baseline, active_apdex, True)
    projection = forecast_local_duration(baseline)
    assert not projection.available
    assert projection.sample_runs == 0
    assert projection.total is None
    assert "Apdex" in " ".join(projection.notes)
    assert [sha256(db.read_bytes()).hexdigest() for db in databases] == before


def test_explicit_historical_apdex_booleans_allow_only_matching_workloads(
    tmp_path,
):
    """Future opt-in physical flags can support a cohort; conflicting runs cannot."""
    databases = [_audit(tmp_path, i) for i in range(5)]
    state = _configured_apdex_fields(_state(tmp_path))
    state.synthetic_apdex = True
    state.apdex_experience = False
    for db in databases:
        with sqlite3.connect(db) as con:
            (text,) = con.execute(
                "SELECT configuration FROM console_execution_projections"
            ).fetchone()
            payload = json.loads(text)
            payload.update(apdex_duration_scope(state))
            con.execute(
                "UPDATE console_execution_projections SET configuration=?",
                (json.dumps(payload),),
            )
    expected = forecast_local_duration(state)
    assert expected.available and expected.sample_runs == 5

    # A mismatched M23-enabled cohort member must not cross the boundary.
    with sqlite3.connect(databases[4]) as con:
        (text,) = con.execute(
            "SELECT configuration FROM console_execution_projections"
        ).fetchone()
        payload = json.loads(text)
        payload["synthetic_apdex"] = False
        con.execute(
            "UPDATE console_execution_projections SET configuration=?",
            (json.dumps(payload),),
        )
    original = [db.read_bytes() for db in databases]
    filtered = forecast_local_duration(state)
    assert not filtered.available and filtered.sample_runs == 4
    assert [db.read_bytes() for db in databases] == original


def test_legacy_disabled_apdex_scope_remains_allowed_but_explicit_true_excluded(
    tmp_path,
):
    databases = [_audit(tmp_path, i) for i in range(5)]
    state = _state(tmp_path)
    state.synthetic_apdex = False
    state.apdex_experience = False
    assert forecast_local_duration(state).available
    with sqlite3.connect(databases[0]) as con:
        (text,) = con.execute(
            "SELECT configuration FROM console_execution_projections"
        ).fetchone()
        payload = json.loads(text)
        payload["synthetic_apdex"] = True
        con.execute(
            "UPDATE console_execution_projections SET configuration=?",
            (json.dumps(payload),),
        )
    assert forecast_local_duration(state).sample_runs == 4


@pytest.mark.parametrize(
    ("module_flag", "intensity_key", "new_value"),
    [
        ("synthetic_apdex", "apdex_samples", 245),
        ("synthetic_apdex", "apdex_concurrency", 5),
        ("apdex_experience", "apdex_experience_samples", 180),
        ("apdex_experience", "apdex_experience_kpm", "LARGEST_CONTENTFUL_PAINT"),
        ("apdex_experience", "apdex_experience_settle", 8.5),
        ("apdex_experience", "apdex_experience_architecture", "SPA"),
    ],
)
def test_workload_parameters_must_match_before_duration_prediction(
    tmp_path, module_flag, intensity_key, new_value,
):
    state = _configured_apdex_fields(_state(tmp_path))
    setattr(state, module_flag, True)
    databases = [_audit(tmp_path, i) for i in range(5)]
    for db in databases:
        with sqlite3.connect(db) as con:
            (config,) = con.execute(
                "SELECT configuration FROM console_execution_projections"
            ).fetchone()
            body = json.loads(config)
            body.update(apdex_duration_scope(state))
            con.execute(
                "UPDATE console_execution_projections SET configuration=?",
                (json.dumps(body),),
            )
    original = [db.read_bytes() for db in databases]
    projection = forecast_local_duration(state)
    assert projection.available and projection.sample_runs == 5
    setattr(state, intensity_key, new_value)
    different = forecast_local_duration(state)
    assert different.sample_runs == 0
    assert not different.available
    assert [db.read_bytes() for db in databases] == original


@pytest.mark.parametrize("tamper", [
    "workload_missing", "workload_missing_field", "workload_forged_type",
    "workload_extra_field",
])
def test_apdex_duration_missing_or_malformed_fingerprint_is_not_estimated(
    tmp_path, tamper,
):
    state = _configured_apdex_fields(_state(tmp_path))
    state.synthetic_apdex = True
    databases = [_audit(tmp_path, i) for i in range(5)]
    for db in databases:
        with sqlite3.connect(db) as con:
            (config,) = con.execute(
                "SELECT configuration FROM console_execution_projections"
            ).fetchone()
            body = json.loads(config)
            body.update(apdex_duration_scope(state))
            con.execute(
                "UPDATE console_execution_projections SET configuration=?",
                (json.dumps(body),),
            )
    assert forecast_local_duration(state).available
    with sqlite3.connect(databases[4]) as con:
        (config,) = con.execute(
            "SELECT configuration FROM console_execution_projections"
        ).fetchone()
        body = json.loads(config)
        if tamper == "workload_missing":
            body.pop("synthetic_apdex_workload")
        elif tamper == "workload_missing_field":
            body["synthetic_apdex_workload"].pop("apdex_samples")
        elif tamper == "workload_forged_type":
            body["synthetic_apdex_workload"]["apdex_samples"] = True
        elif tamper == "workload_extra_field":
            body["synthetic_apdex_workload"]["secret"] = "invalid"
        con.execute(
            "UPDATE console_execution_projections SET configuration=?",
            (json.dumps(body),),
        )
    before = [db.read_bytes() for db in databases]
    result = forecast_local_duration(state)
    assert result.sample_runs == 4 and not result.available
    assert [db.read_bytes() for db in databases] == before


@pytest.mark.parametrize("enabled_flag", (
    "improvement_enabled", "search_ai_competitive", "technical_remediation",
))
def test_319_optional_console_bool_must_be_explicit_in_new_physical_cohort(
    tmp_path, enabled_flag,
):
    """New console snapshots enable only exact observed optional scopes."""
    physical = [_audit(tmp_path, index) for index in range(5)]
    state = _state(tmp_path)
    setattr(state, enabled_flag, True)
    if enabled_flag == "search_ai_competitive":
        # CAT-05 requires a real declared shape; same enabled flag alone
        # no longer counts as equal execution work.
        state.search_queries = ("seguro de vida", "seguro viagem")
        state.search_depth = 20
        state.search_device = "mobile"
        state.market = "BR"
        state.language = "pt-BR"
        state.search_region = ""
        state.search_compare_content = True
        state.search_competitive = True
        state.search_max_content_pages = 3
        state.search_content_timeout_seconds = 10.0
        state.search_content_max_bytes = 2_000_000
        state.search_content_max_redirects = 5
        state.search_ymyl_mode = "AUTO"
    before = [db.read_bytes() for db in physical]
    old = forecast_local_duration(state)
    assert old.sample_runs == 0
    assert not old.available
    assert [db.read_bytes() for db in physical] == before

    for db in physical:
        with sqlite3.connect(db) as con:
            (raw,) = con.execute(
                "SELECT configuration FROM console_execution_projections"
            ).fetchone()
            config = json.loads(raw)
            config[enabled_flag] = True
            if enabled_flag == "search_ai_competitive":
                from rasai.console_search_duration_scope import search_ai_duration_scope
                config.update(search_ai_duration_scope(state))
            for sibling in (
                "improvement_enabled", "search_ai_competitive",
                "technical_remediation",
            ):
                config.setdefault(sibling, False)
            con.execute(
                "UPDATE console_execution_projections SET configuration=?",
                (json.dumps(config, sort_keys=True),),
            )
    verified = [db.read_bytes() for db in physical]
    forecast = forecast_local_duration(state)
    assert forecast.available and forecast.sample_runs == 5
    assert forecast.total is not None
    assert [db.read_bytes() for db in physical] == verified

    with sqlite3.connect(physical[4]) as con:
        (raw,) = con.execute(
            "SELECT configuration FROM console_execution_projections"
        ).fetchone()
        config = json.loads(raw)
        config[enabled_flag] = "true"
        con.execute(
            "UPDATE console_execution_projections SET configuration=?",
            (json.dumps(config, sort_keys=True),),
        )
    dirty = [db.read_bytes() for db in physical]
    rejected = forecast_local_duration(state)
    assert not rejected.available and rejected.sample_runs == 4
    assert [db.read_bytes() for db in physical] == dirty


@pytest.mark.parametrize("value", [True, False])
def test_boolean_historical_page_count_never_matches_numeric_scope(tmp_path, value):
    from rasai.audit_duration_forecast import _strictly_comparable
    state = _state(tmp_path)
    config = {
        "input_mode": "URL", "device": "MOBILE",
        "ai_provider": "auto", "ai_model": "",
        "content_remediation": False, "web_performance": True,
        "field_source": "NONE", "max_pages": value, "web_max_pages": 1,
    }
    assert _strictly_comparable(state, config) is False
    config["max_pages"] = 1
    state.max_pages = value
    assert _strictly_comparable(state, config) is False


@pytest.mark.parametrize("value", [1.5, "1.9", float("nan"), float("inf"), 0, -1])
def test_fractional_nonfinite_or_nonpositive_page_counts_abstain(tmp_path, value):
    from rasai.audit_duration_forecast import _strictly_comparable
    state = _state(tmp_path)
    config = {
        "input_mode": "URL", "device": "MOBILE",
        "ai_provider": "auto", "ai_model": "",
        "content_remediation": False, "web_performance": True,
        "field_source": "NONE", "max_pages": value, "web_max_pages": 1,
    }
    assert _strictly_comparable(state, config) is False


def test_integer_text_page_scope_remains_comparable(tmp_path):
    from rasai.audit_duration_forecast import _strictly_comparable
    state = _state(tmp_path)
    config = {
        "input_mode": "URL", "device": "MOBILE",
        "ai_provider": "auto", "ai_model": "",
        "content_remediation": False, "web_performance": True,
        "field_source": "NONE", "max_pages": "1", "web_max_pages": 1,
    }
    assert _strictly_comparable(state, config) is True


def test_large_adjacent_integer_page_counts_never_alias_via_float(tmp_path):
    from rasai.audit_duration_forecast import _strictly_comparable
    state = _state(tmp_path)
    state.max_pages = 9007199254740992
    config = {
        "input_mode": "URL", "device": "MOBILE",
        "ai_provider": "auto", "ai_model": "",
        "content_remediation": False, "web_performance": True,
        "field_source": "NONE", "max_pages": 9007199254740993,
        "web_max_pages": 1,
    }
    assert _strictly_comparable(state, config) is False
    config["max_pages"] = "9007199254740992"
    assert _strictly_comparable(state, config) is True


@pytest.mark.parametrize("invalid_target", [True, False, 1.0, 1.5, "1", None])
def test_noninteger_requested_page_scope_must_abstain(tmp_path, invalid_target):
    state = _state(tmp_path)
    for index in range(5):
        _audit(tmp_path, index)
    result = forecast_local_duration(state, target_pages=invalid_target)
    assert result.available is False
    assert result.sample_runs == 0


@pytest.mark.parametrize("bad_budget", [True, False, 1.5, "1.9", 0, -2, float("nan"), float("inf")])
def test_web_page_budget_must_be_integral_positive_in_duration_cohort(tmp_path, bad_budget):
    from rasai.audit_duration_forecast import _strictly_comparable
    state = _state(tmp_path)
    config = {
        "input_mode": "URL", "device": "MOBILE", "ai_provider": "auto",
        "ai_model": "", "content_remediation": False,
        "web_performance": True, "field_source": "NONE",
        "max_pages": 1, "web_max_pages": bad_budget,
    }
    assert _strictly_comparable(state, config) is False


def test_web_page_budget_uses_exact_integer_identity(tmp_path):
    from rasai.audit_duration_forecast import _strictly_comparable
    state = _state(tmp_path)
    state.web_max_pages = 9007199254740992
    config = {
        "input_mode": "URL", "device": "MOBILE", "ai_provider": "auto",
        "ai_model": "", "content_remediation": False,
        "web_performance": True, "field_source": "NONE",
        "max_pages": 1, "web_max_pages": 9007199254740993,
    }
    assert _strictly_comparable(state, config) is False
    config["web_max_pages"] = "9007199254740992"
    assert _strictly_comparable(state, config) is True


def test_duration_preview_discloses_missing_non_ai_stage_forecasts_without_guessing():
    from rasai.audit_duration_forecast import (
        AuditDurationForecast, DurationRange, format_duration_preview,
    )

    total = DurationRange("TOTAL", 5, 800000.0, 750000.0, 900000.0, 1000000.0)
    projection = AuditDurationForecast(
        sample_runs=5, total=total, ai_stages=(), http_request_stages=(),
    )
    lines = format_duration_preview(projection)
    assert any("Duracao total histor." in line for line in lines)
    assert any(
        "captura" in line and "PageSpeed" in line
        and "Apdex" in line and "N/D por fase" in line
        for line in lines
    )
    assert not any("mediana 0.0s" in line for line in lines)
