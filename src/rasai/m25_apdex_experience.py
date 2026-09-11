"""M25 - Synthetic User Experience Apdex calibrável.

M25 aproxima a estrutura de coleta de uma user action RUM, mas permanece
estritamente sintético. Ele não substitui nem recalcula o M23 Standard Apdex.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import sqlite3
import statistics
import threading
import time
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright

from rasai.browser_identity_renderer import realistic_context_options
from rasai.domain import new_id
from rasai.m23_apdex_profiles import (
    DESKTOP_STANDARD_PROFILE,
    MOBILE_STANDARD_PROFILE,
    TABLET_STANDARD_PROFILE,
    SyntheticProfile,
    _apply_network_profile,
    static_host_environment,
)
from rasai.m25_dynatrace import SUPPORTED_TIME_KPMS, load_dynatrace_calibration
from rasai.m25_persistence import M25Persistence, SyntheticUxRun, SyntheticUxSample, SyntheticUxSummary
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace

TASK_SYNTHETIC_USER_ACTION = "SYNTHETIC_LOAD_ACTION"
M25_PROFILE_VERSION = "M25-PROFILE-002"
NORMAL_GROUP_MINIMUM = 100
MAX_CONCURRENCY = 2
_DEVICE_ORDER = ("MOBILE", "DESKTOP", "TABLET")


@dataclass(frozen=True, slots=True)
class ExperienceApdexConfig:
    enabled: bool = False
    target_samples_per_page: int = 100
    max_attempts_per_page: int = 125
    max_pages: int = 1
    device_mix: tuple[tuple[str, float], ...] = ()
    session_mode: str = "cold"
    kpm: str = "USER_ACTION_DURATION"
    satisfied_threshold_seconds: float | None = None
    frustrated_threshold_seconds: float | None = None
    errors_affect_apdex: bool = True
    error_scope: str = "first-party"
    settle_seconds: float = 5.0
    delay_seconds: float = 1.0
    concurrency: int = 1
    dynatrace_import: bool = False
    dynatrace_base_url: str | None = None
    dynatrace_application_id: str | None = None
    dynatrace_config_json: str | None = None

    def validate(self) -> "ExperienceApdexConfig":
        if not self.enabled:
            return self
        if self.target_samples_per_page < 1:
            raise ValueError("Synthetic User Experience Apdex: target_samples_per_page deve ser >= 1")
        if self.max_attempts_per_page < self.target_samples_per_page:
            raise ValueError("Synthetic User Experience Apdex: max_attempts_per_page deve ser >= target_samples_per_page")
        if self.max_pages < 0:
            raise ValueError("Synthetic User Experience Apdex: max_pages deve ser >= 0; 0 significa todas")
        mix = self.device_mix_dict()
        if not mix:
            raise ValueError("Synthetic User Experience Apdex exige mix explícito de dispositivos, por exemplo mobile=60,desktop=35,tablet=5")
        if abs(sum(mix.values()) - 100.0) > 1e-6:
            raise ValueError("Synthetic User Experience Apdex: device mix deve somar exatamente 100")
        if any(value < 0 for value in mix.values()):
            raise ValueError("Synthetic User Experience Apdex: device mix não aceita percentuais negativos")
        if self.session_mode not in {"cold", "warm"}:
            raise ValueError("Synthetic User Experience Apdex: session_mode deve ser cold ou warm")
        normalized_kpm = self.kpm.strip().upper()
        if not self.dynatrace_import and not self.dynatrace_config_json:
            if normalized_kpm not in SUPPORTED_TIME_KPMS:
                raise ValueError(f"KPM não suportada para calibração temporal do Synthetic User Experience Apdex: {normalized_kpm}")
            _validate_thresholds(self.satisfied_threshold_seconds, self.frustrated_threshold_seconds)
        if self.error_scope not in {"navigation", "first-party", "all"}:
            raise ValueError("Synthetic User Experience Apdex: error_scope deve ser navigation, first-party ou all")
        if not math.isfinite(self.settle_seconds) or self.settle_seconds <= 0:
            raise ValueError("Synthetic User Experience Apdex: settle_seconds deve ser > 0")
        if not math.isfinite(self.delay_seconds) or self.delay_seconds < 0:
            raise ValueError("Synthetic User Experience Apdex: delay_seconds deve ser >= 0")
        if self.concurrency < 1 or self.concurrency > MAX_CONCURRENCY:
            raise ValueError(f"Synthetic User Experience Apdex: concurrency deve estar entre 1 e {MAX_CONCURRENCY}")
        if self.dynatrace_import and not self.dynatrace_config_json:
            if not self.dynatrace_base_url or not self.dynatrace_application_id:
                raise ValueError("Synthetic User Experience Apdex: importação Dynatrace exige base URL e application ID")
        return self

    def device_mix_dict(self) -> dict[str, float]:
        return {str(name).upper(): float(value) for name, value in self.device_mix if float(value) > 0}

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "target_samples_per_page": self.target_samples_per_page,
            "max_attempts_per_page": self.max_attempts_per_page,
            "max_pages": self.max_pages,
            "device_mix": self.device_mix_dict(),
            "session_mode": self.session_mode,
            "kpm": self.kpm,
            "satisfied_threshold_seconds": self.satisfied_threshold_seconds,
            "frustrated_threshold_seconds": self.frustrated_threshold_seconds,
            "errors_affect_apdex": self.errors_affect_apdex,
            "error_scope": self.error_scope,
            "settle_seconds": self.settle_seconds,
            "delay_seconds": self.delay_seconds,
            "concurrency": self.concurrency,
            "dynatrace_import": self.dynatrace_import,
            "dynatrace_base_url": self.dynatrace_base_url,
            "dynatrace_application_id": self.dynatrace_application_id,
            "dynatrace_config_json": self.dynatrace_config_json,
            "dynatrace_api_token_persisted": False,
        }


@dataclass(frozen=True, slots=True)
class Calibration:
    source: str
    kpm: str
    satisfied_threshold_seconds: float
    frustrated_threshold_seconds: float
    errors_affect_apdex: bool
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UxMeasurement:
    status: str
    user_action_duration_ms: float | None
    navigation_duration_ms: float | None = None
    response_start_ms: float | None = None
    response_end_ms: float | None = None
    dom_interactive_ms: float | None = None
    load_event_start_ms: float | None = None
    load_event_end_ms: float | None = None
    lcp_ms: float | None = None
    cls: float | None = None
    http_status: int | None = None
    final_url: str | None = None
    xhr_fetch_count: int = 0
    dynamic_resource_count: int = 0
    javascript_error_count: int = 0
    console_error_count: int = 0
    request_failed_count: int = 0
    first_party_request_failed_count: int = 0
    http_error_count: int = 0
    first_party_http_error_count: int = 0
    network_settled: bool = True
    profile_applied: bool = True
    error_code: str | None = None
    error_message: str | None = None
    cpu_method: str | None = None
    network_method: str | None = None


class SyntheticUxGateway(Protocol):
    def measure(
        self,
        *,
        url: str,
        device: str,
        profile: SyntheticProfile,
        timeout_seconds: float,
        settle_seconds: float,
    ) -> UxMeasurement: ...
    def environment(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class M25ExecutionResult:
    enabled: bool
    status: str
    pages_considered: int
    attempted_samples: int
    valid_samples: int
    invalid_samples: int
    final_population_groups: int
    report_path: str | None


@dataclass(frozen=True, slots=True)
class _Classified:
    run_index: int
    device: str
    measurement: UxMeasurement
    classification: str | None
    kpm_value_ms: float | None
    error_forced: bool


class _OriginPacer:
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


class PlaywrightSyntheticUxGateway:
    """Chromium gateway that records a bounded synthetic load-action envelope."""

    def __init__(self, *, session_mode: str = "cold", executable_path: str | None = None) -> None:
        self.session_mode = session_mode
        self.executable_path = executable_path
        self._playwright = None
        self._browser = None
        self._startup_error: str | None = None
        self._warm_contexts: dict[str, Any] = {}

    def _start(self) -> None:
        if self._browser is not None or self._startup_error is not None:
            return
        try:
            self._playwright = sync_playwright().start()
            options: dict[str, Any] = {"headless": True}
            if self.executable_path:
                options["executable_path"] = self.executable_path
            self._browser = self._playwright.chromium.launch(**options)
        except Exception as exc:
            self._startup_error = type(exc).__name__
            self.close()

    def environment(self) -> dict[str, Any]:
        self._start()
        value = static_host_environment()
        value["chromium_version"] = getattr(self._browser, "version", None) if self._browser is not None else None
        value["m25_profile_version"] = M25_PROFILE_VERSION
        value["session_mode"] = self.session_mode
        value["startup_error"] = self._startup_error
        return value

    def close(self) -> None:
        for context in list(self._warm_contexts.values()):
            try:
                context.close()
            except Exception:
                pass
        self._warm_contexts.clear()
        browser, playwright = self._browser, self._playwright
        self._browser = None
        self._playwright = None
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass

    def _context(self, *, device: str, profile: SyntheticProfile) -> tuple[Any, bool]:
        assert self._browser is not None and self._playwright is not None
        if self.session_mode == "warm" and profile.profile_id in self._warm_contexts:
            return self._warm_contexts[profile.profile_id], False
        context_options, _identity = realistic_context_options(
            self._playwright,
            browser_version=getattr(self._browser, "version", None),
            device=profile.device,
            profile_override=profile.browser_profile,
            descriptor_name=profile.playwright_descriptor or None,
        )
        context = self._browser.new_context(**context_options)
        if self.session_mode == "warm":
            self._warm_contexts[profile.profile_id] = context
            return context, False
        return context, True

    def measure(
        self,
        *,
        url: str,
        device: str,
        profile: SyntheticProfile,
        timeout_seconds: float,
        settle_seconds: float,
    ) -> UxMeasurement:
        self._start()
        if self._browser is None or self._playwright is None:
            return UxMeasurement(
                status="BROWSER_UNAVAILABLE",
                user_action_duration_ms=None,
                profile_applied=False,
                network_settled=False,
                error_code=self._startup_error or "BROWSER_UNAVAILABLE",
            )

        context = page = session = None
        close_context = False
        cpu_method = network_method = None
        counters = {
            "xhr_fetch": 0,
            "dynamic": 0,
            "js": 0,
            "console": 0,
            "failed": 0,
            "first_failed": 0,
            "http": 0,
            "first_http": 0,
        }
        started = time.monotonic()
        last_activity = started
        load_completed_at: float | None = None
        target_host = _normalize_host(urlsplit(url).hostname)

        def is_first_party(candidate: str) -> bool:
            return _normalize_host(urlsplit(candidate).hostname) == target_host

        def mark_activity() -> None:
            nonlocal last_activity
            last_activity = time.monotonic()

        try:
            context, close_context = self._context(device=device, profile=profile)
            page = context.new_page()
            session = context.new_cdp_session(page)
            session.send("Network.enable")
            session.send("Network.setCacheDisabled", {"cacheDisabled": self.session_mode == "cold"})
            try:
                session.send("Emulation.setCPUThrottlingRate", {"rate": profile.cpu_slowdown})
                cpu_method = "CDP:Emulation.setCPUThrottlingRate"
            except PlaywrightError as exc:
                return _invalid("CPU_PROFILE_ERROR", exc, cpu_method, network_method)
            try:
                network_method = _apply_network_profile(session, profile)
            except PlaywrightError as exc:
                return _invalid("NETWORK_PROFILE_ERROR", exc, cpu_method, network_method)

            page.add_init_script(
                """
                (() => {
                  window.__rasaiUx = {lcp: null, cls: 0};
                  try {
                    new PerformanceObserver((list) => {
                      const entries = list.getEntries();
                      if (entries.length) window.__rasaiUx.lcp = entries[entries.length - 1].startTime;
                    }).observe({type: 'largest-contentful-paint', buffered: true});
                  } catch (_) {}
                  try {
                    new PerformanceObserver((list) => {
                      for (const e of list.getEntries()) if (!e.hadRecentInput) window.__rasaiUx.cls += e.value || 0;
                    }).observe({type: 'layout-shift', buffered: true});
                  } catch (_) {}
                })();
                """
            )

            def on_request(request: Any) -> None:
                if str(getattr(request, "resource_type", "")) in {"xhr", "fetch"}:
                    counters["xhr_fetch"] += 1
                if load_completed_at is not None and str(getattr(request, "resource_type", "")) != "document":
                    counters["dynamic"] += 1

            def on_request_finished(_request: Any) -> None:
                mark_activity()

            def on_request_failed(request: Any) -> None:
                counters["failed"] += 1
                if is_first_party(str(getattr(request, "url", ""))):
                    counters["first_failed"] += 1
                mark_activity()

            def on_response(response: Any) -> None:
                try:
                    status = int(response.status)
                    response_url = str(response.url)
                except Exception:
                    return
                if status >= 400:
                    counters["http"] += 1
                    if is_first_party(response_url):
                        counters["first_http"] += 1

            page.on("request", on_request)
            page.on("requestfinished", on_request_finished)
            page.on("requestfailed", on_request_failed)
            page.on("response", on_response)
            page.on("pageerror", lambda _exc: counters.__setitem__("js", counters["js"] + 1))
            page.on("console", lambda msg: counters.__setitem__("console", counters["console"] + (1 if msg.type == "error" else 0)))

            started = time.monotonic()
            last_activity = started
            try:
                response = page.goto(url, wait_until="load", timeout=int(timeout_seconds * 1000.0))
                load_completed_at = time.monotonic()
                http_status = response.status if response is not None else None
                status = "APPLICATION_ERROR" if http_status is not None and http_status >= 400 else "SUCCESS"
            except PlaywrightTimeoutError:
                elapsed = (time.monotonic() - started) * 1000.0
                return UxMeasurement(
                    status="TIMEOUT", user_action_duration_ms=elapsed,
                    http_status=None, final_url=page.url, network_settled=False,
                    error_code="NAVIGATION_TIMEOUT", error_message="navigation exceeded configured timeout",
                    cpu_method=cpu_method, network_method=network_method,
                )
            except PlaywrightError as exc:
                elapsed = (time.monotonic() - started) * 1000.0
                return UxMeasurement(
                    status="NAVIGATION_ERROR", user_action_duration_ms=elapsed,
                    http_status=None, final_url=page.url, network_settled=False,
                    error_code=type(exc).__name__.upper(), error_message=_bounded(str(exc), 256),
                    cpu_method=cpu_method, network_method=network_method,
                )

            network_settled = True
            try:
                page.wait_for_load_state("networkidle", timeout=int(settle_seconds * 1000.0))
            except PlaywrightTimeoutError:
                network_settled = False

            action_end = max(load_completed_at or started, last_activity)
            user_action_ms = max((action_end - started) * 1000.0, 0.0)
            timing: dict[str, Any] = {}
            visual: dict[str, Any] = {}
            try:
                timing = page.evaluate(
                    """() => {
                      const n = performance.getEntriesByType('navigation')[0];
                      if (!n) return {};
                      const v = (x) => Number.isFinite(x) && x >= 0 ? x : null;
                      return {
                        duration: v(n.duration), responseStart: v(n.responseStart), responseEnd: v(n.responseEnd),
                        domInteractive: v(n.domInteractive), loadEventStart: v(n.loadEventStart), loadEventEnd: v(n.loadEventEnd)
                      };
                    }"""
                ) or {}
                visual = page.evaluate("() => window.__rasaiUx || {}") or {}
            except PlaywrightError:
                pass

            return UxMeasurement(
                status=status,
                user_action_duration_ms=user_action_ms,
                navigation_duration_ms=_num(timing.get("duration")),
                response_start_ms=_num(timing.get("responseStart")),
                response_end_ms=_num(timing.get("responseEnd")),
                dom_interactive_ms=_num(timing.get("domInteractive")),
                load_event_start_ms=_num(timing.get("loadEventStart")),
                load_event_end_ms=_num(timing.get("loadEventEnd")),
                lcp_ms=_num(visual.get("lcp")),
                cls=_num(visual.get("cls")),
                http_status=http_status,
                final_url=page.url,
                xhr_fetch_count=counters["xhr_fetch"],
                dynamic_resource_count=counters["dynamic"],
                javascript_error_count=counters["js"],
                console_error_count=counters["console"],
                request_failed_count=counters["failed"],
                first_party_request_failed_count=counters["first_failed"],
                http_error_count=counters["http"],
                first_party_http_error_count=counters["first_http"],
                network_settled=network_settled,
                profile_applied=True,
                cpu_method=cpu_method,
                network_method=network_method,
            )
        except PlaywrightError as exc:
            return _invalid("MEASUREMENT_ERROR", exc, cpu_method, network_method)
        except Exception as exc:
            return _invalid("MEASUREMENT_SETUP_ERROR", exc, cpu_method, network_method)
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass
            if page is not None:
                try:
                    page.close()
                except Exception:
                    pass
            if close_context and context is not None:
                try:
                    context.close()
                except Exception:
                    pass


def resolve_calibration(config: ExperienceApdexConfig) -> Calibration:
    cfg = config.validate()
    if cfg.dynatrace_import or cfg.dynatrace_config_json:
        imported = load_dynatrace_calibration(
            base_url=cfg.dynatrace_base_url,
            application_id=cfg.dynatrace_application_id,
            config_json_path=cfg.dynatrace_config_json,
        )
        if imported.kpm not in SUPPORTED_TIME_KPMS:
            raise ValueError(
                f"Dynatrace usa KPM {imported.kpm}, ainda não mensurável com equivalência suficiente no Synthetic User Experience Apdex; "
                "nenhum fallback silencioso foi aplicado"
            )
        errors = imported.errors_affect_apdex
        source = imported.source
        metadata = dict(imported.metadata)
        if errors is None:
            errors = cfg.errors_affect_apdex
            source += "+MANUAL_ERROR_POLICY"
            metadata["error_policy_fallback"] = "manual M25 configuration"
        return Calibration(
            source=source,
            kpm=imported.kpm,
            satisfied_threshold_seconds=imported.satisfied_threshold_seconds,
            frustrated_threshold_seconds=imported.frustrated_threshold_seconds,
            errors_affect_apdex=bool(errors),
            metadata=metadata,
        )

    _validate_thresholds(cfg.satisfied_threshold_seconds, cfg.frustrated_threshold_seconds)
    return Calibration(
        source="MANUAL_CALIBRATION",
        kpm=cfg.kpm.strip().upper(),
        satisfied_threshold_seconds=float(cfg.satisfied_threshold_seconds),
        frustrated_threshold_seconds=float(cfg.frustrated_threshold_seconds),
        errors_affect_apdex=cfg.errors_affect_apdex,
        metadata={"threshold_unit": "seconds", "raw_configuration_persisted": False},
    )


def classify_measurement(
    measurement: UxMeasurement,
    calibration: Calibration,
    *,
    error_scope: str,
) -> tuple[str | None, float | None, bool]:
    if not measurement.profile_applied:
        return None, None, False
    value = kpm_value_ms(measurement, calibration.kpm)
    if measurement.status in {"TIMEOUT", "NAVIGATION_ERROR"}:
        return "FRUSTRATED", value, True
    if value is None:
        return None, None, False
    forced = calibration.errors_affect_apdex and _qualifying_error(measurement, error_scope)
    if forced:
        return "FRUSTRATED", value, True
    seconds = value / 1000.0
    if seconds < calibration.satisfied_threshold_seconds:
        return "SATISFIED", value, False
    if seconds <= calibration.frustrated_threshold_seconds:
        return "TOLERATING", value, False
    return "FRUSTRATED", value, False


def kpm_value_ms(item: UxMeasurement, kpm: str) -> float | None:
    mapping = {
        "USER_ACTION_DURATION": item.user_action_duration_ms,
        "DOM_INTERACTIVE": item.dom_interactive_ms,
        "LOAD_EVENT_START": item.load_event_start_ms,
        "LOAD_EVENT_END": item.load_event_end_ms,
        "RESPONSE_START": item.response_start_ms,
        "RESPONSE_END": item.response_end_ms,
        "LARGEST_CONTENTFUL_PAINT": item.lcp_ms,
    }
    value = mapping.get(kpm.strip().upper())
    return float(value) if value is not None and math.isfinite(float(value)) and float(value) >= 0 else None


def execute_m25_experience(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    config: ExperienceApdexConfig,
    gateway: SyntheticUxGateway | None = None,
    gateway_factory: Callable[[], SyntheticUxGateway] | None = None,
) -> M25ExecutionResult:
    cfg = config.validate()
    if not cfg.enabled:
        return M25ExecutionResult(False, "DISABLED", 0, 0, 0, 0, 0, None)
    calibration = resolve_calibration(cfg)
    pages = _selected_pages(workspace, audit_id, cfg.max_pages)
    mix = cfg.device_mix_dict()
    targets = allocate_samples(cfg.target_samples_per_page, mix)
    attempt_targets = allocate_attempts(cfg.max_attempts_per_page, mix, targets)
    factory = gateway_factory or (lambda: PlaywrightSyntheticUxGateway(session_mode=cfg.session_mode))
    pacer = _OriginPacer(cfg.delay_seconds)

    try_append_operational_event(
        workspace,
        "M25_UX_STARTED",
        audit_id=audit_id,
        task_id=TASK_SYNTHETIC_USER_ACTION,
        pages=len(pages),
        target_samples_per_page=cfg.target_samples_per_page,
        device_mix=mix,
        session_mode=cfg.session_mode,
        kpm=calibration.kpm,
        satisfied_threshold_seconds=calibration.satisfied_threshold_seconds,
        frustrated_threshold_seconds=calibration.frustrated_threshold_seconds,
        errors_affect_apdex=calibration.errors_affect_apdex,
        error_scope=cfg.error_scope,
        calibration_source=calibration.source,
    )

    shared_gateway = gateway
    owned_shared = False
    if shared_gateway is not None and cfg.concurrency != 1:
        raise ValueError("Synthetic User Experience Apdex: gateway injetado exige concurrency=1")
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

    attempted_total = valid_total = invalid_total = final_groups = 0
    summaries_all: list[SyntheticUxSummary] = []
    try:
        with M25Persistence(workspace) as store:
            store.clear_audit(audit_id)
            for page_index, page in enumerate(pages, 1):
                page_samples: list[_Classified] = []
                per_device: dict[str, list[_Classified]] = {}
                for device in _DEVICE_ORDER:
                    target = targets.get(device, 0)
                    if target <= 0:
                        continue
                    items = _measure_device(
                        audit_id=audit_id,
                        workspace=workspace,
                        url=str(page["url"]),
                        device=device,
                        target=target,
                        max_attempts=attempt_targets[device],
                        page_index=page_index,
                        page_total=len(pages),
                        calibration=calibration,
                        config=cfg,
                        pacer=pacer,
                        shared_gateway=shared_gateway,
                        factory=factory,
                    )
                    per_device[device] = items
                    page_samples.extend(items)
                    profile = _profile_for_device(device)
                    for sample in items:
                        store.add_sample(_persisted_sample(audit_id, str(page["page_id"]), str(page["url"]), profile, cfg, calibration, sample))
                    summary = _summary(
                        audit_id=audit_id,
                        page_id=str(page["page_id"]),
                        url=str(page["url"]),
                        device=device,
                        profile_id=profile.profile_id,
                        target=target,
                        items=items,
                    )
                    store.upsert_summary(summary)
                    summaries_all.append(summary)
                population = _summary(
                    audit_id=audit_id,
                    page_id=str(page["page_id"]),
                    url=str(page["url"]),
                    device="POPULATION",
                    profile_id="MIXED_DEVICE_POPULATION",
                    target=cfg.target_samples_per_page,
                    items=page_samples,
                )
                store.upsert_summary(population)
                summaries_all.append(population)
                if population.final_group:
                    final_groups += 1
                attempted_total += len(page_samples)
                valid_total += sum(item.classification is not None for item in page_samples)
                invalid_total += sum(item.classification is None for item in page_samples)

            if not pages:
                status, reason = "NO_PAGES", "NO_AUDITED_PAGES"
            elif final_groups == len(pages) and invalid_total == 0:
                status, reason = "SUCCESS", None
            elif valid_total == 0:
                status, reason = "UNAVAILABLE", "NO_VALID_SYNTHETIC_UX_SAMPLES"
            else:
                status, reason = "PARTIAL", "ONE_OR_MORE_POPULATION_GROUPS_INCOMPLETE_OR_INVALID"

            store.upsert_run(SyntheticUxRun(
                audit_id=audit_id,
                enabled=True,
                status=status,
                task_id=TASK_SYNTHETIC_USER_ACTION,
                target_samples_per_page=cfg.target_samples_per_page,
                max_attempts_per_page=cfg.max_attempts_per_page,
                page_limit=cfg.max_pages,
                pages_considered=len(pages),
                attempted_samples=attempted_total,
                valid_samples=valid_total,
                invalid_samples=invalid_total,
                device_mix=mix,
                session_mode=cfg.session_mode,
                kpm=calibration.kpm,
                satisfied_threshold_seconds=calibration.satisfied_threshold_seconds,
                frustrated_threshold_seconds=calibration.frustrated_threshold_seconds,
                errors_affect_apdex=calibration.errors_affect_apdex,
                error_scope=cfg.error_scope,
                settle_seconds=cfg.settle_seconds,
                calibration_source=calibration.source,
                dynatrace_application_id=cfg.dynatrace_application_id,
                calibration_metadata=calibration.metadata,
                configuration=cfg.as_dict(),
                host_environment=host_environment,
                reason=reason,
                updated_at=_utc_now(),
            ))
    finally:
        if owned_shared and shared_gateway is not None:
            shared_gateway.close()

    report_path: str | None = None
    try:
        from rasai.m25_reporting import enrich_m25_report_site
        path = enrich_m25_report_site(audit_id=audit_id, workspace=workspace)
        report_path = str(path)
    except Exception as exc:
        try_append_operational_event(
            workspace, "M25_UX_REPORT_FAILURE", level="WARNING", audit_id=audit_id,
            error_type=type(exc).__name__, error_message=_bounded(str(exc), 512),
        )

    try_append_operational_event(
        workspace,
        "M25_UX_COMPLETED",
        audit_id=audit_id,
        status=status,
        attempted_samples=attempted_total,
        valid_samples=valid_total,
        invalid_samples=invalid_total,
        final_population_groups=final_groups,
        report_path=report_path,
    )
    return M25ExecutionResult(True, status, len(pages), attempted_total, valid_total, invalid_total, final_groups, report_path)


def allocate_samples(total: int, mix: dict[str, float]) -> dict[str, int]:
    if total < 1:
        raise ValueError("total deve ser >=1")
    normalized = {name.upper(): float(value) for name, value in mix.items() if float(value) > 0}
    if any(name not in _DEVICE_ORDER for name in normalized):
        unknown = sorted(set(normalized) - set(_DEVICE_ORDER))
        raise ValueError(f"device mix contém device não suportado: {', '.join(unknown)}")
    if abs(sum(normalized.values()) - 100.0) > 1e-6:
        raise ValueError("device mix deve somar 100")
    raw = {name: total * value / 100.0 for name, value in normalized.items()}
    result = {name: int(math.floor(value)) for name, value in raw.items()}
    remaining = total - sum(result.values())
    order = sorted(normalized, key=lambda name: (-(raw[name] - result[name]), _DEVICE_ORDER.index(name)))
    for name in order[:remaining]:
        result[name] += 1
    return {name: result.get(name, 0) for name in _DEVICE_ORDER if name in normalized}


def allocate_attempts(total: int, mix: dict[str, float], targets: dict[str, int]) -> dict[str, int]:
    result = allocate_samples(total, mix)
    for name, target in targets.items():
        result[name] = max(result.get(name, 0), target)
    return result


def _measure_device(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    target: int,
    max_attempts: int,
    page_index: int,
    page_total: int,
    calibration: Calibration,
    config: ExperienceApdexConfig,
    pacer: _OriginPacer,
    shared_gateway: SyntheticUxGateway | None,
    factory: Callable[[], SyntheticUxGateway],
) -> list[_Classified]:
    profile = _profile_for_device(device)

    def one(run_index: int, runner: SyntheticUxGateway) -> _Classified:
        pacer.wait_for_slot()
        measurement = runner.measure(
            url=url, device=device, profile=profile,
            timeout_seconds=max(config.settle_seconds + calibration.frustrated_threshold_seconds + 5.0, 15.0),
            settle_seconds=config.settle_seconds,
        )
        classification, value, forced = classify_measurement(measurement, calibration, error_scope=config.error_scope)
        item = _Classified(run_index, device, measurement, classification, value, forced)
        _log_progress(workspace, audit_id, url, device, page_index, page_total, target, max_attempts, item)
        return item

    if config.concurrency == 1:
        assert shared_gateway is not None
        items: list[_Classified] = []
        for index in range(1, max_attempts + 1):
            if sum(item.classification is not None for item in items) >= target:
                break
            items.append(one(index, shared_gateway))
        return items

    thread_state = threading.local()
    runners: list[SyntheticUxGateway] = []
    runners_lock = threading.Lock()

    def runner_for_thread() -> SyntheticUxGateway:
        runner = getattr(thread_state, "runner", None)
        if runner is None:
            runner = factory()
            thread_state.runner = runner
            with runners_lock:
                runners.append(runner)
        return runner

    def task(index: int) -> _Classified:
        return one(index, runner_for_thread())

    items: list[_Classified] = []
    next_index = 1
    futures: dict[Future[_Classified], int] = {}
    try:
        with ThreadPoolExecutor(max_workers=config.concurrency, thread_name_prefix="rasai-ux") as executor:
            while next_index <= max_attempts and len(futures) < config.concurrency:
                futures[executor.submit(task, next_index)] = next_index
                next_index += 1
            while futures:
                done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
                for future in done:
                    futures.pop(future, None)
                    items.append(future.result())
                if sum(item.classification is not None for item in items) >= target:
                    for future in futures:
                        future.cancel()
                    break
                while next_index <= max_attempts and len(futures) < config.concurrency:
                    futures[executor.submit(task, next_index)] = next_index
                    next_index += 1
    finally:
        for runner in runners:
            try:
                runner.close()
            except Exception:
                pass
    return sorted(items, key=lambda item: item.run_index)


def _persisted_sample(
    audit_id: str,
    page_id: str,
    url: str,
    profile: SyntheticProfile,
    config: ExperienceApdexConfig,
    calibration: Calibration,
    item: _Classified,
) -> SyntheticUxSample:
    m = item.measurement
    return SyntheticUxSample(
        sample_id=new_id("UXA"), audit_id=audit_id, page_id=page_id, url=url,
        device=item.device, run_index=item.run_index, task_id=TASK_SYNTHETIC_USER_ACTION,
        profile_id=profile.profile_id, session_mode=config.session_mode, status=m.status,
        classification=item.classification, kpm=calibration.kpm, kpm_value_ms=item.kpm_value_ms,
        user_action_duration_ms=m.user_action_duration_ms, navigation_duration_ms=m.navigation_duration_ms,
        response_start_ms=m.response_start_ms, response_end_ms=m.response_end_ms,
        dom_interactive_ms=m.dom_interactive_ms, load_event_start_ms=m.load_event_start_ms,
        load_event_end_ms=m.load_event_end_ms, lcp_ms=m.lcp_ms, cls=m.cls,
        http_status=m.http_status, final_url=m.final_url, xhr_fetch_count=m.xhr_fetch_count,
        dynamic_resource_count=m.dynamic_resource_count, javascript_error_count=m.javascript_error_count,
        console_error_count=m.console_error_count, request_failed_count=m.request_failed_count,
        first_party_request_failed_count=m.first_party_request_failed_count,
        http_error_count=m.http_error_count, first_party_http_error_count=m.first_party_http_error_count,
        network_settled=m.network_settled, error_forced_frustrated=item.error_forced,
        error_code=m.error_code, error_message=_bounded(m.error_message, 256),
        cpu_method=m.cpu_method, network_method=m.network_method, captured_at=_utc_now(),
    )


def _summary(
    *,
    audit_id: str,
    page_id: str,
    url: str,
    device: str,
    profile_id: str,
    target: int,
    items: list[_Classified],
) -> SyntheticUxSummary:
    valid = [item for item in items if item.classification is not None]
    values = sorted(float(item.kpm_value_ms) for item in valid if item.kpm_value_ms is not None)
    counts = {name: sum(item.classification == name for item in valid) for name in ("SATISFIED", "TOLERATING", "FRUSTRATED")}
    total = len(valid)
    score = (counts["SATISFIED"] + 0.5 * counts["TOLERATING"]) / total if total else None
    return SyntheticUxSummary(
        summary_id=new_id("UXS"), audit_id=audit_id, page_id=page_id, url=url,
        device=device, task_id=TASK_SYNTHETIC_USER_ACTION, profile_id=profile_id,
        target_samples=target, valid_samples=total, invalid_samples=len(items) - total,
        satisfied_count=counts["SATISFIED"], tolerating_count=counts["TOLERATING"],
        frustrated_count=counts["FRUSTRATED"],
        error_forced_frustrated_count=sum(item.error_forced for item in valid),
        apdex_score=round(score, 6) if score is not None else None,
        small_group=0 < total < NORMAL_GROUP_MINIMUM,
        final_group=total >= target,
        mean_ms=statistics.fmean(values) if values else None,
        median_ms=statistics.median(values) if values else None,
        p75_ms=_percentile(values, 0.75), p90_ms=_percentile(values, 0.90),
        p95_ms=_percentile(values, 0.95), p99_ms=_percentile(values, 0.99),
        javascript_error_samples=sum(item.measurement.javascript_error_count > 0 for item in valid),
        request_error_samples=sum(
            (item.measurement.request_failed_count + item.measurement.http_error_count) > 0 for item in valid
        ),
        network_unsettled_samples=sum(not item.measurement.network_settled for item in valid),
        calculated_at=_utc_now(),
    )


def _qualifying_error(item: UxMeasurement, scope: str) -> bool:
    if item.status == "APPLICATION_ERROR":
        return True
    if scope == "navigation":
        return False
    if item.javascript_error_count > 0:
        return True
    if scope == "first-party":
        return item.first_party_request_failed_count > 0 or item.first_party_http_error_count > 0
    return item.request_failed_count > 0 or item.http_error_count > 0


def _profile_for_device(device: str) -> SyntheticProfile:
    if device == "MOBILE":
        return MOBILE_STANDARD_PROFILE
    if device == "DESKTOP":
        return DESKTOP_STANDARD_PROFILE
    if device == "TABLET":
        return TABLET_STANDARD_PROFILE
    raise ValueError(f"device não suportado pelo Synthetic User Experience Apdex: {device}")


def _selected_pages(workspace: AuditWorkspace, audit_id: str, max_pages: int) -> list[dict[str, str]]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT p.page_id,p.normalized_url,s.final_url
            FROM pages p LEFT JOIN page_snapshots s ON s.page_id=p.page_id
            WHERE p.audit_id=? ORDER BY p.normalized_url,p.page_id,s.snapshot_id
            """,
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()
    by_page: dict[str, dict[str, str]] = {}
    for row in rows:
        page_id = str(row["page_id"])
        if page_id not in by_page:
            by_page[page_id] = {
                "page_id": page_id,
                "url": str(row["final_url"] or row["normalized_url"]),
            }
    values = list(by_page.values())
    return values if max_pages == 0 else values[:max_pages]


def _log_progress(
    workspace: AuditWorkspace,
    audit_id: str,
    url: str,
    device: str,
    page_index: int,
    page_total: int,
    target: int,
    max_attempts: int,
    item: _Classified,
) -> None:
    try_append_operational_event(
        workspace,
        "M25_UX_SAMPLE",
        level="WARNING" if item.classification in {"FRUSTRATED", None} else "INFO",
        audit_id=audit_id, url=url, device=device, page_index=page_index, page_total=page_total,
        run_index=item.run_index, target_valid_samples=target, max_attempts=max_attempts,
        classification=item.classification, status=item.measurement.status,
        kpm_value_ms=item.kpm_value_ms, error_forced_frustrated=item.error_forced,
        javascript_errors=item.measurement.javascript_error_count,
        request_failures=item.measurement.request_failed_count,
        http_errors=item.measurement.http_error_count,
        network_settled=item.measurement.network_settled,
    )


def _validate_thresholds(satisfied: float | None, frustrated: float | None) -> None:
    if satisfied is None or frustrated is None:
        raise ValueError("Synthetic User Experience Apdex exige thresholds Satisfied/Tolerating e Frustrated ou importação Dynatrace")
    if not math.isfinite(float(satisfied)) or float(satisfied) <= 0:
        raise ValueError("Synthetic User Experience Apdex: satisfied threshold deve ser >0")
    if not math.isfinite(float(frustrated)) or float(frustrated) <= float(satisfied):
        raise ValueError("Synthetic User Experience Apdex: frustrated threshold deve ser maior que o satisfied threshold")


def _invalid(code: str, exc: Exception, cpu_method: str | None, network_method: str | None) -> UxMeasurement:
    return UxMeasurement(
        status="INVALID_SAMPLE", user_action_duration_ms=None, profile_applied=False,
        network_settled=False, error_code=code, error_message=_bounded(str(exc), 256),
        cpu_method=cpu_method, network_method=network_method,
    )


def _normalize_host(host: str | None) -> str:
    value = (host or "").strip().lower().rstrip(".")
    return value[4:] if value.startswith("www.") else value


def _num(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _percentile(values: list[float], fraction: float) -> float | None:
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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bounded(value: str | None, limit: int) -> str | None:
    return None if value is None else str(value)[:limit]
