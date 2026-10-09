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
        audits_root=str(root), device="MOBILE", ai_provider="auto",
        ai_model="", content_remediation=False, web_performance=True,
        field_source="NONE", max_pages=1, improvement_enabled=False,
        search_ai_competitive=False,
    )


def _audit(root: Path, index: int, *, status="COMPLETE", duration=600_000,
           with_stage=True, device="MOBILE", complete_config=True,
           wrong_clock=False, pages=1) -> Path:
    audit_id = f"AUD-DURATION-{index}"
    folder = root / audit_id
    folder.mkdir(parents=True)
    database = folder / "audit.db"
    started = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
    finished = started + timedelta(milliseconds=duration * (2 if wrong_clock else 1))
    config = {
        "device": device, "ai_provider": "auto", "ai_model": "",
        "content_remediation": False, "web_performance": True,
        "field_source": "NONE", "max_pages": 1,
    }
    if not complete_config:
        config.pop("field_source")
    with sqlite3.connect(database) as con:
        con.executescript(
            """
            CREATE TABLE audits (audit_id TEXT PRIMARY KEY, status TEXT);
            CREATE TABLE pages (page_id TEXT PRIMARY KEY);
            CREATE TABLE console_execution_projections (
                audit_id TEXT, configuration TEXT, duration_ms INTEGER,
                started_at TEXT, finished_at TEXT
            );
            CREATE TABLE ai_provider_attempts (
                attempt_id TEXT PRIMARY KEY, audit_id TEXT,
                operation TEXT, started_at TEXT, finished_at TEXT
            );
            """
        )
        con.execute("INSERT INTO audits VALUES (?,?)", (audit_id, status))
        for page_no in range(pages):
            con.execute("INSERT INTO pages VALUES (?)", (f"PAGE-{page_no}",))
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
