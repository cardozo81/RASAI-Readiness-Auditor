"""M23 - medição controlada de Synthetic Navigation Apdex.

O índice é calculado somente a partir de tempos repetidos de uma Task explícita.
Não é inferido de Lighthouse, Core Web Vitals, PageSpeed ou IA. A baseline usa
perfis CPU/rede determinísticos e versionados, BrowserContext novo por amostra,
cache desabilitado, pacing configurável e alvo de amostras VÁLIDAS por contexto.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
import sqlite3
import statistics
import threading
import time
from typing import Any, Callable

from rasai.domain import DeviceContext, new_id
from rasai.m23_apdex_profiles import (
    DESKTOP_STANDARD_PROFILE,
    MOBILE_STANDARD_PROFILE,
    PROFILE_VERSION,
    NavigationMeasurement,
    PlaywrightSyntheticNavigationGateway,
    SyntheticNavigationGateway,
    SyntheticProfile,
    static_host_environment,
)
from rasai.m23_persistence import (
    M23Persistence,
    SyntheticApdexRun,
    SyntheticApdexSample,
    SyntheticApdexSummary,
)
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace

TASK_NAVIGATION_LOAD = "NAVIGATION_LOAD"
NORMAL_GROUP_MINIMUM = 100
MAX_CONCURRENCY = 2


@dataclass(frozen=True, slots=True)
class SyntheticApdexConfig:
    enabled: bool = False
    threshold_seconds: float | None = None
    target_valid_samples: int = NORMAL_GROUP_MINIMUM
    max_attempts_per_context: int = 125
    max_pages: int = 1
    timeout_seconds: float = 45.0
    delay_seconds: float = 1.0
    concurrency: int = 1
    mobile_profile: SyntheticProfile = MOBILE_STANDARD_PROFILE
    desktop_profile: SyntheticProfile = DESKTOP_STANDARD_PROFILE

    def validate(self) -> "SyntheticApdexConfig":
        if not self.enabled:
            return replace(self, threshold_seconds=None)
        if self.threshold_seconds is None or not math.isfinite(self.threshold_seconds) or self.threshold_seconds <= 0:
            raise ValueError("Synthetic Apdex exige threshold T positivo e explícito")
        _validate_threshold_resolution(self.threshold_seconds)
        if self.target_valid_samples < 1:
            raise ValueError("target_valid_samples deve ser >= 1")
        if self.max_attempts_per_context < self.target_valid_samples:
            raise ValueError("max_attempts_per_context deve ser >= target_valid_samples")
        if self.max_pages < 0:
            raise ValueError("max_pages deve ser >= 0; 0 significa todas as páginas auditadas")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 4.0 * self.threshold_seconds:
            raise ValueError("timeout_seconds deve ser maior que 4*T")
        if not math.isfinite(self.delay_seconds) or self.delay_seconds < 0:
            raise ValueError("delay_seconds deve ser finito e >= 0")
        if self.concurrency < 1 or self.concurrency > MAX_CONCURRENCY:
            raise ValueError(f"concurrency deve estar entre 1 e {MAX_CONCURRENCY}")
        self.mobile_profile.validate()
        self.desktop_profile.validate()
        return self


@dataclass(frozen=True, slots=True)
class M23ExecutionResult:
    enabled: bool
    status: str
    pages_considered: int
    contexts_considered: int
    attempted_samples: int
    valid_samples: int
    invalid_samples: int
    complete_contexts: int
    small_group_summaries: int


@dataclass(frozen=True, slots=True)
class _MeasuredSample:
    run_index: int
    measurement: NavigationMeasurement
    classification: str | None


class _OriginPacer:
    """Garante intervalo mínimo determinístico entre INÍCIOS de amostras."""

    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
        self._lock = threading.Lock()
        self._next_start = 0.0

    def wait_for_slot(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(self._next_start - now, 0.0)
            if delay:
                time.sleep(delay)
            self._next_start = time.monotonic() + self.delay_seconds


def execute_m23_apdex(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    config: SyntheticApdexConfig | None = None,
    gateway: SyntheticNavigationGateway | None = None,
    gateway_factory: Callable[[], SyntheticNavigationGateway] | None = None,
) -> M23ExecutionResult:
    cfg = (config or SyntheticApdexConfig()).validate()
    factory = gateway_factory or PlaywrightSyntheticNavigationGateway
    configuration = _configuration(cfg)

    try_append_operational_event(
        workspace,
        "M23_STARTED",
        audit_id=audit_id,
        enabled=cfg.enabled,
        task_id=TASK_NAVIGATION_LOAD,
        threshold_seconds=cfg.threshold_seconds,
        target_valid_samples=cfg.target_valid_samples,
        max_attempts_per_context=cfg.max_attempts_per_context,
        max_pages=cfg.max_pages,
        timeout_seconds=cfg.timeout_seconds,
        delay_seconds=cfg.delay_seconds,
        concurrency=cfg.concurrency,
        ai_calls=0,
        external_measurement_apis=0,
    )

    if not cfg.enabled:
        with M23Persistence(workspace) as store:
            store.upsert_run(
                SyntheticApdexRun(
                    audit_id=audit_id,
                    enabled=False,
                    status="DISABLED",
                    task_id=TASK_NAVIGATION_LOAD,
                    threshold_seconds=None,
                    frustration_seconds=None,
                    target_valid_samples=cfg.target_valid_samples,
                    max_attempts_per_context=cfg.max_attempts_per_context,
                    page_limit=cfg.max_pages,
                    pages_considered=0,
                    contexts_considered=0,
                    attempted_samples=0,
                    valid_samples=0,
                    invalid_samples=0,
                    delay_seconds=cfg.delay_seconds,
                    concurrency=cfg.concurrency,
                    configuration=configuration,
                    host_environment=static_host_environment(),
                    reason="SYNTHETIC_APDEX_DISABLED",
                    updated_at=_utc_now(),
                )
            )
        try_append_operational_event(workspace, "M23_COMPLETED", audit_id=audit_id, status="DISABLED")
        return M23ExecutionResult(False, "DISABLED", 0, 0, 0, 0, 0, 0, 0)

    if gateway is not None and cfg.concurrency != 1:
        raise ValueError("gateway injetado somente é suportado com concurrency=1")

    contexts = _selected_contexts(workspace, audit_id, cfg.max_pages)
    threshold = float(cfg.threshold_seconds)
    pacer = _OriginPacer(cfg.delay_seconds)

    shared_gateway = gateway
    owned_shared = False
    if shared_gateway is None and cfg.concurrency == 1:
        shared_gateway = factory()
        owned_shared = True

    if shared_gateway is not None:
        host_environment = shared_gateway.environment()
    else:
        probe = factory()
        try:
            host_environment = probe.environment()
        finally:
            probe.close()

    attempted_total = valid_total = invalid_total = 0
    complete_contexts = target_met_contexts = small_groups = 0
    try:
        with M23Persistence(workspace) as store:
            for context_index, row in enumerate(contexts, start=1):
                outcome = _measure_context(
                    audit_id=audit_id,
                    workspace=workspace,
                    row=row,
                    context_index=context_index,
                    context_total=len(contexts),
                    threshold=threshold,
                    config=cfg,
                    pacer=pacer,
                    shared_gateway=shared_gateway,
                    factory=factory,
                )
                for sample in outcome["samples"]:
                    store.add_sample(sample)
                summary = outcome["summary"]
                store.upsert_summary(summary)
                attempted_total += int(outcome["attempted"])
                valid_total += int(outcome["valid"])
                invalid_total += int(outcome["invalid"])
                if summary.final_group:
                    complete_contexts += 1
                if summary.valid_samples >= cfg.target_valid_samples:
                    target_met_contexts += 1
                if summary.small_group and summary.valid_samples:
                    small_groups += 1

            status, reason = _run_status(
                context_count=len(contexts),
                final_contexts=complete_contexts,
                target_met_contexts=target_met_contexts,
                small_groups=small_groups,
                valid_total=valid_total,
                invalid_total=invalid_total,
            )

            pages_considered = len({str(row["page_id"]) for row in contexts})
            store.upsert_run(
                SyntheticApdexRun(
                    audit_id=audit_id,
                    enabled=True,
                    status=status,
                    task_id=TASK_NAVIGATION_LOAD,
                    threshold_seconds=threshold,
                    frustration_seconds=4.0 * threshold,
                    target_valid_samples=cfg.target_valid_samples,
                    max_attempts_per_context=cfg.max_attempts_per_context,
                    page_limit=cfg.max_pages,
                    pages_considered=pages_considered,
                    contexts_considered=len(contexts),
                    attempted_samples=attempted_total,
                    valid_samples=valid_total,
                    invalid_samples=invalid_total,
                    delay_seconds=cfg.delay_seconds,
                    concurrency=cfg.concurrency,
                    configuration=configuration,
                    host_environment=host_environment,
                    reason=reason,
                    updated_at=_utc_now(),
                )
            )
    finally:
        if owned_shared and shared_gateway is not None:
            shared_gateway.close()

    try_append_operational_event(
        workspace,
        "M23_COMPLETED",
        audit_id=audit_id,
        status=status,
        attempted_samples=attempted_total,
        valid_samples=valid_total,
        invalid_samples=invalid_total,
        complete_contexts=complete_contexts,
        contexts_considered=len(contexts),
    )
    return M23ExecutionResult(
        True,
        status,
        len({str(row["page_id"]) for row in contexts}),
        len(contexts),
        attempted_total,
        valid_total,
        invalid_total,
        complete_contexts,
        small_groups,
    )


def _run_status(
    *,
    context_count: int,
    final_contexts: int,
    target_met_contexts: int,
    small_groups: int,
    valid_total: int,
    invalid_total: int,
) -> tuple[str, str | None]:
    if context_count == 0:
        return "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
    if final_contexts == context_count and invalid_total == 0:
        return "SUCCESS", None
    if valid_total == 0:
        return "UNAVAILABLE", "NO_VALID_SYNTHETIC_SAMPLES"
    if target_met_contexts == context_count and invalid_total == 0 and small_groups:
        return "PARTIAL", "SMALL_GROUP_BELOW_NORMAL_MINIMUM"
    return "PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE_OR_INVALID"


def _measure_context(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    row: dict[str, Any],
    context_index: int,
    context_total: int,
    threshold: float,
    config: SyntheticApdexConfig,
    pacer: _OriginPacer,
    shared_gateway: SyntheticNavigationGateway | None,
    factory: Callable[[], SyntheticNavigationGateway],
) -> dict[str, Any]:
    device = DeviceContext(str(row["device"]))
    profile = config.mobile_profile if device is DeviceContext.MOBILE else config.desktop_profile
    url = str(row["final_url"] or row["normalized_url"])
    samples: list[_MeasuredSample] = []

    if config.concurrency == 1:
        assert shared_gateway is not None
        for run_index in range(1, config.max_attempts_per_context + 1):
            if _valid_count(samples) >= config.target_valid_samples:
                break
            pacer.wait_for_slot()
            measurement = shared_gateway.measure(url=url, profile=profile, timeout_seconds=config.timeout_seconds)
            item = _sample(run_index, measurement, threshold)
            samples.append(item)
            _log_progress(
                workspace=workspace,
                audit_id=audit_id,
                url=url,
                device=device,
                context_index=context_index,
                context_total=context_total,
                config=config,
                samples=samples,
                item=item,
            )
    else:
        samples = _measure_context_parallel(
            audit_id=audit_id,
            workspace=workspace,
            url=url,
            device=device,
            profile=profile,
            context_index=context_index,
            context_total=context_total,
            threshold=threshold,
            config=config,
            pacer=pacer,
            factory=factory,
        )

    persisted = tuple(
        SyntheticApdexSample(
            sample_id=new_id("APX"),
            audit_id=audit_id,
            page_id=str(row["page_id"]),
            snapshot_id=str(row["snapshot_id"]),
            device=device.value,
            url=url,
            run_index=item.run_index,
            task_id=TASK_NAVIGATION_LOAD,
            profile_id=profile.profile_id,
            profile_version=PROFILE_VERSION,
            status=item.measurement.status,
            classification=item.classification,
            duration_ms=item.measurement.duration_ms,
            http_status=item.measurement.http_status,
            final_url=item.measurement.final_url,
            error_code=item.measurement.error_code,
            error_message=_bounded(item.measurement.error_message, 256),
            cpu_method=item.measurement.cpu_method,
            network_method=item.measurement.network_method,
            cache_policy="COLD_CONTEXT",
            captured_at=_utc_now(),
        )
        for item in sorted(samples, key=lambda value: value.run_index)
    )
    summary = _summary(
        audit_id=audit_id,
        page_id=str(row["page_id"]),
        device=device.value,
        url=url,
        profile=profile,
        threshold=threshold,
        target=config.target_valid_samples,
        samples=sorted(samples, key=lambda value: value.run_index),
    )
    return {
        "attempted": len(samples),
        "valid": _valid_count(samples),
        "invalid": sum(item.classification is None for item in samples),
        "samples": persisted,
        "summary": summary,
    }


def _measure_context_parallel(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: DeviceContext,
    profile: SyntheticProfile,
    context_index: int,
    context_total: int,
    threshold: float,
    config: SyntheticApdexConfig,
    pacer: _OriginPacer,
    factory: Callable[[], SyntheticNavigationGateway],
) -> list[_MeasuredSample]:
    thread_state = threading.local()
    created_gateways: list[SyntheticNavigationGateway] = []
    created_lock = threading.Lock()

    def gateway_for_thread() -> SyntheticNavigationGateway:
        runner = getattr(thread_state, "gateway", None)
        if runner is None:
            runner = factory()
            thread_state.gateway = runner
            with created_lock:
                created_gateways.append(runner)
        return runner

    def run_one(run_index: int) -> _MeasuredSample:
        pacer.wait_for_slot()
        measurement = gateway_for_thread().measure(
            url=url,
            profile=profile,
            timeout_seconds=config.timeout_seconds,
        )
        return _sample(run_index, measurement, threshold)

    results: list[_MeasuredSample] = []
    next_index = 1
    futures: dict[Future[_MeasuredSample], int] = {}
    try:
        with ThreadPoolExecutor(max_workers=config.concurrency, thread_name_prefix="rasai-apdex") as executor:
            while next_index <= config.max_attempts_per_context and len(futures) < config.concurrency:
                future = executor.submit(run_one, next_index)
                futures[future] = next_index
                next_index += 1

            while futures:
                done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    futures.pop(future, None)
                    item = future.result()
                    results.append(item)
                    _log_progress(
                        workspace=workspace,
                        audit_id=audit_id,
                        url=url,
                        device=device,
                        context_index=context_index,
                        context_total=context_total,
                        config=config,
                        samples=results,
                        item=item,
                    )
                if _valid_count(results) >= config.target_valid_samples:
                    for future in futures:
                        future.cancel()
                    break
                while next_index <= config.max_attempts_per_context and len(futures) < config.concurrency:
                    future = executor.submit(run_one, next_index)
                    futures[future] = next_index
                    next_index += 1
    finally:
        # ThreadPool already joined; closing Chromium/Playwright after all worker
        # activity prevents context/session reuse while keeping worker browsers bounded.
        for runner in created_gateways:
            try:
                runner.close()
            except Exception:
                pass
    return results


def _sample(run_index: int, measurement: NavigationMeasurement, threshold: float) -> _MeasuredSample:
    return _MeasuredSample(run_index, measurement, _classification(measurement, threshold))


def _classification(item: NavigationMeasurement, threshold_seconds: float) -> str | None:
    if not item.profile_applied or item.duration_ms is None:
        return None
    if item.status in {"APPLICATION_ERROR", "TIMEOUT", "NAVIGATION_ERROR"}:
        return "FRUSTRATED"
    seconds = item.duration_ms / 1000.0
    if seconds <= threshold_seconds:
        return "SATISFIED"
    if seconds <= 4.0 * threshold_seconds:
        return "TOLERATING"
    return "FRUSTRATED"


def _summary(
    *,
    audit_id: str,
    page_id: str,
    device: str,
    url: str,
    profile: SyntheticProfile,
    threshold: float,
    target: int,
    samples: list[_MeasuredSample],
) -> SyntheticApdexSummary:
    valid_items = [item for item in samples if item.classification is not None]
    durations = [int(item.measurement.duration_ms or 0) for item in valid_items]
    counts = {
        name: sum(item.classification == name for item in valid_items)
        for name in ("SATISFIED", "TOLERATING", "FRUSTRATED")
    }
    statuses = {
        name: sum(item.measurement.status == name for item in valid_items)
        for name in ("SUCCESS", "APPLICATION_ERROR", "TIMEOUT", "NAVIGATION_ERROR")
    }
    total = len(valid_items)
    score = (counts["SATISFIED"] + 0.5 * counts["TOLERATING"]) / total if total else None
    mean = statistics.fmean(durations) if durations else None
    stddev = statistics.pstdev(durations) if len(durations) > 1 else (0.0 if durations else None)
    cv = (stddev / mean) if mean not in (None, 0) and stddev is not None else None
    split = max(len(durations) // 2, 1) if durations else 0
    first = statistics.fmean(durations[:split]) if durations else None
    second = statistics.fmean(durations[split:]) if len(durations) > split else first
    trend = ((second - first) / first * 100.0) if first not in (None, 0) and second is not None else None
    ordered = sorted(durations)
    return SyntheticApdexSummary(
        summary_id=new_id("APS"),
        audit_id=audit_id,
        page_id=page_id,
        device=device,
        url=url,
        task_id=TASK_NAVIGATION_LOAD,
        profile_id=profile.profile_id,
        threshold_seconds=threshold,
        frustration_seconds=4.0 * threshold,
        valid_samples=total,
        invalid_samples=sum(item.classification is None for item in samples),
        satisfied_count=counts["SATISFIED"],
        tolerating_count=counts["TOLERATING"],
        frustrated_count=counts["FRUSTRATED"],
        success_count=statuses["SUCCESS"],
        application_error_count=statuses["APPLICATION_ERROR"],
        timeout_count=statuses["TIMEOUT"],
        navigation_error_count=statuses["NAVIGATION_ERROR"],
        apdex_score=round(score, 6) if score is not None else None,
        small_group=0 < total < NORMAL_GROUP_MINIMUM,
        final_group=total >= max(target, NORMAL_GROUP_MINIMUM),
        min_ms=float(min(ordered)) if ordered else None,
        max_ms=float(max(ordered)) if ordered else None,
        mean_ms=mean,
        median_ms=statistics.median(ordered) if ordered else None,
        stddev_ms=stddev,
        coefficient_of_variation=cv,
        p75_ms=_percentile(ordered, 0.75),
        p90_ms=_percentile(ordered, 0.90),
        p95_ms=_percentile(ordered, 0.95),
        p99_ms=_percentile(ordered, 0.99),
        first_half_mean_ms=first,
        second_half_mean_ms=second,
        trend_percent=trend,
        calculated_at=_utc_now(),
    )


def _log_progress(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    url: str,
    device: DeviceContext,
    context_index: int,
    context_total: int,
    config: SyntheticApdexConfig,
    samples: list[_MeasuredSample],
    item: _MeasuredSample,
) -> None:
    valid = _valid_count(samples)
    progress = min(valid / config.target_valid_samples * 100.0, 100.0)
    try_append_operational_event(
        workspace,
        "M23_APDEX_SAMPLE",
        level="WARNING" if item.classification in {"FRUSTRATED", None} else "INFO",
        audit_id=audit_id,
        url=url,
        device=device.value,
        context_index=context_index,
        context_total=context_total,
        run_index=item.run_index,
        attempt_count=len(samples),
        max_attempts=config.max_attempts_per_context,
        valid_samples=valid,
        target_valid_samples=config.target_valid_samples,
        progress_percent=round(progress, 2),
        classification=item.classification,
        status=item.measurement.status,
        duration_ms=item.measurement.duration_ms,
        http_status=item.measurement.http_status,
        error_code=item.measurement.error_code,
        profile_id=(config.mobile_profile if device is DeviceContext.MOBILE else config.desktop_profile).profile_id,
        cache_policy="COLD_CONTEXT",
    )


def _valid_count(samples: list[_MeasuredSample]) -> int:
    return sum(item.classification is not None for item in samples)


def _selected_contexts(workspace: AuditWorkspace, audit_id: str, max_pages: int) -> list[dict[str, Any]]:
    rows = _audit_contexts(workspace, audit_id)
    ordered_pages: list[str] = []
    for row in rows:
        page_id = str(row["page_id"])
        if page_id not in ordered_pages:
            ordered_pages.append(page_id)
    selected = set(ordered_pages if max_pages == 0 else ordered_pages[:max_pages])
    return [row for row in rows if str(row["page_id"]) in selected]


def _audit_contexts(workspace: AuditWorkspace, audit_id: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT p.page_id,p.normalized_url,s.snapshot_id,s.device,s.final_url
            FROM pages p JOIN page_snapshots s ON s.page_id=p.page_id
            WHERE p.audit_id=?
            ORDER BY p.normalized_url,p.page_id,s.device,s.snapshot_id
            """,
            (audit_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _configuration(cfg: SyntheticApdexConfig) -> dict[str, Any]:
    return {
        "task_id": TASK_NAVIGATION_LOAD,
        "task_start": "immediately before page.goto",
        "task_end": "page.goto wait_until=load completed",
        "cache_policy": "COLD_CONTEXT",
        "browser_context_policy": "FRESH_CONTEXT_PER_SAMPLE",
        "randomization": "NONE",
        "normal_group_minimum": NORMAL_GROUP_MINIMUM,
        "target_valid_samples": cfg.target_valid_samples,
        "max_attempts_per_context": cfg.max_attempts_per_context,
        "delay_seconds": cfg.delay_seconds,
        "concurrency": cfg.concurrency,
        "mobile_profile": cfg.mobile_profile.as_dict(),
        "desktop_profile": cfg.desktop_profile.as_dict(),
    }


def _percentile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return float(values[0])
    position = (len(values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return float(values[low])
    weight = position - low
    return float(values[low] * (1.0 - weight) + values[high] * weight)


def _validate_threshold_resolution(value: float) -> None:
    tolerance = 1e-9
    if value < 10:
        scaled = value * 10.0
        valid = abs(scaled - round(scaled)) <= tolerance
        hint = "0,1 segundo"
    elif value < 100:
        valid = abs(value - round(value)) <= tolerance
        hint = "1 segundo"
    elif value < 1000:
        scaled = value / 10.0
        valid = abs(scaled - round(scaled)) <= tolerance
        hint = "10 segundos"
    else:
        exponent = math.floor(math.log10(value)) - 1
        step = 10 ** exponent
        scaled = value / step
        valid = abs(scaled - round(scaled)) <= tolerance
        hint = "dois algarismos significativos"
    if not valid:
        raise ValueError(f"threshold T não respeita a resolução da especificação Apdex; use precisão de {hint}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: str | None, limit: int) -> str | None:
    return None if value is None else value[:limit]
