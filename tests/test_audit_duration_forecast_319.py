"""#319 conservative ex-ante physical duration preview; no collector/provider use."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai.audit_duration_forecast_319 import (
    forecast_local_duration,
    format_duration_preview,
)
from rasai.console_cost_confirmation import _render_forecast
from rasai.cost_forecast import CostForecast


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
           input_mode="URL", with_http=False, invalid_http=False) -> Path:
    audit_id = f"AUD-DURATION-{index}"
    folder = root / audit_id
    folder.mkdir(parents=True)
    database = folder / "audit.db"
    started = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
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
