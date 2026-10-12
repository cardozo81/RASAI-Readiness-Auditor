"""#319: conservative, read-only ex-ante duration ranges from comparable local AUDs.

Only completed local AUDs with a measured console wall-clock interval enter the
cohort. AI stage estimates require complete, offset-aware intervals in every
cohort member. Missing physical stage telemetry must remain N/D, not a guessed
residual or a sum of parallel provider call durations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import sqlite3
from statistics import median
from typing import Any, Mapping

from rasai.audit_attempt_timeline import read_audit_attempt_timeline


_MIN_RUNS = 5
_MIN_BACKTEST_RUNS = 8
_MIN_FORWARD_FOLDS = 3
_MAX_RUNS_SCANNED = 200
_MAX_WALL_MS = 48 * 60 * 60 * 1000
_COMPARABLE_FIELDS = (
    "input_mode", "device", "ai_provider", "ai_model",
    "content_remediation", "web_performance", "web_max_pages",
    "field_source", "max_pages",
)


@dataclass(frozen=True, slots=True)
class DurationRange:
    label: str
    sample_runs: int
    median_ms: float
    p25_ms: float
    p75_ms: float
    p90_ms: float


@dataclass(frozen=True, slots=True)
class DurationP90Backtest:
    """Retrospective leave-one-out diagnostic; never a calibrated SLA."""

    evaluated_runs: int
    within_held_out_p90: int
    observed_fraction: float
    method: str = "LEAVE_ONE_OUT_RETROSPECTIVE_ONLY"


@dataclass(frozen=True, slots=True)
class DurationForwardP90Backtest:
    """Chronological expanding-origin replay; not a prospectively tested SLA."""

    evaluated_runs: int
    within_prior_p90: int
    observed_fraction: float
    min_prior_cohort: int
    method: str = "PAST_COMPLETED_AUDS_ONLY_EXPANDING_WINDOW"


@dataclass(frozen=True, slots=True)
class AuditDurationForecast:
    sample_runs: int
    total: DurationRange | None
    ai_stages: tuple[DurationRange, ...]
    http_request_stages: tuple[DurationRange, ...] = ()
    source: str = "historico-local-console"
    notes: tuple[str, ...] = ()
    total_p90_backtest: DurationP90Backtest | None = None
    forward_p90_backtest: DurationForwardP90Backtest | None = None

    @property
    def available(self) -> bool:
        return self.total is not None


def _percentile(values: list[float], p: float) -> float:
    sorted_values = sorted(values)
    position = (len(sorted_values) - 1) * p
    index = int(position)
    nxt = min(index + 1, len(sorted_values) - 1)
    return sorted_values[index] + (sorted_values[nxt] - sorted_values[index]) * (position - index)


def _range(label: str, values: list[float]) -> DurationRange:
    return DurationRange(
        label, len(values), round(median(values), 2),
        round(_percentile(values, .25), 2),
        round(_percentile(values, .75), 2),
        round(_percentile(values, .90), 2),
    )


def _historical_p90_backtest(wall_ms: list[float]) -> DurationP90Backtest | None:
    """Leave one eligible AUD out of the P90 estimate for each fold.

    This is a self-consistency diagnostic of the exact same cohort and
    configuration gates; NOT out-of-time validation, independent holdout,
    calibration to a service-level target or a forecast confidence interval.
    """
    if len(wall_ms) < _MIN_BACKTEST_RUNS:
        return None
    hits = sum(
        value <= _percentile(wall_ms[:i] + wall_ms[i + 1:], .90)
        for i, value in enumerate(wall_ms)
    )
    return DurationP90Backtest(
        evaluated_runs=len(wall_ms),
        within_held_out_p90=hits,
        observed_fraction=round(hits / len(wall_ms), 4),
    )


def _chronological_p90_backtest(
    eligible: list[tuple[Any, ...]],
) -> DurationForwardP90Backtest | None:
    """Replay P90 as of each AUD start using only previously finished AUDs.

    Sorting on file mtime or completion order risks future-data leakage for
    overlapping runs. A prior observation enters the fold only if its
    *physical end* is at or before the target AUD's physical start.
    """
    if len(eligible) < _MIN_BACKTEST_RUNS:
        return None
    ordered = sorted(eligible, key=lambda item: (item[4], item[1]))
    hits = 0
    folds = 0
    for observed in ordered:
        target_start = observed[4]
        history = [
            item[0] for item in ordered
            if item[1] != observed[1] and item[5] <= target_start
        ]
        if len(history) < _MIN_RUNS:
            continue
        folds += 1
        hits += observed[0] <= _percentile(history, .90)
    if folds < _MIN_FORWARD_FOLDS:
        return None
    return DurationForwardP90Backtest(
        evaluated_runs=folds, within_prior_p90=hits,
        observed_fraction=round(hits / folds, 4),
        min_prior_cohort=_MIN_RUNS,
    )


def _time(value: Any) -> datetime | None:
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError):
        return None


def _strictly_comparable(current: Any, historical: Mapping[str, Any]) -> bool:
    # The existing forecast comparison allows missing legacy fields for monetary
    # usage. Wall-time is more sensitive to configuration, so fail closed here.
    for field in _COMPARABLE_FIELDS:
        if field not in historical or not hasattr(current, field):
            return False
        wanted = getattr(current, field)
        old = historical[field]
        if field == "max_pages":
            try:
                if int(wanted) != int(old):
                    return False
            except (ValueError, TypeError):
                return False
        elif field in {"content_remediation", "web_performance"}:
            if type(wanted) is not bool or type(old) is not bool or wanted != old:
                return False
        elif str(wanted or "").strip().casefold() != str(old or "").strip().casefold():
            return False
    # Optional workloads change physical duration. An enabled current scope
    # needs explicit persisted evidence; a historically enabled scope cannot
    # silently enter a baseline where it is disabled now. Legacy absent flags
    # remain admissible only for a current disabled/default scope.
    for flag in ("improvement_enabled", "search_ai_competitive",
                 "technical_remediation"):
        current_value = getattr(current, flag, False)
        if type(current_value) is not bool:
            return False
        if flag not in historical:
            if current_value:
                return False
            continue
        historic_value = historical[flag]
        if type(historic_value) is not bool or historic_value != current_value:
            return False
    return True


def _m21_http_request_sums(conn: sqlite3.Connection, audit_id: str) -> dict[str, float]:
    """Cumulative HTTP request time, never an M21 stage wall-clock duration.

    Only complete, nonnegative per-request timings for a known service qualify.
    Missing table/columns, unmeasured attempts and schema drift abstain.
    """
    try:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(web_performance_attempts)")
        }
        if not {"audit_id", "service", "duration_ms"}.issubset(columns):
            return {}
        rows = conn.execute(
            "SELECT service, duration_ms FROM web_performance_attempts WHERE audit_id=?",
            (audit_id,),
        )
        totals: dict[str, float] = {}
        rejected: set[str] = set()
        for service, duration in rows:
            name = str(service or "").strip().upper()
            if name not in {"PAGESPEED_INSIGHTS", "CRUX_API"}:
                continue
            if duration is None:
                rejected.add(name)
                continue
            try:
                elapsed = float(duration)
            except (TypeError, ValueError, OverflowError):
                rejected.add(name)
                continue
            if not math.isfinite(elapsed) or not 0 < elapsed <= _MAX_WALL_MS:
                rejected.add(name)
                continue
            totals[name] = totals.get(name, 0.0) + elapsed
        return {
            name: milliseconds
            for name, milliseconds in totals.items()
            if name not in rejected and milliseconds <= _MAX_WALL_MS
        }
    except sqlite3.Error:
        return {}



def _ai_intervals_within_console(
    con: sqlite3.Connection, audit_id: str, started: datetime, finished: datetime,
) -> bool:
    """Fail closed on IA timing that cannot belong to the same physical AUD.

    Attempt ledgers may include later continuations or clock inconsistencies.
    Those attempts remain valid economic evidence but may NOT supply a stage
    duration estimate for this console wall-clock cohort.
    """
    for table in ("ai_provider_attempts", "content_remediation_attempts"):
        columns = {
            str(row[1]) for row in con.execute("PRAGMA table_info(" + table + ")")
        }
        if not columns:
            continue
        if not {"audit_id", "started_at", "finished_at"}.issubset(columns):
            return False
        for first, last in con.execute(
            "SELECT started_at, finished_at FROM " + table + " WHERE audit_id=?",
            (audit_id,),
        ):
            lo, hi = _time(first), _time(last)
            if lo is None or hi is None or not (started <= lo <= hi <= finished):
                return False
    return True


def _historical_audit(
    database: Path, state: Any, target_pages: int,
) -> tuple[float, str, dict[str, float], dict[str, float], datetime, datetime] | None:
    # Only local physical AUD packages may enter the historical cohort.
    # Following an AUD directory or audit.db symlink could import a
    # foreign package with a matching audit_id into the forecast.
    if (
        database.is_symlink() or database.parent.is_symlink()
        or any(
            Path(str(database) + suffix).exists()
            for suffix in ("-wal", "-shm", "-journal")
        )
    ):
        # Historical forecasting must not include an AUD with an unsealed
        # SQLite transaction. Even a logically COMPLETE row may be read from
        # an active WAL, yielding a projection not reproducible from audit.db.
        return None
    try:
        source_stat = database.stat()
        source_identity = (
            source_stat.st_dev, source_stat.st_ino,
            source_stat.st_size, source_stat.st_mtime_ns,
            source_stat.st_ctime_ns,
        )
        conn = sqlite3.connect(
            database.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=.5,
        )
    except (sqlite3.Error, OSError):
        return None
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT audit_id, configuration, duration_ms, started_at, finished_at "
            "FROM console_execution_projections LIMIT 2"
        ).fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
        audit_id = str(row["audit_id"] or "")
        if audit_id != database.parent.name:
            return None
        try:
            config = json.loads(str(row["configuration"]))
        except (ValueError, TypeError):
            return None
        if not isinstance(config, dict) or not _strictly_comparable(state, config):
            return None
        # Physical duration must not be learned from a logically partial AUD.
        # COMPLETED is the lifecycle status, NOT proof that mandatory catalog
        # requirements reached completion_status=COMPLETE.
        audit_columns = {
            str(column[1]) for column in conn.execute("PRAGMA table_info(audits)")
        }
        page_columns = {
            str(column[1]) for column in conn.execute("PRAGMA table_info(pages)")
        }
        if not {"audit_id", "status", "completion_status"}.issubset(audit_columns):
            return None
        if not {"audit_id", "page_id"}.issubset(page_columns):
            return None
        audit = conn.execute(
            "SELECT status, completion_status FROM audits WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        if (
            not audit
            or str(audit["status"] or "").strip().upper() != "COMPLETED"
            or str(audit["completion_status"] or "").strip().upper() != "COMPLETE"
        ):
            return None
        count = int(conn.execute(
            "SELECT COUNT(*) FROM pages WHERE audit_id=?", (audit_id,),
        ).fetchone()[0])
        if count != target_pages or count <= 0:
            return None
        wall = float(row["duration_ms"])
        started = _time(row["started_at"])
        finished = _time(row["finished_at"])
        if not started or not finished or not (0 < wall <= _MAX_WALL_MS):
            return None
        observed = (finished - started).total_seconds() * 1000
        if not (0 < observed <= _MAX_WALL_MS) or abs(observed - wall) > max(5000, observed * .05):
            return None
        # This optional stage projection reads existing, aud-scoped AI telemetry
        # only. It never requests a provider and does not materialize results.
        timeline = read_audit_attempt_timeline(database, audit_id)
        # The stage union may be individually shorter than AUD duration while
        # physically occurring entirely outside the observed console session.
        # Never use such activity to forecast in-session stage latency.
        stage_provenance_ok = _ai_intervals_within_console(
            conn, audit_id, started, finished,
        )
        stages = {
            item.name: float(item.union_active_ms)
            for item in timeline.stages
            if (
                stage_provenance_ok
                and item.attempts > 0
                and item.unknown_intervals == 0
                and item.union_active_ms is not None
                and 0 <= float(item.union_active_ms) <= wall
            )
        }
        requests = _m21_http_request_sums(conn, audit_id)
        # Immutable SQLite reads are not a lock on the physical AUD. Abort
        # if a journal appeared or file identity/mtime/size moved mid-read;
        # this inexpensive guard does not pretend to cryptographically seal
        # every historical AUD (which would multiply preview I/O).
        current_stat = database.stat()
        if (
            database.is_symlink() or database.parent.is_symlink()
            or any(Path(str(database) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))
            or (
                current_stat.st_dev, current_stat.st_ino,
                current_stat.st_size, current_stat.st_mtime_ns,
                current_stat.st_ctime_ns,
            ) != source_identity
        ):
            return None
        return (wall, audit_id, stages, requests, started, finished)
    except (OSError, sqlite3.Error, ValueError, TypeError, OverflowError):
        return None
    finally:
        conn.close()


def forecast_local_duration(
    state: Any, *, target_pages: int = 1,
) -> AuditDurationForecast:
    """Return descriptive quartiles only if >=5 matching completed AUDs exist.

    Stage estimates are *active AI time*, not additive wall-clock stages.
    The total is based solely on a complete console-observed AUD duration.
    """
    root = Path(str(getattr(state, "audits_root", "audits")))
    if target_pages < 1 or not root.is_dir():
        return AuditDurationForecast(0, None, (), notes=("Sem historico local comparavel.",))
    try:
        databases = sorted(
            (
                p / "audit.db" for p in root.glob("AUD-*")
                if p.is_dir() and not p.is_symlink()
                and (p / "audit.db").is_file()
                and not (p / "audit.db").is_symlink()
                and p.resolve().parent == root.resolve()
            ),
            key=lambda p: p.stat().st_mtime_ns, reverse=True,
        )[:_MAX_RUNS_SCANNED]
    except OSError:
        return AuditDurationForecast(0, None, (), notes=("Historico local inacessivel.",))
    eligible = []
    for database in databases:
        observation = _historical_audit(database, state, target_pages)
        if observation:
            eligible.append(observation)
    count = len(eligible)
    if count < _MIN_RUNS:
        return AuditDurationForecast(
            count, None, (),
            notes=(
                f"Sem previsao de duracao: {count}/{_MIN_RUNS} AUDs concluidas "
                "com configuracao registrada compativel, mesmo numero de paginas "
                "e intervalo fisico consistente.",
            ),
        )
    wall_values = [a[0] for a in eligible]
    total = _range("Auditoria total (relogio do console)", wall_values)
    p90_diagnostic = _historical_p90_backtest(wall_values)
    forward_diagnostic = _chronological_p90_backtest(eligible)
    names = sorted(set().union(*(set(a[2]) for a in eligible)))
    stages = tuple(
        _range(name, [a[2][name] for a in eligible])
        for name in names
        if all(name in a[2] for a in eligible)
    )
    technical_names = sorted(set().union(*(set(a[3]) for a in eligible)))
    http_request_stages = tuple(
        _range(name, [a[3][name] for a in eligible])
        for name in technical_names
        if all(name in a[3] for a in eligible)
    )
    return AuditDurationForecast(
        count, total, stages, http_request_stages=http_request_stages,
        total_p90_backtest=p90_diagnostic,
        forward_p90_backtest=forward_diagnostic,
        notes=(
            "Mediana, P25-P75 e P90 sao descritores historicos, nao SLA nem "
            "intervalos probabilisticos calibrados.",
            "Atividade de IA pode ocorrer em paralelo: tempos por etapa "
            "NAO devem ser somados para prever duracao da AUD.",
            "Tempos de IA fora do intervalo do console, ou sem relogios "
            "rastreaveis, ficam N/D na previsao por etapa.",
            "Coleta, PageSpeed, Apdex e relatorio nao possuem duracao fisica "
            "por etapa comprovada por este historico; permanecem N/D.",
            "Quando disponiveis, tempos PSI/CrUX somam duracoes de HTTP por "
            "servico: NAO sao wall-clock do M21, nem aditivos a IA ou a AUD.",
            "Flag opcional nao presente na configuracao historica impede "
            "comparacao quando solicitada; etapas opcionais externas ficam fora.",
        ),
    )


def format_duration_preview(projection: AuditDurationForecast) -> tuple[str, ...]:
    """Human-readable lines. No monetary forecast or external operations."""
    if projection.total is None:
        return ("Previsao de duracao : N/D (historico fisico insuficiente)", *projection.notes)
    def seconds(ms: float) -> str:
        return f"{ms / 1000:.1f}s"
    lines = [
        f"Duracao total histor.: mediana {seconds(projection.total.median_ms)} "
        f"| P25-P75 {seconds(projection.total.p25_ms)}-{seconds(projection.total.p75_ms)} "
        f"| P90 {seconds(projection.total.p90_ms)} "
        f"({projection.sample_runs} AUDs)",
    ]
    diagnostic = projection.total_p90_backtest
    if diagnostic is not None:
        lines.append(
            "Backtest retrospectivo LOO do P90 total: "
            f"{diagnostic.within_held_out_p90}/{diagnostic.evaluated_runs} "
            "AUDs dentro do P90 reconstruido sem a propria AUD; "
            "nao e calibracao prospectiva ou SLA."
        )
    forward = projection.forward_p90_backtest
    if forward is not None:
        lines.append(
            "Replay cronologico P90 total (AUDs anteriores concluidas): "
            f"{forward.within_prior_p90}/{forward.evaluated_runs} "
            "dentro do P90 calculado com historico disponivel antes do inicio; "
            "amostra local observacional, nao homologacao de SLA ou "
            "garantia de previsao futura."
        )
    for stage in projection.ai_stages:
        lines.append(
            f"IA {stage.label}: tempo ativo mediano {seconds(stage.median_ms)} "
            f"({stage.sample_runs} AUDs)"
        )
    for stage in projection.http_request_stages:
        lines.append(
            f"HTTP {stage.label}: tempo acumulado de requests, mediana "
            f"{seconds(stage.median_ms)} ({stage.sample_runs} AUDs; nao wall-clock)"
        )
    lines.extend(projection.notes)
    return tuple(lines)
