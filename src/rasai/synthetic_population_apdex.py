"""Stratified, weighted and reproducible Synthetic Population Apdex for CAT-07.

This is an additive mode over the existing Synthetic User Experience Apdex baseline.
It reuses the canonical Chromium gateway, CAT-07 classification semantics and runtime
profile presets. It never changes CAT-06, SCORE-GEO, the baseline CAT-07 formula or AI.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from rasai.domain import new_id
from rasai.m23_apdex_profiles import profile_from_presets
from rasai.persistence import AuditWorkspace
from rasai.synthetic_runtime_profiles import validate_preset

POPULATION_RUNTIME_VERSION = "SYNTHETIC-POPULATION-001"
WEIGHT_SOURCE_TYPES = {
    "RUM",
    "DYNATRACE_RUM",
    "ANALYTICS",
    "CRUX",
    "BENCHMARK",
    "RASAI_OPERATOR",
}
_ALLOWED_PROFILE_KEYS = {
    "population_profile_id",
    "profile_version",
    "weight_source",
    "weight_source_ref",
    "target_samples_per_page",
    "strata",
}
_ALLOWED_STRATUM_KEYS = {
    "stratum_id",
    "weight",
    "device",
    "client_profile_id",
    "hardware_profile_id",
    "network_profile_id",
    "session_mode",
}


@dataclass(frozen=True, slots=True)
class PopulationStratum:
    stratum_id: str
    weight: float
    device: str
    client_profile_id: str
    hardware_profile_id: str
    network_profile_id: str
    session_mode: str


@dataclass(frozen=True, slots=True)
class PopulationProfile:
    population_profile_id: str
    profile_version: str
    weight_source: str
    weight_source_ref: str | None
    target_samples_per_page: int
    strata: tuple[PopulationStratum, ...]


@dataclass(frozen=True, slots=True)
class StratumStatistics:
    stratum_id: str
    target_samples: int
    valid_samples: int
    invalid_samples: int
    satisfied_count: int
    tolerating_count: int
    frustrated_count: int
    apdex_score: float | None
    median_ms: float | None
    p75_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    values_ms: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class PopulationStatistics:
    status: str
    weighted_apdex: float | None
    observed_weight_percent: float
    satisfied_count: int
    tolerating_count: int
    frustrated_count: int
    weighted_satisfied_share: float | None
    weighted_tolerating_share: float | None
    weighted_frustrated_share: float | None
    median_ms: float | None
    p75_ms: float | None
    p90_ms: float | None
    p95_ms: float | None
    standard_error: float | None
    ci95_low: float | None
    ci95_high: float | None
    valid_samples: int
    invalid_samples: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier(value: Any, field: str) -> str:
    text = str(value or "").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._"
    if not text or len(text) > 96 or any(ch not in allowed for ch in text):
        raise ValueError(f"{field} deve usar 1..96 caracteres alfanuméricos, ponto, hífen ou underscore")
    return text


def _positive_int(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} deve ser inteiro >= 1") from exc
    if parsed < 1:
        raise ValueError(f"{field} deve ser inteiro >= 1")
    return parsed


def parse_population_profile(
    raw: str,
    *,
    expected_device: str,
    default_target_samples: int,
) -> PopulationProfile:
    """Validate the explicit population contract without consulting current defaults."""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Synthetic Population profile deve ser JSON válido") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Synthetic Population profile deve ser um objeto JSON")
    unknown = set(payload) - _ALLOWED_PROFILE_KEYS
    if unknown:
        raise ValueError("campos não suportados no Synthetic Population profile: " + ", ".join(sorted(unknown)))

    profile_id = _identifier(payload.get("population_profile_id"), "population_profile_id")
    profile_version = _identifier(payload.get("profile_version"), "profile_version")
    weight_source = str(payload.get("weight_source") or "").strip().upper()
    if weight_source not in WEIGHT_SOURCE_TYPES:
        raise ValueError("weight_source deve ser um de: " + ", ".join(sorted(WEIGHT_SOURCE_TYPES)))
    weight_source_ref = str(payload.get("weight_source_ref") or "").strip() or None
    if weight_source != "RASAI_OPERATOR" and not weight_source_ref:
        raise ValueError("weight_source_ref é obrigatório quando os pesos não são arbitrados pelo operador RASAi")

    target = _positive_int(
        payload.get("target_samples_per_page", default_target_samples),
        "target_samples_per_page",
    )
    items = payload.get("strata")
    if not isinstance(items, list) or len(items) < 2:
        raise ValueError("Synthetic Population exige pelo menos dois estratos explícitos")
    if target < len(items):
        raise ValueError("target_samples_per_page deve ser >= número de estratos")

    expected = str(expected_device or "").strip().upper()
    if expected not in {"MOBILE", "DESKTOP"}:
        raise ValueError("Synthetic Population V1 exige AUD com device MOBILE ou DESKTOP")

    strata: list[PopulationStratum] = []
    identifiers: set[str] = set()
    total_weight = 0.0
    for index, raw_item in enumerate(items, 1):
        if not isinstance(raw_item, Mapping):
            raise ValueError(f"strata[{index}] deve ser objeto JSON")
        unknown_item = set(raw_item) - _ALLOWED_STRATUM_KEYS
        if unknown_item:
            raise ValueError(
                f"campos não suportados em strata[{index}]: " + ", ".join(sorted(unknown_item))
            )
        stratum_id = _identifier(raw_item.get("stratum_id"), f"strata[{index}].stratum_id")
        if stratum_id in identifiers:
            raise ValueError(f"stratum_id duplicado: {stratum_id}")
        identifiers.add(stratum_id)
        try:
            weight = float(raw_item.get("weight"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"peso inválido em {stratum_id}") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"peso de {stratum_id} deve ser finito e > 0")
        device = str(raw_item.get("device") or "").strip().upper()
        if device != expected:
            raise ValueError(
                f"estrato {stratum_id} usa {device or '-'}; V1 deve manter o device {expected} congelado da AUD"
            )
        client = validate_preset("client", device, str(raw_item.get("client_profile_id") or ""))
        hardware = validate_preset("hardware", device, str(raw_item.get("hardware_profile_id") or ""))
        network = validate_preset("network", device, str(raw_item.get("network_profile_id") or ""))
        session = str(raw_item.get("session_mode") or "").strip().casefold()
        if session not in {"cold", "warm"}:
            raise ValueError(f"session_mode de {stratum_id} deve ser cold ou warm")
        strata.append(PopulationStratum(
            stratum_id=stratum_id,
            weight=weight,
            device=device,
            client_profile_id=client,
            hardware_profile_id=hardware,
            network_profile_id=network,
            session_mode=session,
        ))
        total_weight += weight
    if abs(total_weight - 100.0) > 1e-6:
        raise ValueError(f"pesos do Synthetic Population devem somar 100; recebido {total_weight:g}")

    allocation = allocate_population_samples(target, tuple(strata))
    if any(value < 1 for value in allocation.values()):
        raise ValueError("target insuficiente para representar todos os estratos")
    return PopulationProfile(
        population_profile_id=profile_id,
        profile_version=profile_version,
        weight_source=weight_source,
        weight_source_ref=weight_source_ref,
        target_samples_per_page=target,
        strata=tuple(strata),
    )


def allocate_population_samples(
    total: int,
    strata: Sequence[PopulationStratum],
) -> dict[str, int]:
    """Largest-remainder allocation with one guaranteed sample per explicit stratum."""
    if total < len(strata) or not strata:
        raise ValueError("total deve ser >= quantidade de estratos")
    remaining = total - len(strata)
    raw = {item.stratum_id: remaining * item.weight / 100.0 for item in strata}
    result = {item.stratum_id: 1 + int(math.floor(raw[item.stratum_id])) for item in strata}
    missing = total - sum(result.values())
    order = sorted(
        strata,
        key=lambda item: (-(raw[item.stratum_id] - math.floor(raw[item.stratum_id])), item.stratum_id),
    )
    for item in order[:missing]:
        result[item.stratum_id] += 1
    return result


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def stratum_statistics(
    stratum_id: str,
    target_samples: int,
    items: Sequence[Any],
) -> StratumStatistics:
    valid = [item for item in items if getattr(item, "classification", None) is not None]
    counts = {
        label: sum(getattr(item, "classification", None) == label for item in valid)
        for label in ("SATISFIED", "TOLERATING", "FRUSTRATED")
    }
    values = tuple(
        float(item.kpm_value_ms)
        for item in valid
        if getattr(item, "kpm_value_ms", None) is not None
        and math.isfinite(float(item.kpm_value_ms))
    )
    total = len(valid)
    score = (counts["SATISFIED"] + 0.5 * counts["TOLERATING"]) / total if total else None
    return StratumStatistics(
        stratum_id=stratum_id,
        target_samples=target_samples,
        valid_samples=total,
        invalid_samples=len(items) - total,
        satisfied_count=counts["SATISFIED"],
        tolerating_count=counts["TOLERATING"],
        frustrated_count=counts["FRUSTRATED"],
        apdex_score=round(score, 6) if score is not None else None,
        median_ms=_percentile(values, 0.50),
        p75_ms=_percentile(values, 0.75),
        p90_ms=_percentile(values, 0.90),
        p95_ms=_percentile(values, 0.95),
        values_ms=values,
    )


def _weighted_percentile(
    profile: PopulationProfile,
    statistics: Mapping[str, StratumStatistics],
    fraction: float,
) -> float | None:
    points: list[tuple[float, float]] = []
    total_weight = 0.0
    for stratum in profile.strata:
        stats = statistics[stratum.stratum_id]
        if not stats.values_ms:
            continue
        sample_weight = stratum.weight / len(stats.values_ms)
        for value in stats.values_ms:
            points.append((value, sample_weight))
            total_weight += sample_weight
    if not points or total_weight <= 0:
        return None
    points.sort(key=lambda item: item[0])
    threshold = total_weight * fraction
    cumulative = 0.0
    for value, weight in points:
        cumulative += weight
        if cumulative + 1e-12 >= threshold:
            return value
    return points[-1][0]


def aggregate_population_statistics(
    profile: PopulationProfile,
    statistics: Mapping[str, StratumStatistics],
) -> PopulationStatistics:
    observed_weight = sum(
        stratum.weight
        for stratum in profile.strata
        if statistics[stratum.stratum_id].valid_samples > 0
    )
    valid_total = sum(stats.valid_samples for stats in statistics.values())
    invalid_total = sum(stats.invalid_samples for stats in statistics.values())
    raw_satisfied = sum(stats.satisfied_count for stats in statistics.values())
    raw_tolerating = sum(stats.tolerating_count for stats in statistics.values())
    raw_frustrated = sum(stats.frustrated_count for stats in statistics.values())
    all_complete = all(
        statistics[stratum.stratum_id].valid_samples >= statistics[stratum.stratum_id].target_samples
        for stratum in profile.strata
    )
    status = "SUCCESS" if all_complete else ("PARTIAL" if valid_total else "UNAVAILABLE")

    if observed_weight <= 0:
        return PopulationStatistics(
            status, None, 0.0, raw_satisfied, raw_tolerating, raw_frustrated,
            None, None, None, None, None, None, None, None, None, None,
            valid_total, invalid_total,
        )

    weighted_score = weighted_s = weighted_t = weighted_f = 0.0
    variance_estimate = 0.0
    for stratum in profile.strata:
        stats = statistics[stratum.stratum_id]
        if stats.valid_samples <= 0 or stats.apdex_score is None:
            continue
        normalized_weight = stratum.weight / observed_weight
        n = stats.valid_samples
        weighted_score += normalized_weight * stats.apdex_score
        weighted_s += normalized_weight * stats.satisfied_count / n
        weighted_t += normalized_weight * stats.tolerating_count / n
        weighted_f += normalized_weight * stats.frustrated_count / n
        if n > 1:
            sum_x = stats.satisfied_count + 0.5 * stats.tolerating_count
            sum_x2 = stats.satisfied_count + 0.25 * stats.tolerating_count
            sample_variance = max((sum_x2 - (sum_x * sum_x) / n) / (n - 1), 0.0)
            variance_estimate += normalized_weight * normalized_weight * sample_variance / n
    standard_error = math.sqrt(variance_estimate)
    ci_low = max(0.0, weighted_score - 1.96 * standard_error)
    ci_high = min(1.0, weighted_score + 1.96 * standard_error)

    return PopulationStatistics(
        status=status,
        weighted_apdex=round(weighted_score, 6),
        observed_weight_percent=round(observed_weight, 6),
        satisfied_count=raw_satisfied,
        tolerating_count=raw_tolerating,
        frustrated_count=raw_frustrated,
        weighted_satisfied_share=round(weighted_s, 6),
        weighted_tolerating_share=round(weighted_t, 6),
        weighted_frustrated_share=round(weighted_f, 6),
        median_ms=_weighted_percentile(profile, statistics, 0.50),
        p75_ms=_weighted_percentile(profile, statistics, 0.75),
        p90_ms=_weighted_percentile(profile, statistics, 0.90),
        p95_ms=_weighted_percentile(profile, statistics, 0.95),
        standard_error=standard_error,
        ci95_low=ci_low,
        ci95_high=ci_high,
        valid_samples=valid_total,
        invalid_samples=invalid_total,
    )


class SyntheticPopulationPersistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self.connection = sqlite3.connect(workspace.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "SyntheticPopulationPersistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS synthetic_population_apdex_runs (
                    audit_id TEXT PRIMARY KEY REFERENCES audits(audit_id) ON DELETE CASCADE,
                    population_profile_id TEXT NOT NULL,
                    profile_version TEXT NOT NULL,
                    runtime_version TEXT NOT NULL,
                    weight_source TEXT NOT NULL,
                    weight_source_ref TEXT,
                    device TEXT NOT NULL,
                    target_samples_per_page INTEGER NOT NULL,
                    kpm TEXT NOT NULL,
                    measurement_contract_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    configuration TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS synthetic_population_apdex_samples (
                    sample_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    stratum_id TEXT NOT NULL,
                    run_index INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    classification TEXT,
                    kpm_value_ms REAL,
                    error_forced_frustrated INTEGER NOT NULL,
                    captured_at TEXT NOT NULL,
                    UNIQUE(audit_id,page_id,stratum_id,run_index)
                );
                CREATE TABLE IF NOT EXISTS synthetic_population_apdex_strata (
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    stratum_id TEXT NOT NULL,
                    weight REAL NOT NULL,
                    device TEXT NOT NULL,
                    client_profile_id TEXT NOT NULL,
                    hardware_profile_id TEXT NOT NULL,
                    network_profile_id TEXT NOT NULL,
                    session_mode TEXT NOT NULL,
                    target_samples INTEGER NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    invalid_samples INTEGER NOT NULL,
                    satisfied_count INTEGER NOT NULL,
                    tolerating_count INTEGER NOT NULL,
                    frustrated_count INTEGER NOT NULL,
                    apdex_score REAL,
                    median_ms REAL,
                    p75_ms REAL,
                    p90_ms REAL,
                    p95_ms REAL,
                    calculated_at TEXT NOT NULL,
                    PRIMARY KEY(audit_id,page_id,stratum_id)
                );
                CREATE TABLE IF NOT EXISTS synthetic_population_apdex_summaries (
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    page_id TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    status TEXT NOT NULL,
                    weighted_apdex REAL,
                    observed_weight_percent REAL NOT NULL,
                    valid_samples INTEGER NOT NULL,
                    invalid_samples INTEGER NOT NULL,
                    satisfied_count INTEGER NOT NULL,
                    tolerating_count INTEGER NOT NULL,
                    frustrated_count INTEGER NOT NULL,
                    weighted_satisfied_share REAL,
                    weighted_tolerating_share REAL,
                    weighted_frustrated_share REAL,
                    median_ms REAL,
                    p75_ms REAL,
                    p90_ms REAL,
                    p95_ms REAL,
                    standard_error REAL,
                    ci95_low REAL,
                    ci95_high REAL,
                    calculated_at TEXT NOT NULL,
                    PRIMARY KEY(audit_id,page_id)
                );
                """
            )

    def clear_audit(self, audit_id: str) -> None:
        with self.connection:
            for table in (
                "synthetic_population_apdex_samples",
                "synthetic_population_apdex_strata",
                "synthetic_population_apdex_summaries",
                "synthetic_population_apdex_runs",
            ):
                self.connection.execute(f"DELETE FROM {table} WHERE audit_id=?", (audit_id,))

    def add_sample(self, audit_id: str, page_id: str, stratum_id: str, item: Any) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO synthetic_population_apdex_samples(
                    sample_id,audit_id,page_id,stratum_id,run_index,status,classification,
                    kpm_value_ms,error_forced_frustrated,captured_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("PXA"), audit_id, page_id, stratum_id, int(item.run_index),
                    str(item.measurement.status), item.classification, item.kpm_value_ms,
                    int(bool(item.error_forced)), str(item.captured_at),
                ),
            )

    def upsert_stratum(
        self,
        audit_id: str,
        page_id: str,
        url: str,
        stratum: PopulationStratum,
        stats: StratumStatistics,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT OR REPLACE INTO synthetic_population_apdex_strata(
                    audit_id,page_id,url,stratum_id,weight,device,client_profile_id,
                    hardware_profile_id,network_profile_id,session_mode,target_samples,
                    valid_samples,invalid_samples,satisfied_count,tolerating_count,
                    frustrated_count,apdex_score,median_ms,p75_ms,p90_ms,p95_ms,calculated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,page_id,url,stratum.stratum_id,stratum.weight,stratum.device,
                    stratum.client_profile_id,stratum.hardware_profile_id,stratum.network_profile_id,
                    stratum.session_mode,stats.target_samples,stats.valid_samples,stats.invalid_samples,
                    stats.satisfied_count,stats.tolerating_count,stats.frustrated_count,
                    stats.apdex_score,stats.median_ms,stats.p75_ms,stats.p90_ms,stats.p95_ms,_utc_now(),
                ),
            )

    def upsert_summary(
        self,
        audit_id: str,
        page_id: str,
        url: str,
        summary: PopulationStatistics,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT OR REPLACE INTO synthetic_population_apdex_summaries(
                    audit_id,page_id,url,status,weighted_apdex,observed_weight_percent,
                    valid_samples,invalid_samples,satisfied_count,tolerating_count,frustrated_count,
                    weighted_satisfied_share,weighted_tolerating_share,weighted_frustrated_share,
                    median_ms,p75_ms,p90_ms,p95_ms,standard_error,ci95_low,ci95_high,calculated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,page_id,url,summary.status,summary.weighted_apdex,
                    summary.observed_weight_percent,summary.valid_samples,summary.invalid_samples,
                    summary.satisfied_count,summary.tolerating_count,summary.frustrated_count,
                    summary.weighted_satisfied_share,summary.weighted_tolerating_share,
                    summary.weighted_frustrated_share,summary.median_ms,summary.p75_ms,
                    summary.p90_ms,summary.p95_ms,summary.standard_error,summary.ci95_low,
                    summary.ci95_high,_utc_now(),
                ),
            )

    def upsert_run(
        self,
        audit_id: str,
        profile: PopulationProfile,
        *,
        device: str,
        kpm: str,
        measurement_contract_version: str,
        status: str,
        configuration: Mapping[str, Any],
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT OR REPLACE INTO synthetic_population_apdex_runs(
                    audit_id,population_profile_id,profile_version,runtime_version,weight_source,
                    weight_source_ref,device,target_samples_per_page,kpm,
                    measurement_contract_version,status,configuration,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,profile.population_profile_id,profile.profile_version,
                    POPULATION_RUNTIME_VERSION,profile.weight_source,profile.weight_source_ref,
                    device,profile.target_samples_per_page,kpm,measurement_contract_version,
                    status,json.dumps(dict(configuration),ensure_ascii=False,separators=(",",":"),sort_keys=True),
                    _utc_now(),
                ),
            )


def execute_population_apdex(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    base_config: Any,
    calibration: Any,
    profile_json: str,
    gateway_factory: Callable[[], Any] | None = None,
) -> str:
    """Execute the additive CAT-07 population without touching baseline M25 tables."""
    from rasai import m25_apdex_experience as m25

    mix = base_config.device_mix_dict()
    if len(mix) != 1:
        raise ValueError("Synthetic Population V1 exige exatamente um device canônico na AUD")
    expected_device = next(iter(mix))
    population = parse_population_profile(
        profile_json,
        expected_device=expected_device,
        default_target_samples=base_config.target_samples_per_page,
    )
    allocation = allocate_population_samples(population.target_samples_per_page, population.strata)
    attempt_ratio = max(
        float(base_config.max_attempts_per_page) / float(base_config.target_samples_per_page),
        1.0,
    )
    pages = m25._selected_pages(workspace, audit_id, base_config.max_pages)
    pacer = m25._OriginPacer(base_config.delay_seconds)
    page_statuses: list[str] = []

    with SyntheticPopulationPersistence(workspace) as store:
        store.clear_audit(audit_id)
        for page_index, page in enumerate(pages, 1):
            page_id = str(page["page_id"])
            url = str(page["url"])
            statistics: dict[str, StratumStatistics] = {}
            for stratum in population.strata:
                target = allocation[stratum.stratum_id]
                max_attempts = max(target, int(math.ceil(target * attempt_ratio)))
                runtime_profile = profile_from_presets(
                    device=stratum.device,
                    client_profile_id=stratum.client_profile_id,
                    hardware_profile_id=stratum.hardware_profile_id,
                    network_profile_id=stratum.network_profile_id,
                )
                stratum_config = replace(
                    base_config,
                    session_mode=stratum.session_mode,
                    population_profile_json=None,
                )
                if gateway_factory is None:
                    base_factory = lambda mode=stratum.session_mode: m25.PlaywrightSyntheticUxGateway(session_mode=mode)
                else:
                    base_factory = gateway_factory
                factory = lambda: m25._apply_gateway_capture_policy(base_factory(), calibration)
                shared = factory() if stratum_config.concurrency == 1 else None
                try:
                    items = m25._measure_device(
                        audit_id=audit_id,
                        workspace=workspace,
                        url=url,
                        device=stratum.device,
                        target=target,
                        max_attempts=max_attempts,
                        page_index=page_index,
                        page_total=len(pages),
                        calibration=calibration,
                        config=stratum_config,
                        pacer=pacer,
                        shared_gateway=shared,
                        factory=factory,
                        profile=runtime_profile,
                    )
                finally:
                    if shared is not None:
                        shared.close()
                stats = stratum_statistics(stratum.stratum_id, target, items)
                statistics[stratum.stratum_id] = stats
                for item in items:
                    store.add_sample(audit_id, page_id, stratum.stratum_id, item)
                store.upsert_stratum(audit_id, page_id, url, stratum, stats)

            summary = aggregate_population_statistics(population, statistics)
            store.upsert_summary(audit_id, page_id, url, summary)
            page_statuses.append(summary.status)

        if not pages:
            status = "NO_PAGES"
        elif page_statuses and all(value == "SUCCESS" for value in page_statuses):
            status = "SUCCESS"
        elif any(value in {"SUCCESS", "PARTIAL"} for value in page_statuses):
            status = "PARTIAL"
        else:
            status = "UNAVAILABLE"
        store.upsert_run(
            audit_id,
            population,
            device=expected_device,
            kpm=calibration.kpm,
            measurement_contract_version=m25.USER_ACTION_DURATION_BOUNDARY_VERSION,
            status=status,
            configuration={
                "population_runtime_version": POPULATION_RUNTIME_VERSION,
                "population_profile": {
                    "population_profile_id": population.population_profile_id,
                    "profile_version": population.profile_version,
                    "weight_source": population.weight_source,
                    "weight_source_ref": population.weight_source_ref,
                    "target_samples_per_page": population.target_samples_per_page,
                    "strata": [
                        {
                            "stratum_id": item.stratum_id,
                            "weight": item.weight,
                            "device": item.device,
                            "client_profile_id": item.client_profile_id,
                            "hardware_profile_id": item.hardware_profile_id,
                            "network_profile_id": item.network_profile_id,
                            "session_mode": item.session_mode,
                            "target_samples": allocation[item.stratum_id],
                        }
                        for item in population.strata
                    ],
                },
                "execution_policy": {
                    "concurrency": base_config.concurrency,
                    "delay_seconds": base_config.delay_seconds,
                    "randomization": "NONE",
                    "geography": "NOT_MODELED",
                    "browser_geolocation": "NOT_USED_AS_NETWORK_GEOGRAPHY",
                },
            },
        )
    return status


def read_population_projection(database: str | Path, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(Path(database))
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='synthetic_population_apdex_runs'"
        ).fetchone()
        if not exists:
            return None
        run = connection.execute(
            "SELECT * FROM synthetic_population_apdex_runs WHERE audit_id=?", (audit_id,)
        ).fetchone()
        if run is None:
            return None
        summaries = connection.execute(
            "SELECT * FROM synthetic_population_apdex_summaries WHERE audit_id=? ORDER BY url,page_id",
            (audit_id,),
        ).fetchall()
        strata = connection.execute(
            "SELECT * FROM synthetic_population_apdex_strata WHERE audit_id=? ORDER BY url,stratum_id",
            (audit_id,),
        ).fetchall()
        return {
            "run": dict(run),
            "summaries": [dict(row) for row in summaries],
            "strata": [dict(row) for row in strata],
        }
    finally:
        connection.close()
