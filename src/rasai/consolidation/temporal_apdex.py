"""Temporal Apdex consolidation across immutable RASAi AUD workspaces.

This module is deliberately outside the audit execution pipeline. It opens source
``AUD-*/audit.db`` files in read-only mode, pools only methodologically comparable
samples, and never rewrites source evidence or recalculates SARI/SCORE-GEO.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import Path
import json
import math
import re
import sqlite3
import statistics
from typing import Any, Iterable

from .models import ConsolidationFilter

TEMPORAL_APDEX_CONTRACT = "TEMPORAL-APDEX-001"


@dataclass(slots=True)
class _SeriesBuilder:
    kind: str
    url: str
    device: str
    task_id: str
    profile_id: str
    threshold_seconds: float | None
    frustrated_threshold_seconds: float | None
    kpm: str | None
    session_mode: str | None
    errors_affect_apdex: bool | None
    error_scope: str | None
    pacing: str
    context_note: str
    audit_ids: set[str] = field(default_factory=set)
    summary_observations: int = 0
    valid_samples: int = 0
    invalid_samples: int = 0
    satisfied_count: int = 0
    tolerating_count: int = 0
    frustrated_count: int = 0
    small_groups: int = 0
    final_groups: int = 0
    durations: list[tuple[str, float]] = field(default_factory=list)
    calculated_times: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TemporalApdexSeries:
    contract: str
    kind: str
    url: str
    device: str
    task_id: str
    profile_id: str
    threshold_seconds: float | None
    frustrated_threshold_seconds: float | None
    kpm: str | None
    session_mode: str | None
    errors_affect_apdex: bool | None
    error_scope: str | None
    pacing: str
    context_note: str
    audits: int
    summary_observations: int
    valid_samples: int
    invalid_samples: int
    satisfied_count: int
    tolerating_count: int
    frustrated_count: int
    apdex_score: float | None
    samples_with_duration: int
    duration_mean_ms: float | None
    duration_median_ms: float | None
    duration_p75_ms: float | None
    duration_p90_ms: float | None
    duration_p95_ms: float | None
    duration_p99_ms: float | None
    duration_min_ms: float | None
    duration_max_ms: float | None
    duration_stddev_ms: float | None
    duration_cv: float | None
    first_observed_at: str | None
    last_observed_at: str | None
    small_groups: int
    final_groups: int
    limitation: str | None


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(ordered[low])
    weight = position - low
    return float(ordered[low] * (1.0 - weight) + ordered[high] * weight)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(connection, table):
        return set()
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _select_rows(
    connection: sqlite3.Connection,
    table: str,
    wanted: tuple[str, ...],
    *,
    where: str = "",
    params: tuple[Any, ...] = (),
    order_by: str = "",
) -> tuple[dict[str, Any], ...]:
    cols = _columns(connection, table)
    if not cols:
        return ()
    select = [name if name in cols else f"NULL AS {name}" for name in wanted]
    sql = f"SELECT {','.join(select)} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return tuple(dict(row) for row in connection.execute(sql, params).fetchall())


def _canonical_json(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        parsed = json.loads(str(value)) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return str(value)
    return json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _config_values(value: Any) -> tuple[str, str]:
    if value in (None, ""):
        return "", ""
    try:
        parsed = json.loads(str(value)) if isinstance(value, str) else dict(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return "", ""
    delay = parsed.get("delay_seconds")
    concurrency = parsed.get("concurrency")
    return str(delay if delay is not None else ""), str(concurrency if concurrency is not None else "")


def _path_for(audits_root: Path, audit: dict[str, Any]) -> Path:
    raw = Path(str(audit.get("db_path") or ""))
    return raw if raw.is_absolute() else audits_root / raw


def _allowed(filters: ConsolidationFilter, url: str, device: str) -> bool:
    if filters.urls and url not in set(filters.urls):
        return False
    if filters.devices and device.upper() not in {item.upper() for item in filters.devices}:
        return False
    return True


def _key(builder: _SeriesBuilder) -> tuple[Any, ...]:
    return (
        builder.kind,
        builder.url,
        builder.device,
        builder.task_id,
        builder.profile_id,
        builder.threshold_seconds,
        builder.frustrated_threshold_seconds,
        builder.kpm,
        builder.session_mode,
        builder.errors_affect_apdex,
        builder.error_scope,
        builder.pacing,
        builder.context_note,
    )


def _ensure(groups: dict[tuple[Any, ...], _SeriesBuilder], builder: _SeriesBuilder) -> _SeriesBuilder:
    key = _key(builder)
    current = groups.get(key)
    if current is None:
        groups[key] = builder
        return builder
    return current


def _add_summary(builder: _SeriesBuilder, audit_id: str, row: dict[str, Any]) -> None:
    builder.audit_ids.add(audit_id)
    builder.summary_observations += 1
    builder.valid_samples += _integer(row.get("valid_samples"))
    builder.invalid_samples += _integer(row.get("invalid_samples"))
    builder.satisfied_count += _integer(row.get("satisfied_count"))
    builder.tolerating_count += _integer(row.get("tolerating_count"))
    builder.frustrated_count += _integer(row.get("frustrated_count"))
    builder.small_groups += int(bool(row.get("small_group")))
    builder.final_groups += int(bool(row.get("final_group")))
    timestamp = str(row.get("calculated_at") or "")
    if timestamp:
        builder.calculated_times.append(timestamp)


def _navigation(
    connection: sqlite3.Connection,
    audit_id: str,
    filters: ConsolidationFilter,
    groups: dict[tuple[Any, ...], _SeriesBuilder],
) -> None:
    if not _table_exists(connection, "synthetic_apdex_summaries"):
        return
    run_rows = _select_rows(
        connection,
        "synthetic_apdex_runs",
        ("task_id", "delay_seconds", "concurrency"),
        where="audit_id=?" if "audit_id" in _columns(connection, "synthetic_apdex_runs") else "",
        params=(audit_id,) if "audit_id" in _columns(connection, "synthetic_apdex_runs") else (),
    )
    run = run_rows[0] if run_rows else {}
    task_default = str(run.get("task_id") or "NAVIGATION_LOAD")
    pacing = f"delay={run.get('delay_seconds') if run.get('delay_seconds') is not None else '-'};concurrency={run.get('concurrency') if run.get('concurrency') is not None else '-'}"
    summaries = _select_rows(
        connection,
        "synthetic_apdex_summaries",
        (
            "audit_id", "url", "device", "calculated_at", "task_id", "profile_id",
            "threshold_seconds", "frustration_seconds", "valid_samples", "invalid_samples",
            "satisfied_count", "tolerating_count", "frustrated_count", "small_group", "final_group",
        ),
        where="audit_id=?",
        params=(audit_id,),
        order_by="calculated_at,url,device",
    )
    contexts: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in summaries:
        url = str(row.get("url") or "")
        device = str(row.get("device") or "UNKNOWN").upper()
        if not _allowed(filters, url, device):
            continue
        threshold = _number(row.get("threshold_seconds"))
        frustrated = _number(row.get("frustration_seconds"))
        if frustrated is None and threshold is not None:
            frustrated = threshold * 4.0
        builder = _SeriesBuilder(
            kind="NAVIGATION",
            url=url,
            device=device,
            task_id=str(row.get("task_id") or task_default),
            profile_id=str(row.get("profile_id") or "UNKNOWN"),
            threshold_seconds=threshold,
            frustrated_threshold_seconds=frustrated,
            kpm="NAVIGATION_DURATION",
            session_mode="cold",
            errors_affect_apdex=True,
            error_scope="navigation",
            pacing=pacing,
            context_note="T/4T clássico; BrowserContext novo e cache local desabilitado por amostra.",
        )
        target = _ensure(groups, builder)
        _add_summary(target, audit_id, row)
        contexts[(url, device)] = _key(target)

    if not contexts or not _table_exists(connection, "synthetic_apdex_samples"):
        return
    samples = _select_rows(
        connection,
        "synthetic_apdex_samples",
        ("url", "device", "classification", "duration_ms", "captured_at"),
        where="audit_id=?",
        params=(audit_id,),
        order_by="captured_at,url,device,run_index",
    )
    for row in samples:
        url = str(row.get("url") or "")
        device = str(row.get("device") or "UNKNOWN").upper()
        key = contexts.get((url, device))
        if key is None or row.get("classification") is None:
            continue
        duration = _number(row.get("duration_ms"))
        if duration is None:
            continue
        groups[key].durations.append((str(row.get("captured_at") or ""), duration))


def _experience(
    connection: sqlite3.Connection,
    audit_id: str,
    filters: ConsolidationFilter,
    groups: dict[tuple[Any, ...], _SeriesBuilder],
) -> None:
    if not _table_exists(connection, "synthetic_ux_apdex_summaries"):
        return
    runs = _select_rows(
        connection,
        "synthetic_ux_apdex_runs",
        (
            "task_id", "device_mix", "session_mode", "kpm", "satisfied_threshold_seconds",
            "frustrated_threshold_seconds", "errors_affect_apdex", "error_scope", "settle_seconds",
            "calibration_source", "configuration",
        ),
        where="audit_id=?",
        params=(audit_id,),
    )
    run = runs[0] if runs else {}
    delay, concurrency = _config_values(run.get("configuration"))
    pacing = f"delay={delay or '-'};concurrency={concurrency or '-'};settle={run.get('settle_seconds') if run.get('settle_seconds') is not None else '-'}"
    kpm = str(run.get("kpm") or "UNKNOWN")
    session_mode = str(run.get("session_mode") or "UNKNOWN")
    sat = _number(run.get("satisfied_threshold_seconds"))
    frustrated = _number(run.get("frustrated_threshold_seconds"))
    errors_affect = _bool_or_none(run.get("errors_affect_apdex"))
    error_scope = str(run.get("error_scope") or "UNKNOWN")
    device_mix = _canonical_json(run.get("device_mix"))
    calibration = str(run.get("calibration_source") or "UNKNOWN")
    task_default = str(run.get("task_id") or "SYNTHETIC_LOAD_ACTION")
    summaries = _select_rows(
        connection,
        "synthetic_ux_apdex_summaries",
        (
            "audit_id", "url", "device", "calculated_at", "task_id", "profile_id", "valid_samples",
            "invalid_samples", "satisfied_count", "tolerating_count", "frustrated_count",
            "small_group", "final_group",
        ),
        where="audit_id=?",
        params=(audit_id,),
        order_by="calculated_at,url,device",
    )
    native_contexts: dict[tuple[str, str], tuple[Any, ...]] = {}
    population_contexts: dict[str, tuple[Any, ...]] = {}
    for row in summaries:
        url = str(row.get("url") or "")
        device = str(row.get("device") or "UNKNOWN").upper()
        if not _allowed(filters, url, device):
            continue
        context_note = f"KPM={kpm}; calibração={calibration}"
        if device == "POPULATION":
            context_note += f"; device_mix={device_mix or '-'}"
        builder = _SeriesBuilder(
            kind="EXPERIENCE",
            url=url,
            device=device,
            task_id=str(row.get("task_id") or task_default),
            profile_id=str(row.get("profile_id") or "UNKNOWN"),
            threshold_seconds=sat,
            frustrated_threshold_seconds=frustrated,
            kpm=kpm,
            session_mode=session_mode,
            errors_affect_apdex=errors_affect,
            error_scope=error_scope,
            pacing=pacing,
            context_note=context_note,
        )
        # The population mix is part of comparability even when the display note is the only
        # place it is surfaced. Appending it to the key prevents unlike populations from merging.
        if device == "POPULATION":
            builder.context_note += f"; population_identity={device_mix}"
        target = _ensure(groups, builder)
        _add_summary(target, audit_id, row)
        key = _key(target)
        if device == "POPULATION":
            population_contexts[url] = key
        else:
            native_contexts[(url, device)] = key

    if (not native_contexts and not population_contexts) or not _table_exists(connection, "synthetic_ux_apdex_samples"):
        return
    samples = _select_rows(
        connection,
        "synthetic_ux_apdex_samples",
        ("url", "device", "classification", "kpm_value_ms", "captured_at"),
        where="audit_id=?",
        params=(audit_id,),
        order_by="captured_at,url,device,run_index",
    )
    for row in samples:
        if row.get("classification") is None:
            continue
        duration = _number(row.get("kpm_value_ms"))
        if duration is None:
            continue
        url = str(row.get("url") or "")
        device = str(row.get("device") or "UNKNOWN").upper()
        native = native_contexts.get((url, device))
        if native is not None:
            groups[native].durations.append((str(row.get("captured_at") or ""), duration))
        population = population_contexts.get(url)
        if population is not None:
            groups[population].durations.append((str(row.get("captured_at") or ""), duration))


def _finalize(builder: _SeriesBuilder) -> TemporalApdexSeries:
    counts_total = builder.satisfied_count + builder.tolerating_count + builder.frustrated_count
    score = (
        (builder.satisfied_count + 0.5 * builder.tolerating_count) / builder.valid_samples
        if builder.valid_samples > 0
        else None
    )
    ordered_samples = sorted(builder.durations, key=lambda item: item[0])
    durations = [value for _, value in ordered_samples]
    mean = statistics.fmean(durations) if durations else None
    stddev = statistics.pstdev(durations) if len(durations) > 1 else (0.0 if durations else None)
    cv = (stddev / mean) if mean not in (None, 0) and stddev is not None else None
    limitations = list(builder.limitations)
    if counts_total != builder.valid_samples:
        limitations.append(
            f"Contagens S/T/F ({counts_total}) diferem das amostras válidas persistidas ({builder.valid_samples}); o denominador persistido foi preservado."
        )
    if builder.valid_samples and len(durations) < builder.valid_samples:
        limitations.append(
            f"{builder.valid_samples - len(durations)} amostra(s) válida(s) não possuem duração/KPM numérica utilizável; entram no Apdex, mas não na distribuição temporal."
        )
    times = [item for item in builder.calculated_times if item] + [stamp for stamp, _ in ordered_samples if stamp]
    return TemporalApdexSeries(
        contract=TEMPORAL_APDEX_CONTRACT,
        kind=builder.kind,
        url=builder.url,
        device=builder.device,
        task_id=builder.task_id,
        profile_id=builder.profile_id,
        threshold_seconds=builder.threshold_seconds,
        frustrated_threshold_seconds=builder.frustrated_threshold_seconds,
        kpm=builder.kpm,
        session_mode=builder.session_mode,
        errors_affect_apdex=builder.errors_affect_apdex,
        error_scope=builder.error_scope,
        pacing=builder.pacing,
        context_note=builder.context_note,
        audits=len(builder.audit_ids),
        summary_observations=builder.summary_observations,
        valid_samples=builder.valid_samples,
        invalid_samples=builder.invalid_samples,
        satisfied_count=builder.satisfied_count,
        tolerating_count=builder.tolerating_count,
        frustrated_count=builder.frustrated_count,
        apdex_score=round(score, 6) if score is not None else None,
        samples_with_duration=len(durations),
        duration_mean_ms=mean,
        duration_median_ms=statistics.median(durations) if durations else None,
        duration_p75_ms=_percentile(durations, 0.75),
        duration_p90_ms=_percentile(durations, 0.90),
        duration_p95_ms=_percentile(durations, 0.95),
        duration_p99_ms=_percentile(durations, 0.99),
        duration_min_ms=min(durations) if durations else None,
        duration_max_ms=max(durations) if durations else None,
        duration_stddev_ms=stddev,
        duration_cv=cv,
        first_observed_at=min(times) if times else None,
        last_observed_at=max(times) if times else None,
        small_groups=builder.small_groups,
        final_groups=builder.final_groups,
        limitation=" ".join(limitations) if limitations else None,
    )


def build_temporal_apdex(
    *,
    audits_root: str | Path,
    audits: Iterable[dict[str, Any]],
    filters: ConsolidationFilter,
) -> tuple[TemporalApdexSeries, ...]:
    """Pool comparable Apdex evidence across the selected completed AUD workspaces.

    Series are intentionally URL-scoped. Different URLs, devices, profiles, thresholds,
    KPM/error/session policies or pacing contexts are never merged silently.
    """
    root = Path(audits_root)
    groups: dict[tuple[Any, ...], _SeriesBuilder] = {}
    for audit in audits:
        audit_id = str(audit.get("audit_id") or "")
        db_path = _path_for(root, audit)
        if not audit_id or not db_path.is_file():
            continue
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, timeout=2.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            try:
                _navigation(connection, audit_id, filters, groups)
                _experience(connection, audit_id, filters, groups)
            finally:
                connection.close()
        except sqlite3.Error:
            # The base consolidator already owns refresh diagnostics. Temporal Apdex is additive
            # and must not make an otherwise valid CONS generation fail closed.
            continue
    return tuple(
        sorted(
            (_finalize(builder) for builder in groups.values()),
            key=lambda item: (item.kind, item.url, item.device, item.profile_id, item.threshold_seconds or -1.0),
        )
    )


def _fmt(value: float | None, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _apdex_tone(value: float | None) -> str:
    if value is None:
        return "neutral"
    if value >= 0.85:
        return "good"
    if value >= 0.70:
        return "warn"
    return "bad"


def _apdex_result_html(value: float | None) -> str:
    tone = _apdex_tone(value)
    return f"<strong class='result-value {tone}'>{_fmt(value, 3)}</strong>"


def _kind_label(value: str) -> str:
    return "Apdex de navegação" if value == "NAVIGATION" else "Apdex de experiência"


def _device_label(value: str) -> str:
    text = str(value or "UNKNOWN").upper()
    return {
        "MOBILE": "Dispositivo móvel",
        "DESKTOP": "Desktop",
        "TABLET": "Tablet",
        "POPULATION": "População consolidada",
        "GLOBAL": "Escopo global",
        "UNKNOWN": "Desconhecido",
    }.get(text, str(value or "-"))


def _kpm_label(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    return {
        "USER_ACTION_DURATION": "Duração da ação do usuário",
        "NAVIGATION_DURATION": "Duração da navegação",
        "DOM_INTERACTIVE": "Tempo até DOM interativo",
        "LOAD_EVENT_START": "Início do evento de carregamento",
        "LOAD_EVENT_END": "Fim do evento de carregamento",
        "RESPONSE_START": "Início da resposta",
        "RESPONSE_END": "Fim da resposta",
        "LARGEST_CONTENTFUL_PAINT": "Largest Contentful Paint (LCP)",
    }.get(raw, "Métrica principal não identificada" if not raw else raw.replace("_", " ").title())


def _profile_label(value: str) -> str:
    raw = str(value or "").strip()
    normalized = raw.casefold()
    if raw.startswith("RASAI_"):
        device = (
            "Dispositivo móvel" if "mobile" in normalized
            else "Desktop" if "desktop" in normalized
            else "Tablet" if "tablet" in normalized
            else "Perfil controlado"
        )
        browser = "Chromium" if "chromium" in normalized else "navegador controlado"
        network = "rede móvel 4G balanceada" if "4g-balanced" in normalized else "rede controlada"
        balance = "balanceado" if "balanced" in normalized else "controlado"
        return f"{device} · {browser} · perfil {balance} · {network}"
    return raw.replace("_", " ").replace("-", " ").strip() or "Perfil não informado"


def _pacing_label(value: str) -> str:
    parts: dict[str, str] = {}
    for token in str(value or "").split(";"):
        key, separator, raw = token.partition("=")
        if separator:
            parts[key.strip().casefold()] = raw.strip()
    labels = []
    if parts.get("delay") not in (None, "", "-"):
        labels.append(f"intervalo entre amostras: {parts['delay']} s")
    if parts.get("concurrency") not in (None, "", "-"):
        labels.append(f"concorrência: {parts['concurrency']}")
    if parts.get("settle") not in (None, "", "-"):
        labels.append(f"estabilização: {parts['settle']} s")
    return " · ".join(labels) or "parâmetros de execução não informados"


def _calibration_label(value: str) -> str:
    raw = str(value or "").strip().upper()
    return {
        "MANUAL_CALIBRATION": "calibração manual",
        "DYNATRACE": "calibração importada do Dynatrace",
        "UNKNOWN": "calibração não informada",
    }.get(raw, raw.replace("_", " ").casefold() if raw else "calibração não informada")


def _context(series: TemporalApdexSeries) -> str:
    if series.kind == "NAVIGATION":
        return (
            f"Limiar de satisfação: {_fmt(series.threshold_seconds, 3)} s · "
            f"limiar de frustração: {_fmt(series.frustrated_threshold_seconds, 3)} s"
        )
    error_policy = "sim" if series.errors_affect_apdex else "não"
    return (
        f"Métrica principal: {escape(_kpm_label(series.kpm))} · "
        f"Satisfeito abaixo de {_fmt(series.threshold_seconds, 3)} s · "
        f"Frustrado acima de {_fmt(series.frustrated_threshold_seconds, 3)} s · "
        f"erros afetam o Apdex: {error_policy}"
    )


def _context_note_label(series: TemporalApdexSeries) -> str:
    if series.kind == "NAVIGATION":
        return "Navegação em contexto novo por amostra, com cache local desabilitado."
    raw = str(series.context_note or "")
    calibration = ""
    if "calibração=" in raw:
        calibration = raw.split("calibração=", 1)[-1].split(";", 1)[0]
    parts = [_calibration_label(calibration)]
    if "device_mix=" in raw:
        encoded = raw.split("device_mix=", 1)[-1].split(";", 1)[0]
        try:
            mix = json.loads(encoded)
        except (TypeError, ValueError, json.JSONDecodeError):
            mix = None
        if isinstance(mix, dict):
            labels = {
                "mobile": "dispositivo móvel",
                "desktop": "desktop",
                "tablet": "tablet",
            }
            rendered = ", ".join(
                f"{labels.get(str(key).casefold(), str(key))}: {value}"
                for key, value in mix.items()
            )
            if rendered:
                parts.append("distribuição de dispositivos: " + rendered)
    return " · ".join(part for part in parts if part)


def render_temporal_apdex(series: tuple[TemporalApdexSeries, ...]) -> str:
    if not series:
        return ""
    rows: list[str] = []
    details: list[str] = []
    for item in series:
        temporal_label = "série temporal" if item.audits >= 3 else "dois marcos" if item.audits == 2 else "um marco"
        rows.append(
            "<tr>"
            f"<td>{escape(_kind_label(item.kind))}</td>"
            f"<td><code>{escape(item.url)}</code></td>"
            f"<td>{escape(_device_label(item.device))}</td>"
            f"<td>{_apdex_result_html(item.apdex_score)}</td>"
            f"<td>{item.valid_samples}</td><td>{item.invalid_samples}</td>"
            f"<td>{item.audits}</td><td>{escape(temporal_label)}</td>"
            f"<td>{_fmt(item.duration_p95_ms, 1)} ms</td>"
            "</tr>"
        )
        limitation = f"<p class='notice warning'>{escape(item.limitation)}</p>" if item.limitation else ""
        details.append(
            f"""
            <details class='details temporal-apdex-series'>
              <summary>{escape(_kind_label(item.kind))} · {escape(_device_label(item.device))} · {escape(item.url)}</summary>
              <div class='metric-grid'>
                <div><small>Apdex do período</small>{_apdex_result_html(item.apdex_score)}</div>
                <div><small>AUDs comparáveis</small><strong>{item.audits}</strong></div>
                <div><small>Amostras válidas</small><strong>{item.valid_samples}</strong></div>
                <div><small>Amostras com duração da métrica principal</small><strong>{item.samples_with_duration}</strong></div>
                <div><small>Satisfeitas / Toleráveis / Frustradas</small><strong>{item.satisfied_count} / {item.tolerating_count} / {item.frustrated_count}</strong></div>
                <div><small>Perfil</small><strong>{escape(_profile_label(item.profile_id))}</strong></div>
              </div>
              <p class='subtle'><strong>Contexto comparável:</strong> {_context(item)} · {_pacing_label(item.pacing)} · {_context_note_label(item)}</p>
              <div class='table-wrap'><table><thead><tr><th>Métrica do pool bruto</th><th>Valor</th></tr></thead><tbody>
                <tr><td>Média</td><td>{_fmt(item.duration_mean_ms, 1)} ms</td></tr>
                <tr><td>Mediana / p50</td><td>{_fmt(item.duration_median_ms, 1)} ms</td></tr>
                <tr><td>p75</td><td>{_fmt(item.duration_p75_ms, 1)} ms</td></tr>
                <tr><td>p90</td><td>{_fmt(item.duration_p90_ms, 1)} ms</td></tr>
                <tr><td>p95</td><td>{_fmt(item.duration_p95_ms, 1)} ms</td></tr>
                <tr><td>p99</td><td>{_fmt(item.duration_p99_ms, 1)} ms</td></tr>
                <tr><td>Mínimo / Máximo</td><td>{_fmt(item.duration_min_ms, 1)} / {_fmt(item.duration_max_ms, 1)} ms</td></tr>
                <tr><td>Desvio-padrão</td><td>{_fmt(item.duration_stddev_ms, 1)} ms</td></tr>
                <tr><td>Coeficiente de variação</td><td>{_fmt(item.duration_cv * 100.0, 1) + '%' if item.duration_cv is not None else '-'}</td></tr>
              </tbody></table></div>
              {limitation}
            </details>
            """
        )
    return f"""
    <section id='apdex'><h2>Apdex sintético no período</h2>
      <p>O consolidado recalcula o Apdex do período pela soma das contagens <strong>Satisfeitas, Toleráveis e Frustradas</strong> das execuções comparáveis. Percentis, média, dispersão e coeficiente de variação são recalculados a partir do <strong>conjunto bruto de amostras</strong>; não é feita média de p95/p99 de execuções individuais.</p>
      <p class='notice info'><strong>Comparabilidade:</strong> séries são separadas por URL, tipo de Apdex, dispositivo, tarefa ou métrica principal, perfil, limiares, política de erros/sessão e parâmetros de execução relevantes. Uma mudança nesses elementos cria outra série em vez de contaminar o período.</p>
      <div class='table-wrap bounded'><table><thead><tr><th>Tipo</th><th>URL</th><th>Dispositivo</th><th>Apdex do período</th><th>Válidas</th><th>Inválidas</th><th>AUDs</th><th>Base</th><th>p95 do período</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
      {''.join(details)}
    </section>
    """


def augment_report(path: Path, series: tuple[TemporalApdexSeries, ...]) -> bool:
    """Replace only the consolidated Apdex section, preserving the rest of the HTML."""
    if not series or not path.is_file():
        return False
    html = path.read_text(encoding="utf-8")
    replacement = render_temporal_apdex(series)
    pattern = re.compile(r"<section\s+id=['\"]apdex['\"][^>]*>.*?</section>", re.DOTALL)
    rendered, count = pattern.subn(replacement, html, count=1)
    if count != 1:
        return False
    rendered = rendered.replace(
        "Apdex só é agregado entre perfil e T compatíveis.",
        "Apdex só é agregado entre contextos metodologicamente compatíveis; Navigation preserva T/4T e Experience preserva KPM, thresholds e políticas efetivas.",
    )
    rendered = rendered.replace(
        "<strong>Apdex:</strong> somente perfil e T compatíveis; o índice consolidado é ponderado pelo número de amostras válidas.",
        "<strong>Apdex:</strong> o índice do período é recalculado pelas contagens S/T/F de contextos compatíveis; a distribuição temporal usa o pool bruto por URL e contexto.",
    )
    if rendered != html:
        path.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def augment_manifest(path: Path, series: tuple[TemporalApdexSeries, ...]) -> bool:
    if not path.is_file():
        return False
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    policy = manifest.setdefault("aggregation_policy", {})
    policy["apdex_period_score"] = "sum_satisfied_tolerating_frustrated_per_exact_context"
    policy["apdex_period_distribution"] = "raw_sample_pool_per_url_exact_context"
    manifest["temporal_apdex"] = {
        "contract": TEMPORAL_APDEX_CONTRACT,
        "series_count": len(series),
        "series": [asdict(item) for item in series],
        "raw_samples_persisted_in_manifest": False,
        "source_policy": "read_only_AUD_audit_db",
    }
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return True