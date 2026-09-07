"""M21 external web performance evidence using PageSpeed Insights and CrUX."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from rasai.domain import DeviceContext, new_id
from rasai.m21_persistence import (
    M21Persistence,
    WebPerformanceAttempt,
    WebPerformanceObservation,
    WebPerformanceRun,
)
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace


PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
DEFAULT_CATEGORIES = ("performance", "accessibility", "best-practices", "seo")
ALLOWED_CATEGORIES = frozenset(DEFAULT_CATEGORIES)
FIELD_SOURCES = frozenset({"auto", "pagespeed", "crux", "none"})
_CRUX_METRICS = (
    "largest_contentful_paint",
    "interaction_to_next_paint",
    "cumulative_layout_shift",
)
_CWV_THRESHOLDS = {
    "largest_contentful_paint": 2500.0,
    "interaction_to_next_paint": 200.0,
    "cumulative_layout_shift": 0.1,
}


@dataclass(frozen=True, slots=True)
class WebPerformanceConfig:
    enabled: bool = False
    max_pages: int = 10
    timeout_seconds: float = 120.0
    categories: tuple[str, ...] = DEFAULT_CATEGORIES
    field_source: str = "auto"
    pagespeed_api_key: str | None = None
    crux_api_key: str | None = None

    def validate(self) -> "WebPerformanceConfig":
        if self.max_pages < 0:
            raise ValueError("web performance max_pages must be >= 0 (0 means all audited pages)")
        if not self.timeout_seconds > 0:
            raise ValueError("web performance timeout_seconds must be > 0")
        categories = tuple(dict.fromkeys(item.strip().casefold() for item in self.categories if item.strip()))
        if not categories:
            raise ValueError("at least one Lighthouse category is required")
        unknown = sorted(set(categories) - ALLOWED_CATEGORIES)
        if unknown:
            raise ValueError(f"unsupported Lighthouse categories: {', '.join(unknown)}")
        field_source = self.field_source.strip().casefold()
        if field_source not in FIELD_SOURCES:
            raise ValueError("field_source must be one of: auto, pagespeed, crux, none")
        if field_source == "crux" and not (self.crux_api_key or "").strip():
            raise ValueError("field_source=crux requires RASAI_CRUX_API_KEY")
        return WebPerformanceConfig(
            enabled=bool(self.enabled),
            max_pages=int(self.max_pages),
            timeout_seconds=float(self.timeout_seconds),
            categories=categories,
            field_source=field_source,
            pagespeed_api_key=(self.pagespeed_api_key or "").strip() or None,
            crux_api_key=(self.crux_api_key or "").strip() or None,
        )


@dataclass(frozen=True, slots=True)
class HttpJsonResult:
    payload: dict[str, Any]
    http_status: int
    duration_ms: int


class PageSpeedGateway(Protocol):
    def run(self, *, url: str, strategy: str, categories: tuple[str, ...], timeout_seconds: float) -> HttpJsonResult: ...


class CruxGateway(Protocol):
    def query(self, *, url: str, form_factor: str, timeout_seconds: float) -> HttpJsonResult: ...


class ExternalServiceError(RuntimeError):
    def __init__(self, service: str, message: str, *, http_status: int | None = None, error_code: str | None = None, duration_ms: int = 0) -> None:
        super().__init__(message)
        self.service = service
        self.http_status = http_status
        self.error_code = error_code
        self.duration_ms = duration_ms


class PageSpeedInsightsClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key or "").strip() or None

    def run(self, *, url: str, strategy: str, categories: tuple[str, ...], timeout_seconds: float) -> HttpJsonResult:
        query: list[tuple[str, str]] = [("url", url), ("strategy", strategy), ("locale", "en")]
        query.extend(("category", category) for category in categories)
        if self._api_key:
            query.append(("key", self._api_key))
        endpoint = f"{PAGESPEED_ENDPOINT}?{urlencode(query)}"
        return _request_json(
            service="PAGESPEED_INSIGHTS",
            request=Request(endpoint, headers={"Accept": "application/json"}),
            timeout_seconds=timeout_seconds,
        )


class CruxApiClient:
    def __init__(self, api_key: str) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError("CrUX API key must not be empty")
        self._api_key = key

    def query(self, *, url: str, form_factor: str, timeout_seconds: float) -> HttpJsonResult:
        endpoint = f"{CRUX_ENDPOINT}?{urlencode({'key': self._api_key})}"
        body = json.dumps(
            {"url": url, "formFactor": form_factor, "metrics": list(_CRUX_METRICS)},
            separators=(",", ":"),
        ).encode("utf-8")
        return _request_json(
            service="CRUX_API",
            request=Request(endpoint, data=body, method="POST", headers={"Accept": "application/json", "Content-Type": "application/json"}),
            timeout_seconds=timeout_seconds,
        )


@dataclass(frozen=True, slots=True)
class M21ExecutionResult:
    status: str
    enabled: bool
    pages_considered: int
    context_attempts: int
    successful_contexts: int
    pagespeed_attempts: int
    pagespeed_successes: int
    crux_attempts: int
    crux_successes: int
    partial_contexts: int
    observation_ids: tuple[str, ...]


def execute_m21(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    config: WebPerformanceConfig | None = None,
    pagespeed_client: PageSpeedGateway | None = None,
    crux_client: CruxGateway | None = None,
) -> M21ExecutionResult:
    """Collect external lab/field performance evidence without changing SCORE-GEO-002."""
    cfg = (config or WebPerformanceConfig()).validate()
    now = _utc_now()
    try_append_operational_event(
        workspace,
        "M21_STARTED",
        audit_id=audit_id,
        enabled=cfg.enabled,
        field_source=cfg.field_source,
        max_pages=cfg.max_pages,
        timeout_seconds=cfg.timeout_seconds,
        categories=cfg.categories,
        pagespeed_api_key_configured=bool(cfg.pagespeed_api_key),
        crux_api_key_configured=bool(cfg.crux_api_key),
    )

    with M21Persistence(workspace) as store:
        if not cfg.enabled:
            store.upsert_run(WebPerformanceRun(
                audit_id=audit_id, enabled=False, status="DISABLED", field_source=cfg.field_source,
                page_limit=cfg.max_pages, pages_considered=0, context_attempts=0, successful_contexts=0,
                pagespeed_successes=0, crux_successes=0, categories=cfg.categories,
                reason="EXTERNAL_WEB_PERFORMANCE_DISABLED", updated_at=now,
            ))
            try_append_operational_event(
                workspace,
                "M21_COMPLETED",
                audit_id=audit_id,
                status="DISABLED",
                reason="EXTERNAL_WEB_PERFORMANCE_DISABLED",
                pages_considered=0,
                context_attempts=0,
                successful_contexts=0,
                partial_contexts=0,
                pagespeed_attempts=0,
                pagespeed_successes=0,
                crux_attempts=0,
                crux_successes=0,
            )
            return M21ExecutionResult(
                status="DISABLED",
                enabled=False,
                pages_considered=0,
                context_attempts=0,
                successful_contexts=0,
                pagespeed_attempts=0,
                pagespeed_successes=0,
                crux_attempts=0,
                crux_successes=0,
                partial_contexts=0,
                observation_ids=(),
            )

        psi = pagespeed_client or PageSpeedInsightsClient(cfg.pagespeed_api_key)
        crux = crux_client
        if crux is None and cfg.crux_api_key:
            crux = CruxApiClient(cfg.crux_api_key)

        contexts = _audit_contexts(workspace, audit_id)
        ordered_page_ids: list[str] = []
        seen_page_ids: set[str] = set()
        for context in contexts:
            if context["page_id"] not in seen_page_ids:
                seen_page_ids.add(context["page_id"])
                ordered_page_ids.append(context["page_id"])
        selected_page_ids = set(ordered_page_ids if cfg.max_pages == 0 else ordered_page_ids[: cfg.max_pages])
        contexts = [context for context in contexts if context["page_id"] in selected_page_ids]

        attempts = successes = 0
        psi_attempts = psi_successes = 0
        crux_attempts = crux_successes = 0
        partial_contexts = 0
        observation_ids: list[str] = []

        for context in contexts:
            normalized_url = str(context["normalized_url"])
            page_id = str(context["page_id"])
            snapshot_id = str(context["snapshot_id"])
            device = DeviceContext(str(context["device"]))
            attempts += 1
            url = str(context["final_url"] or normalized_url)
            strategy = "mobile" if device is DeviceContext.MOBILE else "desktop"
            form_factor = "PHONE" if device is DeviceContext.MOBILE else "DESKTOP"
            observation_id = new_id("WPE")
            psi_payload: dict[str, Any] | None = None
            psi_artifact: str | None = None
            crux_artifact: str | None = None
            errors: list[str] = []
            psi_http_status: int | None = None
            crux_http_status: int | None = None

            psi_attempts += 1
            try:
                response = psi.run(url=url, strategy=strategy, categories=cfg.categories, timeout_seconds=cfg.timeout_seconds)
                psi_payload = response.payload
                psi_http_status = response.http_status
                psi_successes += 1
                psi_artifact = _write_json_artifact(workspace, observation_id, "pagespeed", psi_payload)
                store.add_attempt(WebPerformanceAttempt(
                    attempt_id=new_id("WPA"), audit_id=audit_id, page_id=page_id, snapshot_id=snapshot_id,
                    device=device.value, url=url, service="PAGESPEED_INSIGHTS", status="SUCCESS",
                    http_status=response.http_status, duration_ms=response.duration_ms, error_code=None,
                    error_message=None, artifact_reference=psi_artifact, created_at=_utc_now(),
                ))
                try_append_operational_event(
                    workspace,
                    "M21_EXTERNAL_ATTEMPT",
                    audit_id=audit_id,
                    service="PAGESPEED_INSIGHTS",
                    status="SUCCESS",
                    url=url,
                    device=device.value,
                    http_status=response.http_status,
                    duration_ms=response.duration_ms,
                    artifact_reference=psi_artifact,
                )
            except ExternalServiceError as exc:
                errors.append(f"PAGESPEED:{exc.error_code or exc.http_status or 'ERROR'}")
                store.add_attempt(WebPerformanceAttempt(
                    attempt_id=new_id("WPA"), audit_id=audit_id, page_id=page_id, snapshot_id=snapshot_id,
                    device=device.value, url=url, service="PAGESPEED_INSIGHTS", status="ERROR",
                    http_status=exc.http_status, duration_ms=exc.duration_ms, error_code=exc.error_code,
                    error_message=_bounded(str(exc), 512), artifact_reference=None, created_at=_utc_now(),
                ))
                try_append_operational_event(
                    workspace,
                    "M21_EXTERNAL_ATTEMPT",
                    level="WARNING",
                    audit_id=audit_id,
                    service="PAGESPEED_INSIGHTS",
                    status="ERROR",
                    url=url,
                    device=device.value,
                    http_status=exc.http_status,
                    duration_ms=exc.duration_ms,
                    error_code=exc.error_code,
                    error_message=_bounded(str(exc), 512),
                )

            field_data, field_source, field_scope = _field_from_pagespeed(psi_payload)
            direct_crux_requested = cfg.field_source == "crux" or (cfg.field_source == "auto" and field_data is None and crux is not None)
            if cfg.field_source == "none":
                field_data, field_source, field_scope = None, None, None
            elif cfg.field_source == "crux":
                field_data, field_source, field_scope = None, None, None

            if direct_crux_requested and crux is not None:
                crux_attempts += 1
                try:
                    response = crux.query(url=url, form_factor=form_factor, timeout_seconds=cfg.timeout_seconds)
                    crux_payload = response.payload
                    crux_http_status = response.http_status
                    crux_successes += 1
                    crux_artifact = _write_json_artifact(workspace, observation_id, "crux", crux_payload)
                    store.add_attempt(WebPerformanceAttempt(
                        attempt_id=new_id("WPA"), audit_id=audit_id, page_id=page_id, snapshot_id=snapshot_id,
                        device=device.value, url=url, service="CRUX_API", status="SUCCESS",
                        http_status=response.http_status, duration_ms=response.duration_ms, error_code=None,
                        error_message=None, artifact_reference=crux_artifact, created_at=_utc_now(),
                    ))
                    try_append_operational_event(
                        workspace,
                        "M21_EXTERNAL_ATTEMPT",
                        audit_id=audit_id,
                        service="CRUX_API",
                        status="SUCCESS",
                        url=url,
                        device=device.value,
                        http_status=response.http_status,
                        duration_ms=response.duration_ms,
                        artifact_reference=crux_artifact,
                    )
                    parsed = _field_from_crux(crux_payload)
                    if parsed is not None:
                        field_data, field_source, field_scope = parsed, "CRUX_API", _crux_scope(crux_payload)
                except ExternalServiceError as exc:
                    errors.append(f"CRUX:{exc.error_code or exc.http_status or 'ERROR'}")
                    store.add_attempt(WebPerformanceAttempt(
                        attempt_id=new_id("WPA"), audit_id=audit_id, page_id=page_id, snapshot_id=snapshot_id,
                        device=device.value, url=url, service="CRUX_API", status="ERROR",
                        http_status=exc.http_status, duration_ms=exc.duration_ms, error_code=exc.error_code,
                        error_message=_bounded(str(exc), 512), artifact_reference=None, created_at=_utc_now(),
                    ))
                    try_append_operational_event(
                        workspace,
                        "M21_EXTERNAL_ATTEMPT",
                        level="WARNING",
                        audit_id=audit_id,
                        service="CRUX_API",
                        status="ERROR",
                        url=url,
                        device=device.value,
                        http_status=exc.http_status,
                        duration_ms=exc.duration_ms,
                        error_code=exc.error_code,
                        error_message=_bounded(str(exc), 512),
                    )
            elif cfg.field_source == "crux" and crux is None:
                errors.append("CRUX:NOT_CONFIGURED")
                try_append_operational_event(
                    workspace,
                    "M21_EXTERNAL_ATTEMPT",
                    level="WARNING",
                    audit_id=audit_id,
                    service="CRUX_API",
                    status="NOT_CONFIGURED",
                    url=url,
                    device=device.value,
                )

            lab = _parse_lighthouse(psi_payload)
            cwv = _assess_cwv(field_data)
            has_lab = any(lab.get(key) is not None for key in ("performance_score", "fcp_lab_ms", "lcp_lab_ms", "tbt_lab_ms", "cls_lab"))
            has_field = field_data is not None and any(field_data.get(key) is not None for key in ("lcp_p75_ms", "inp_p75_ms", "cls_p75"))
            if has_lab or has_field:
                successes += 1
                status = "SUCCESS" if not errors else "PARTIAL"
            else:
                status = "UNAVAILABLE"
            if status == "PARTIAL":
                partial_contexts += 1

            store.add_observation(WebPerformanceObservation(
                observation_id=observation_id, audit_id=audit_id, page_id=page_id, snapshot_id=snapshot_id,
                device=device.value, url=url, strategy=strategy, status=status,
                lighthouse_version=lab.get("lighthouse_version"), lighthouse_fetch_time=lab.get("lighthouse_fetch_time"),
                performance_score=lab.get("performance_score"), accessibility_score=lab.get("accessibility_score"),
                best_practices_score=lab.get("best_practices_score"), seo_score=lab.get("seo_score"),
                fcp_lab_ms=lab.get("fcp_lab_ms"), speed_index_lab_ms=lab.get("speed_index_lab_ms"),
                lcp_lab_ms=lab.get("lcp_lab_ms"), tbt_lab_ms=lab.get("tbt_lab_ms"), cls_lab=lab.get("cls_lab"),
                field_source=field_source, field_scope=field_scope,
                lcp_p75_ms=(field_data or {}).get("lcp_p75_ms"), inp_p75_ms=(field_data or {}).get("inp_p75_ms"),
                cls_p75=(field_data or {}).get("cls_p75"), lcp_assessment=cwv.get("lcp_assessment"),
                inp_assessment=cwv.get("inp_assessment"), cls_assessment=cwv.get("cls_assessment"),
                cwv_assessment=cwv.get("cwv_assessment") or "UNAVAILABLE",
                pagespeed_http_status=psi_http_status, crux_http_status=crux_http_status,
                pagespeed_artifact_reference=psi_artifact, crux_artifact_reference=crux_artifact,
                error_summary=";".join(errors) if errors else None, captured_at=_utc_now(),
            ))
            observation_ids.append(observation_id)

        if attempts == 0:
            run_status, reason = "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
        elif successes == 0:
            run_status, reason = "UNAVAILABLE", "EXTERNAL_WEB_PERFORMANCE_UNAVAILABLE"
        elif partial_contexts > 0 or successes < attempts:
            run_status, reason = "PARTIAL", "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE"
        else:
            run_status, reason = "SUCCESS", None

        store.upsert_run(WebPerformanceRun(
            audit_id=audit_id, enabled=True, status=run_status, field_source=cfg.field_source,
            page_limit=cfg.max_pages, pages_considered=len(selected_page_ids), context_attempts=attempts,
            successful_contexts=successes, pagespeed_successes=psi_successes, crux_successes=crux_successes,
            categories=cfg.categories, reason=reason, updated_at=_utc_now(),
        ))

    try_append_operational_event(
        workspace,
        "M21_COMPLETED",
        audit_id=audit_id,
        status=run_status,
        reason=reason,
        pages_considered=len(selected_page_ids),
        context_attempts=attempts,
        successful_contexts=successes,
        partial_contexts=partial_contexts,
        pagespeed_attempts=psi_attempts,
        pagespeed_successes=psi_successes,
        crux_attempts=crux_attempts,
        crux_successes=crux_successes,
    )
    return M21ExecutionResult(
        status=run_status,
        enabled=True,
        pages_considered=len(selected_page_ids),
        context_attempts=attempts,
        successful_contexts=successes,
        pagespeed_attempts=psi_attempts,
        pagespeed_successes=psi_successes,
        crux_attempts=crux_attempts,
        crux_successes=crux_successes,
        partial_contexts=partial_contexts,
        observation_ids=tuple(observation_ids),
    )


def _audit_contexts(workspace: AuditWorkspace, audit_id: str) -> list[dict[str, Any]]:
    import sqlite3
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT p.page_id,p.normalized_url,s.snapshot_id,s.device,s.final_url
            FROM pages p JOIN page_snapshots s ON s.page_id=p.page_id
            WHERE p.audit_id=? ORDER BY p.normalized_url,p.page_id,s.device,s.snapshot_id
            """,
            (audit_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def _request_json(*, service: str, request: Request, timeout_seconds: float) -> HttpJsonResult:
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        duration = int((time.monotonic() - started) * 1000)
        try:
            body = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(body)
            message = parsed.get("error", {}).get("message") if isinstance(parsed, dict) else None
            code = parsed.get("error", {}).get("status") if isinstance(parsed, dict) else None
        except Exception:
            message = code = None
        raise ExternalServiceError(service, _bounded(message or f"HTTP {exc.code}", 512), http_status=exc.code, error_code=_bounded(str(code), 96) if code else None, duration_ms=duration) from exc
    except (URLError, TimeoutError, OSError) as exc:
        duration = int((time.monotonic() - started) * 1000)
        raise ExternalServiceError(service, _bounded(type(exc).__name__, 96), error_code=type(exc).__name__.upper(), duration_ms=duration) from exc
    duration = int((time.monotonic() - started) * 1000)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalServiceError(service, "INVALID_JSON_RESPONSE", http_status=status, error_code="INVALID_JSON", duration_ms=duration) from exc
    if not isinstance(payload, dict):
        raise ExternalServiceError(service, "INVALID_JSON_OBJECT", http_status=status, error_code="INVALID_JSON_OBJECT", duration_ms=duration)
    return HttpJsonResult(payload=payload, http_status=status, duration_ms=duration)


def _write_json_artifact(workspace: AuditWorkspace, observation_id: str, source: str, payload: dict[str, Any]) -> str:
    relative = Path("artifacts") / "web-performance" / f"{observation_id}.{source}.json"
    path = workspace.root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return relative.as_posix()


def _parse_lighthouse(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload.get("lighthouseResult"), dict):
        return {}
    result = payload["lighthouseResult"]
    categories = result.get("categories") if isinstance(result.get("categories"), dict) else {}
    audits = result.get("audits") if isinstance(result.get("audits"), dict) else {}

    def category_score(name: str) -> float | None:
        item = categories.get(name)
        value = _float(item.get("score")) if isinstance(item, dict) else None
        return round(value * 100.0, 2) if value is not None else None

    def numeric(audit_id: str) -> float | None:
        item = audits.get(audit_id)
        return _float(item.get("numericValue")) if isinstance(item, dict) else None

    return {
        "lighthouse_version": _string(result.get("lighthouseVersion")),
        "lighthouse_fetch_time": _string(result.get("fetchTime")),
        "performance_score": category_score("performance"),
        "accessibility_score": category_score("accessibility"),
        "best_practices_score": category_score("best-practices"),
        "seo_score": category_score("seo"),
        "fcp_lab_ms": numeric("first-contentful-paint"),
        "speed_index_lab_ms": numeric("speed-index"),
        "lcp_lab_ms": numeric("largest-contentful-paint"),
        "tbt_lab_ms": numeric("total-blocking-time"),
        "cls_lab": numeric("cumulative-layout-shift"),
    }


def _field_from_pagespeed(payload: dict[str, Any] | None) -> tuple[dict[str, float | None] | None, str | None, str | None]:
    if not payload:
        return None, None, None
    for key, scope in (("loadingExperience", "URL"), ("originLoadingExperience", "ORIGIN")):
        experience = payload.get(key)
        if not isinstance(experience, dict) or not isinstance(experience.get("metrics"), dict) or not experience["metrics"]:
            continue
        metrics = experience["metrics"]
        lcp = _psi_percentile(metrics, ("LARGEST_CONTENTFUL_PAINT_MS",))
        inp = _psi_percentile(metrics, ("INTERACTION_TO_NEXT_PAINT", "INTERACTION_TO_NEXT_PAINT_MS"))
        cls_raw = _psi_percentile(metrics, ("CUMULATIVE_LAYOUT_SHIFT_SCORE",))
        cls = cls_raw / 100.0 if cls_raw is not None else None
        if any(value is not None for value in (lcp, inp, cls)):
            actual_scope = "ORIGIN" if bool(experience.get("origin_fallback")) else scope
            return {"lcp_p75_ms": lcp, "inp_p75_ms": inp, "cls_p75": cls}, "PAGESPEED_CRUX", actual_scope
    return None, None, None


def _psi_percentile(metrics: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        item = metrics.get(key)
        if isinstance(item, dict):
            value = _float(item.get("percentile"))
            if value is not None:
                return value
    return None


def _field_from_crux(payload: dict[str, Any] | None) -> dict[str, float | None] | None:
    record = payload.get("record") if payload else None
    metrics = record.get("metrics") if isinstance(record, dict) else None
    if not isinstance(metrics, dict):
        return None
    values = {
        "lcp_p75_ms": _crux_p75(metrics.get("largest_contentful_paint")),
        "inp_p75_ms": _crux_p75(metrics.get("interaction_to_next_paint")),
        "cls_p75": _crux_p75(metrics.get("cumulative_layout_shift")),
    }
    return values if any(value is not None for value in values.values()) else None


def _crux_scope(payload: dict[str, Any]) -> str | None:
    record = payload.get("record")
    key = record.get("key") if isinstance(record, dict) else None
    if not isinstance(key, dict):
        return None
    return "URL" if key.get("url") else "ORIGIN" if key.get("origin") else None


def _crux_p75(metric: Any) -> float | None:
    percentiles = metric.get("percentiles") if isinstance(metric, dict) else None
    return _float(percentiles.get("p75")) if isinstance(percentiles, dict) else None


def _assess_cwv(field: dict[str, float | None] | None) -> dict[str, str | None]:
    if not field:
        return {"lcp_assessment": None, "inp_assessment": None, "cls_assessment": None, "cwv_assessment": "UNAVAILABLE"}

    def assess(value: float | None, threshold: float) -> str | None:
        return None if value is None else "GOOD" if value <= threshold else "NEEDS_IMPROVEMENT_OR_POOR"

    lcp = assess(field.get("lcp_p75_ms"), _CWV_THRESHOLDS["largest_contentful_paint"])
    inp = assess(field.get("inp_p75_ms"), _CWV_THRESHOLDS["interaction_to_next_paint"])
    cls = assess(field.get("cls_p75"), _CWV_THRESHOLDS["cumulative_layout_shift"])
    components = (lcp, inp, cls)
    overall = "INCOMPLETE" if any(value is None for value in components) else "PASS" if all(value == "GOOD" for value in components) else "FAIL"
    return {"lcp_assessment": lcp, "inp_assessment": inp, "cls_assessment": cls, "cwv_assessment": overall}


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _bounded(value: str, limit: int) -> str:
    return value[:limit]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
