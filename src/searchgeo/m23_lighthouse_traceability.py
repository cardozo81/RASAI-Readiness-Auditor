"""Extract Lighthouse execution settings from already-persisted M21 artifacts.

This module performs no network calls for Lighthouse traceability and never
invents missing emulation or throttling settings. M25 hooks here only as an
additive one-shot synthetic domain before M23's standard samples.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any

from searchgeo.m23_persistence import LighthouseExecutionProfile, M23Persistence
from searchgeo.m25_runtime import execute_pending_m25
from searchgeo.operational_log import try_append_operational_event
from searchgeo.persistence import AuditWorkspace


@dataclass(frozen=True, slots=True)
class LighthouseTraceabilityResult:
    observations_considered: int
    profiles_extracted: int
    missing_artifacts: int
    invalid_artifacts: int


def extract_lighthouse_execution_profiles(*, audit_id: str, workspace: AuditWorkspace) -> LighthouseTraceabilityResult:
    # M25 is deliberately fail-open and has independent persistence/reporting.
    # The one-shot config is populated by the extended CLI. Running it here keeps
    # M23 Standard Apdex code and formula untouched while guaranteeing M25 runs
    # after the core audit has materialized pages/report and before M23 samples.
    execute_pending_m25(audit_id=audit_id, workspace=workspace)

    rows = _observations(workspace, audit_id)
    extracted = missing = invalid = 0
    if not rows:
        return LighthouseTraceabilityResult(0, 0, 0, 0)
    with M23Persistence(workspace) as store:
        for row in rows:
            reference = row["pagespeed_artifact_reference"]
            if not reference:
                missing += 1
                continue
            path = workspace.root / Path(str(reference))
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except OSError:
                missing += 1
                continue
            except (UnicodeDecodeError, json.JSONDecodeError):
                invalid += 1
                continue
            if not isinstance(payload, dict):
                invalid += 1
                continue
            parsed = _parse_profile(payload)
            crux_period = _crux_collection_period(workspace, row["crux_artifact_reference"])
            item = LighthouseExecutionProfile(
                observation_id=str(row["observation_id"]), audit_id=audit_id,
                device=str(row["device"]), url=str(row["url"]),
                form_factor=parsed.get("form_factor"),
                throttling_method=parsed.get("throttling_method"),
                rtt_ms=parsed.get("rtt_ms"), throughput_kbps=parsed.get("throughput_kbps"),
                request_latency_ms=parsed.get("request_latency_ms"),
                download_throughput_kbps=parsed.get("download_throughput_kbps"),
                upload_throughput_kbps=parsed.get("upload_throughput_kbps"),
                cpu_slowdown_multiplier=parsed.get("cpu_slowdown_multiplier"),
                screen_mobile=parsed.get("screen_mobile"), screen_width=parsed.get("screen_width"),
                screen_height=parsed.get("screen_height"),
                device_scale_factor=parsed.get("device_scale_factor"),
                screen_disabled=parsed.get("screen_disabled"),
                emulated_user_agent=parsed.get("emulated_user_agent"),
                host_user_agent=parsed.get("host_user_agent"),
                network_user_agent=parsed.get("network_user_agent"),
                benchmark_index=parsed.get("benchmark_index"),
                lighthouse_total_ms=parsed.get("lighthouse_total_ms"),
                collection_period_start=crux_period[0], collection_period_end=crux_period[1],
                raw_config=parsed.get("raw_config", {}), captured_at=_utc_now(),
            )
            store.upsert_lighthouse_profile(item)
            extracted += 1
            try_append_operational_event(
                workspace, "M23_LIGHTHOUSE_PROFILE_EXTRACTED", audit_id=audit_id,
                observation_id=item.observation_id, device=item.device, url=item.url,
                form_factor=item.form_factor, throttling_method=item.throttling_method,
                cpu_slowdown_multiplier=item.cpu_slowdown_multiplier,
                rtt_ms=item.rtt_ms, throughput_kbps=item.throughput_kbps,
                benchmark_index=item.benchmark_index,
            )
    return LighthouseTraceabilityResult(len(rows), extracted, missing, invalid)


def _observations(workspace: AuditWorkspace, audit_id: str) -> list[sqlite3.Row]:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        try:
            return list(connection.execute(
                """
                SELECT observation_id,device,url,pagespeed_artifact_reference,crux_artifact_reference
                FROM web_performance_observations
                WHERE audit_id=? ORDER BY device,url,observation_id
                """,
                (audit_id,),
            ).fetchall())
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc).lower():
                return []
            raise
    finally:
        connection.close()


def _parse_profile(payload: dict[str, Any]) -> dict[str, Any]:
    lighthouse = payload.get("lighthouseResult") if isinstance(payload.get("lighthouseResult"), dict) else {}
    config = lighthouse.get("configSettings") if isinstance(lighthouse.get("configSettings"), dict) else {}
    throttle = config.get("throttling") if isinstance(config.get("throttling"), dict) else {}
    screen = config.get("screenEmulation") if isinstance(config.get("screenEmulation"), dict) else {}
    environment = lighthouse.get("environment") if isinstance(lighthouse.get("environment"), dict) else {}
    timing = lighthouse.get("timing") if isinstance(lighthouse.get("timing"), dict) else {}
    return {
        "form_factor": _string(config.get("formFactor")),
        "throttling_method": _string(config.get("throttlingMethod")),
        "rtt_ms": _number(throttle.get("rttMs")),
        "throughput_kbps": _number(throttle.get("throughputKbps")),
        "request_latency_ms": _number(throttle.get("requestLatencyMs")),
        "download_throughput_kbps": _number(throttle.get("downloadThroughputKbps")),
        "upload_throughput_kbps": _number(throttle.get("uploadThroughputKbps")),
        "cpu_slowdown_multiplier": _number(throttle.get("cpuSlowdownMultiplier")),
        "screen_mobile": _boolean(screen.get("mobile")),
        "screen_width": _integer(screen.get("width")),
        "screen_height": _integer(screen.get("height")),
        "device_scale_factor": _number(screen.get("deviceScaleFactor")),
        "screen_disabled": _boolean(screen.get("disabled")),
        "emulated_user_agent": _string(config.get("emulatedUserAgent")),
        "host_user_agent": _string(environment.get("hostUserAgent")),
        "network_user_agent": _string(environment.get("networkUserAgent")),
        "benchmark_index": _number(environment.get("benchmarkIndex")),
        "lighthouse_total_ms": _number(timing.get("total")),
        "raw_config": config,
    }


def _crux_collection_period(workspace: AuditWorkspace, reference: Any) -> tuple[str | None, str | None]:
    if not reference:
        return None, None
    path = workspace.root / Path(str(reference))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    record = payload.get("record") if isinstance(payload, dict) else None
    period = record.get("collectionPeriod") if isinstance(record, dict) else None
    if not isinstance(period, dict):
        return None, None
    return _date(period.get("firstDate")), _date(period.get("lastDate"))


def _date(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    try:
        year, month, day = int(value["year"]), int(value["month"]), int(value["day"])
    except (KeyError, TypeError, ValueError):
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
