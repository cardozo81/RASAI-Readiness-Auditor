"""Runtime policy for bounded, non-redundant external measurements.

The core audit owns direct HTTP acquisition and one Chromium snapshot navigation per
URL/device. External services run only after that evidence is persisted. They must not
silently re-fetch the target unless their metric contract requires an independent
measurement.

PageSpeed Insights is such an independent measurement: Google's service runs its own
Lighthouse navigation. CrUX is a data-service lookup and does not navigate the target.
This adapter therefore keeps one PageSpeed request per selected URL/device, removes the
legacy automatic retry, and adds a caller-side wall-clock deadline so a slow provider
cannot hold the audit indefinitely.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import queue
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request

from rasai.operational_log import try_append_operational_event


POLICY_VERSION = "EXTERNAL-MEASUREMENT-001"
_INSTALLED = False
_STATE = threading.local()


@dataclass(slots=True)
class _M21ExecutionState:
    audit_id: str
    workspace: Any
    context_total: int
    context_index: int = 0
    active_context_index: int = 0

    def begin_pagespeed(self) -> int:
        self.context_index += 1
        self.active_context_index = self.context_index
        return self.active_context_index

    def current_context(self) -> int:
        return max(self.active_context_index, 1 if self.context_total else 0)


def _run_with_wallclock_deadline(
    operation: Callable[[], Any],
    *,
    service: str,
    timeout_seconds: float,
    error_type: type[Exception],
) -> Any:
    """Return/raise within the configured wall-clock budget.

    urllib's timeout is fundamentally a socket-operation timeout. A daemon worker gives
    the caller a second, total wall-clock boundary. The underlying request receives the
    same socket timeout and is never retried by this policy.
    """
    timeout = max(float(timeout_seconds), 0.001)
    result_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
    started = time.monotonic()

    def run() -> None:
        try:
            result_queue.put(("result", operation()))
        except Exception as exc:  # pragma: no branch - one terminal path per worker
            result_queue.put(("error", exc))

    worker = threading.Thread(
        target=run,
        name=f"rasai-{service.casefold()}-deadline",
        daemon=True,
    )
    worker.start()
    worker.join(timeout)
    duration_ms = int(max(time.monotonic() - started, 0.0) * 1000.0)
    if worker.is_alive():
        raise error_type(
            service,
            f"wall-clock deadline exceeded after {timeout:g}s",
            error_code="WALL_CLOCK_TIMEOUT",
            duration_ms=duration_ms,
        )
    try:
        kind, value = result_queue.get_nowait()
    except queue.Empty as exc:
        raise error_type(
            service,
            "external request worker finished without a result",
            error_code="WORKER_RESULT_MISSING",
            duration_ms=duration_ms,
        ) from exc
    if kind == "error":
        if isinstance(value, error_type):
            raise value
        raise error_type(
            service,
            type(value).__name__,
            error_code=type(value).__name__.upper(),
            duration_ms=duration_ms,
        ) from value
    return value


def _selected_context_count(m21: Any, workspace: Any, audit_id: str, max_pages: int) -> int:
    contexts = m21._audit_contexts(workspace, audit_id)
    ordered_page_ids: list[str] = []
    seen_page_ids: set[str] = set()
    for context in contexts:
        page_id = str(context["page_id"])
        if page_id not in seen_page_ids:
            seen_page_ids.add(page_id)
            ordered_page_ids.append(page_id)
    selected = set(ordered_page_ids if max_pages == 0 else ordered_page_ids[:max_pages])
    return sum(1 for context in contexts if str(context["page_id"]) in selected)


def _runtime_state() -> _M21ExecutionState | None:
    value = getattr(_STATE, "m21", None)
    return value if isinstance(value, _M21ExecutionState) else None


def _emit_request_started(
    *,
    service: str,
    url: str,
    device: str,
    timeout_seconds: float,
    target_navigation: bool,
) -> None:
    state = _runtime_state()
    if state is None:
        return
    context_index = state.begin_pagespeed() if service == "PAGESPEED_INSIGHTS" else state.current_context()
    try_append_operational_event(
        state.workspace,
        "M21_EXTERNAL_REQUEST_STARTED",
        audit_id=state.audit_id,
        service=service,
        url=url,
        device=device,
        context_index=context_index,
        context_total=state.context_total,
        timeout_seconds=float(timeout_seconds),
        retry_policy="NONE",
        measurement_scope="INDEPENDENT_EXTERNAL",
        target_navigation=bool(target_navigation),
        policy_version=POLICY_VERSION,
    )


def _emit_deadline(*, service: str, url: str, device: str, timeout_seconds: float) -> None:
    state = _runtime_state()
    if state is None:
        return
    try_append_operational_event(
        state.workspace,
        "M21_EXTERNAL_REQUEST_DEADLINE",
        level="WARNING",
        audit_id=state.audit_id,
        service=service,
        url=url,
        device=device,
        context_index=state.current_context(),
        context_total=state.context_total,
        timeout_seconds=float(timeout_seconds),
        retry_policy="NONE",
        policy_version=POLICY_VERSION,
    )


def _install_m21_policy() -> None:
    from rasai import cli as audit_cli
    from rasai import m21_web_performance as m21

    original_execute = m21.execute_m21
    if bool(getattr(original_execute, "_rasai_external_measurement_policy", False)):
        audit_cli.execute_m21 = original_execute
        return

    def pagespeed_run_once(
        self: Any,
        *,
        url: str,
        strategy: str,
        categories: tuple[str, ...],
        timeout_seconds: float,
    ) -> Any:
        _emit_request_started(
            service="PAGESPEED_INSIGHTS",
            url=url,
            device=str(strategy).upper(),
            timeout_seconds=timeout_seconds,
            target_navigation=True,
        )
        query: list[tuple[str, str]] = [("url", url), ("strategy", strategy), ("locale", "en")]
        query.extend(("category", category) for category in categories)
        if getattr(self, "_api_key", None):
            query.append(("key", str(self._api_key)))
        request = Request(
            f"{m21.PAGESPEED_ENDPOINT}?{urlencode(query)}",
            headers={"Accept": "application/json"},
        )
        try:
            return _run_with_wallclock_deadline(
                lambda: m21._request_json(
                    service="PAGESPEED_INSIGHTS",
                    request=request,
                    timeout_seconds=timeout_seconds,
                ),
                service="PAGESPEED_INSIGHTS",
                timeout_seconds=timeout_seconds,
                error_type=m21.ExternalServiceError,
            )
        except m21.ExternalServiceError as exc:
            if exc.error_code == "WALL_CLOCK_TIMEOUT":
                _emit_deadline(
                    service="PAGESPEED_INSIGHTS",
                    url=url,
                    device=str(strategy).upper(),
                    timeout_seconds=timeout_seconds,
                )
            raise

    def crux_query_once(
        self: Any,
        *,
        url: str,
        form_factor: str,
        timeout_seconds: float,
    ) -> Any:
        _emit_request_started(
            service="CRUX_API",
            url=url,
            device=str(form_factor).upper(),
            timeout_seconds=timeout_seconds,
            target_navigation=False,
        )
        endpoint = f"{m21.CRUX_ENDPOINT}?{urlencode({'key': self._api_key})}"
        body = json.dumps(
            {
                "url": url,
                "formFactor": form_factor,
                "metrics": list(m21._CRUX_METRICS),
            },
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            return _run_with_wallclock_deadline(
                lambda: m21._request_json(
                    service="CRUX_API",
                    request=request,
                    timeout_seconds=timeout_seconds,
                ),
                service="CRUX_API",
                timeout_seconds=timeout_seconds,
                error_type=m21.ExternalServiceError,
            )
        except m21.ExternalServiceError as exc:
            if exc.error_code == "WALL_CLOCK_TIMEOUT":
                _emit_deadline(
                    service="CRUX_API",
                    url=url,
                    device=str(form_factor).upper(),
                    timeout_seconds=timeout_seconds,
                )
            raise

    def execute_m21_bounded(*args: Any, **kwargs: Any) -> Any:
        config = kwargs.get("config")
        workspace = kwargs.get("workspace")
        audit_id = kwargs.get("audit_id")
        cfg = (config or m21.WebPerformanceConfig()).validate()
        total = 0
        if cfg.enabled and workspace is not None and audit_id is not None:
            total = _selected_context_count(m21, workspace, str(audit_id), cfg.max_pages)
            try_append_operational_event(
                workspace,
                "M21_EXTERNAL_PLAN",
                audit_id=str(audit_id),
                policy_version=POLICY_VERSION,
                contexts=total,
                pagespeed_calls_planned=total,
                pagespeed_retries=0,
                pagespeed_target_navigations_planned=total,
                crux_policy="FALLBACK_ONLY_WHEN_FIELD_DATA_MISSING_OR_EXPLICIT_CRUX",
                crux_target_navigations=0,
                core_snapshot_reused_as_input=True,
                externalized_after_core=True,
            )
        previous = getattr(_STATE, "m21", None)
        if workspace is not None and audit_id is not None:
            _STATE.m21 = _M21ExecutionState(str(audit_id), workspace, total)
        try:
            return original_execute(*args, **kwargs)
        finally:
            if previous is None:
                try:
                    delattr(_STATE, "m21")
                except AttributeError:
                    pass
            else:
                _STATE.m21 = previous

    setattr(execute_m21_bounded, "_rasai_external_measurement_policy", True)
    setattr(execute_m21_bounded, "_rasai_original", original_execute)
    m21.PageSpeedInsightsClient.run = pagespeed_run_once
    m21.CruxApiClient.query = crux_query_once
    m21._PAGESPEED_MAX_ATTEMPTS = 1
    m21.execute_m21 = execute_m21_bounded
    # cli.py imported execute_m21 by value; keep the runtime call site aligned.
    audit_cli.execute_m21 = execute_m21_bounded


def install() -> None:
    """Install bounded external-measurement behavior idempotently."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_m21_policy()
    _INSTALLED = True


def strategy_summary() -> dict[str, Any]:
    return {
        "version": POLICY_VERSION,
        "core_http": "ONE_DIRECT_HTTP_ACQUISITION_PER_URL",
        "core_browser": "ONE_BROWSER_NAVIGATION_PER_URL_DEVICE",
        "pagespeed": "ONE_INDEPENDENT_EXTERNAL_MEASUREMENT_PER_SELECTED_URL_DEVICE_NO_RETRY",
        "crux": "DATA_API_LOOKUP_NO_TARGET_NAVIGATION_FALLBACK_ONLY",
        "wallclock_deadline": "ENFORCED_PER_EXTERNAL_PROVIDER_CALL",
        "downstream_refetch": "FORBIDDEN_UNLESS_METRIC_CONTRACT_REQUIRES_INDEPENDENT_MEASUREMENT",
    }
