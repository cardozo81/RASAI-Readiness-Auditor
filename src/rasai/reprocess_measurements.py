"""Selective recovery for live M21/M23/M25 work-items.

Successful external calls and valid synthetic samples are never repeated. Recovery
only acquires the missing effective evidence needed by the original configuration.
Historical failures remain persisted for cost/reliability/operational analysis.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from rasai.audit_fulfillment import WorkItem
from rasai.domain import DeviceContext, new_id
from rasai.persistence import AuditWorkspace


def _json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _read_artifact(workspace: AuditWorkspace, reference: str | None) -> dict[str, Any] | None:
    if not reference:
        return None
    path = workspace.root / str(reference)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return dict(value) if isinstance(value, dict) else None


def _last_success_attempt(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    snapshot_id: str,
    service: str,
) -> sqlite3.Row | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """SELECT * FROM web_performance_attempts
               WHERE audit_id=? AND snapshot_id=? AND service=? AND status='SUCCESS'
               ORDER BY created_at DESC,rowid DESC LIMIT 1""",
            (audit_id, snapshot_id, service),
        ).fetchone()
    finally:
        connection.close()


def recover_web_performance(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
) -> bool:
    """Retry only unresolved PageSpeed/CrUX service calls per existing snapshot."""
    from rasai import m21_web_performance as m21
    from rasai.m21_persistence import (
        M21Persistence,
        WebPerformanceAttempt,
        WebPerformanceObservation,
        WebPerformanceRun,
    )

    cfg_map = dict(item.configuration)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            "SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,)
        ).fetchone()
        if run is not None:
            persisted_categories = tuple(_json_load(run["categories"], []))
            cfg_map.setdefault("max_pages", int(run["page_limit"]))
            cfg_map.setdefault("field_source", str(run["field_source"]))
            if persisted_categories:
                cfg_map.setdefault("categories", list(persisted_categories))
    finally:
        connection.close()

    cfg = m21.WebPerformanceConfig(
        enabled=True,
        max_pages=int(cfg_map.get("max_pages", cfg_map.get("page_limit", 10)) or 0),
        timeout_seconds=float(cfg_map.get("timeout_seconds", 120.0) or 120.0),
        categories=tuple(cfg_map.get("categories") or m21.DEFAULT_CATEGORIES),
        field_source=str(cfg_map.get("field_source") or "auto"),
        pagespeed_api_key=(os.getenv("RASAI_PAGESPEED_API_KEY") or "").strip() or None,
        crux_api_key=(os.getenv("RASAI_CRUX_API_KEY") or "").strip() or None,
    ).validate()
    psi = m21.PageSpeedInsightsClient(cfg.pagespeed_api_key)
    crux = m21.CruxApiClient(cfg.crux_api_key) if cfg.crux_api_key else None
    contexts = m21._audit_contexts(workspace, audit_id)
    ordered_pages: list[str] = []
    for context in contexts:
        page_id = str(context["page_id"])
        if page_id not in ordered_pages:
            ordered_pages.append(page_id)
    selected = set(ordered_pages if cfg.max_pages == 0 else ordered_pages[: cfg.max_pages])
    contexts = [row for row in contexts if str(row["page_id"]) in selected]
    successful_contexts = 0
    effective_psi_successes = 0
    effective_crux_successes = 0
    partial_contexts = 0

    with M21Persistence(workspace) as store:
        for context in contexts:
            page_id = str(context["page_id"])
            snapshot_id = str(context["snapshot_id"])
            device = DeviceContext(str(context["device"]))
            url = str(context["final_url"] or context["normalized_url"])
            strategy = "mobile" if device is DeviceContext.MOBILE else "desktop"
            form_factor = "PHONE" if device is DeviceContext.MOBILE else "DESKTOP"
            observation_id = new_id("WPE")
            errors: list[str] = []

            psi_row = _last_success_attempt(
                workspace,audit_id=audit_id,snapshot_id=snapshot_id,service="PAGESPEED_INSIGHTS"
            )
            psi_payload = _read_artifact(workspace, psi_row["artifact_reference"] if psi_row else None)
            psi_artifact = str(psi_row["artifact_reference"]) if psi_row and psi_payload is not None else None
            psi_http_status = int(psi_row["http_status"]) if psi_row and psi_row["http_status"] is not None and psi_payload is not None else None
            if psi_payload is None:
                try:
                    response = psi.run(url=url,strategy=strategy,categories=cfg.categories,timeout_seconds=cfg.timeout_seconds)
                    psi_payload = response.payload
                    psi_http_status = response.http_status
                    psi_artifact = m21._write_json_artifact(workspace, observation_id, "pagespeed", psi_payload)
                    store.add_attempt(WebPerformanceAttempt(
                        attempt_id=new_id("WPA"),audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                        device=device.value,url=url,service="PAGESPEED_INSIGHTS",status="SUCCESS",
                        http_status=response.http_status,duration_ms=response.duration_ms,error_code=None,
                        error_message=None,artifact_reference=psi_artifact,created_at=m21._utc_now(),
                    ))
                except m21.ExternalServiceError as exc:
                    errors.append(f"PAGESPEED:{exc.error_code or exc.http_status or 'ERROR'}")
                    store.add_attempt(WebPerformanceAttempt(
                        attempt_id=new_id("WPA"),audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                        device=device.value,url=url,service="PAGESPEED_INSIGHTS",status="ERROR",
                        http_status=exc.http_status,duration_ms=exc.duration_ms,error_code=exc.error_code,
                        error_message=m21._bounded(str(exc),512),artifact_reference=None,created_at=m21._utc_now(),
                    ))
            if psi_payload is not None:
                effective_psi_successes += 1

            field_data, field_source, field_scope = m21._field_from_pagespeed(psi_payload)
            if cfg.field_source == "none":
                field_data, field_source, field_scope = None, None, None
            elif cfg.field_source == "crux":
                field_data, field_source, field_scope = None, None, None

            crux_row = _last_success_attempt(
                workspace,audit_id=audit_id,snapshot_id=snapshot_id,service="CRUX_API"
            )
            crux_payload = _read_artifact(workspace, crux_row["artifact_reference"] if crux_row else None)
            prior_crux_success = crux_payload is not None
            was_crux_configured = bool(cfg_map.get("crux_key_configured"))
            direct_crux_required = (
                cfg.field_source == "crux"
                or (cfg.field_source == "auto" and field_data is None and (crux is not None or prior_crux_success or was_crux_configured))
            )
            crux_artifact = str(crux_row["artifact_reference"]) if crux_row and prior_crux_success else None
            crux_http_status = int(crux_row["http_status"]) if crux_row and crux_row["http_status"] is not None and prior_crux_success else None
            if direct_crux_required:
                if crux_payload is None and crux is not None:
                    try:
                        response = crux.query(url=url,form_factor=form_factor,timeout_seconds=cfg.timeout_seconds)
                        crux_payload = response.payload
                        crux_http_status = response.http_status
                        crux_artifact = m21._write_json_artifact(workspace, observation_id, "crux", crux_payload)
                        store.add_attempt(WebPerformanceAttempt(
                            attempt_id=new_id("WPA"),audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                            device=device.value,url=url,service="CRUX_API",status="SUCCESS",
                            http_status=response.http_status,duration_ms=response.duration_ms,error_code=None,
                            error_message=None,artifact_reference=crux_artifact,created_at=m21._utc_now(),
                        ))
                    except m21.ExternalServiceError as exc:
                        errors.append(f"CRUX:{exc.error_code or exc.http_status or 'ERROR'}")
                        store.add_attempt(WebPerformanceAttempt(
                            attempt_id=new_id("WPA"),audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                            device=device.value,url=url,service="CRUX_API",status="ERROR",
                            http_status=exc.http_status,duration_ms=exc.duration_ms,error_code=exc.error_code,
                            error_message=m21._bounded(str(exc),512),artifact_reference=None,created_at=m21._utc_now(),
                        ))
                if crux_payload is None:
                    errors.append("CRUX:NOT_CONFIGURED" if crux is None else "CRUX:UNAVAILABLE")
                else:
                    parsed = m21._field_from_crux(crux_payload)
                    if parsed is not None:
                        field_data, field_source, field_scope = parsed, "CRUX_API", m21._crux_scope(crux_payload)
                        effective_crux_successes += 1

            lab = m21._parse_lighthouse(psi_payload)
            cwv = m21._assess_cwv(field_data)
            has_lab = any(
                lab.get(key) is not None
                for key in (
                    "performance_score","accessibility_score","best_practices_score","seo_score",
                    "agentic_browsing_score","fcp_lab_ms","lcp_lab_ms","tbt_lab_ms","cls_lab",
                )
            )
            has_field = field_data is not None and any(
                field_data.get(key) is not None for key in ("lcp_p75_ms","inp_p75_ms","cls_p75")
            )
            if (has_lab or has_field) and not errors:
                status = "SUCCESS"
                successful_contexts += 1
            elif has_lab or has_field:
                status = "PARTIAL"
                partial_contexts += 1
            else:
                status = "UNAVAILABLE"

            store.add_observation(WebPerformanceObservation(
                observation_id=observation_id,audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                device=device.value,url=url,strategy=strategy,status=status,
                lighthouse_version=lab.get("lighthouse_version"),lighthouse_fetch_time=lab.get("lighthouse_fetch_time"),
                performance_score=lab.get("performance_score"),accessibility_score=lab.get("accessibility_score"),
                best_practices_score=lab.get("best_practices_score"),seo_score=lab.get("seo_score"),
                agentic_browsing_score=lab.get("agentic_browsing_score"),fcp_lab_ms=lab.get("fcp_lab_ms"),
                speed_index_lab_ms=lab.get("speed_index_lab_ms"),lcp_lab_ms=lab.get("lcp_lab_ms"),
                tbt_lab_ms=lab.get("tbt_lab_ms"),cls_lab=lab.get("cls_lab"),field_source=field_source,
                field_scope=field_scope,lcp_p75_ms=(field_data or {}).get("lcp_p75_ms"),
                inp_p75_ms=(field_data or {}).get("inp_p75_ms"),cls_p75=(field_data or {}).get("cls_p75"),
                lcp_assessment=cwv.get("lcp_assessment"),inp_assessment=cwv.get("inp_assessment"),
                cls_assessment=cwv.get("cls_assessment"),cwv_assessment=cwv.get("cwv_assessment") or "UNAVAILABLE",
                pagespeed_http_status=psi_http_status,crux_http_status=crux_http_status,
                pagespeed_artifact_reference=psi_artifact,crux_artifact_reference=crux_artifact,
                error_summary=";".join(dict.fromkeys(errors)) if errors else None,captured_at=m21._utc_now(),
            ))

        if not contexts:
            run_status, reason = "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
        elif successful_contexts == len(contexts):
            run_status, reason = "SUCCESS", None
        elif successful_contexts or partial_contexts:
            run_status, reason = "PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE"
        else:
            run_status, reason = "UNAVAILABLE", "NO_SUCCESSFUL_WEB_PERFORMANCE_CONTEXTS"
        store.upsert_run(WebPerformanceRun(
            audit_id=audit_id,enabled=True,status=run_status,field_source=cfg.field_source,page_limit=cfg.max_pages,
            pages_considered=len({str(row["page_id"]) for row in contexts}),context_attempts=len(contexts),
            successful_contexts=successful_contexts,pagespeed_successes=effective_psi_successes,
            crux_successes=effective_crux_successes,categories=cfg.categories,reason=reason,updated_at=m21._utc_now(),
        ))
    return bool(contexts) and successful_contexts == len(contexts)


def _profile_from_persisted(value: Any, *, device: str):
    from rasai.m23_apdex_profiles import (
        DESKTOP_STANDARD_PROFILE,
        MOBILE_STANDARD_PROFILE,
        profile_from_presets,
    )
    data = _json_load(value, {})
    if isinstance(data, dict):
        client = data.get("client_profile_id")
        hardware = data.get("hardware_profile_id")
        network = data.get("network_profile_id")
        if client and hardware and network:
            try:
                return profile_from_presets(
                    device=device,client_profile_id=str(client),hardware_profile_id=str(hardware),network_profile_id=str(network)
                )
            except (KeyError, TypeError, ValueError):
                pass
    return MOBILE_STANDARD_PROFILE if device.upper() == "MOBILE" else DESKTOP_STANDARD_PROFILE


def _m23_item_from_row(row: sqlite3.Row):
    from rasai.m23_apdex import _MeasuredSample
    from rasai.m23_apdex_profiles import NavigationMeasurement
    diagnostics = _json_load(row["browser_diagnostics"], {})
    events = diagnostics.get("events", []) if isinstance(diagnostics, dict) else []
    measurement = NavigationMeasurement(
        status=str(row["status"]),duration_ms=row["duration_ms"],http_status=row["http_status"],
        final_url=row["final_url"],error_code=row["error_code"],error_message=row["error_message"],
        profile_applied=bool(row["classification"] is not None),cpu_method=row["cpu_method"],
        network_method=row["network_method"],browser_diagnostics=tuple(dict(item) for item in events if isinstance(item,dict)),
    )
    return _MeasuredSample(int(row["run_index"]), measurement, row["classification"])


def recover_synthetic_apdex(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
) -> bool:
    """Append only the valid-sample deficit for each M23 context."""
    from rasai import m23_apdex as m23
    from rasai.m23_apdex_profiles import PlaywrightSyntheticNavigationGateway, PROFILE_VERSION, static_host_environment
    from rasai.m23_persistence import M23Persistence, SyntheticApdexRun, SyntheticApdexSample

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute("SELECT * FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,)).fetchone()
        if run is None or not bool(run["enabled"]):
            return False
        persisted_cfg = _json_load(run["configuration"], {})
        mobile = _profile_from_persisted((persisted_cfg or {}).get("mobile_profile"), device="MOBILE")
        desktop = _profile_from_persisted((persisted_cfg or {}).get("desktop_profile"), device="DESKTOP")
        cfg = m23.SyntheticApdexConfig(
            enabled=True,threshold_seconds=float(run["threshold_seconds"]),
            target_valid_samples=int(run["target_valid_samples"]),
            max_attempts_per_context=int(run["max_attempts_per_context"]),max_pages=int(run["page_limit"]),
            timeout_seconds=float(item.configuration.get("timeout_seconds", 45.0) or 45.0),
            delay_seconds=float(run["delay_seconds"]),concurrency=1,mobile_profile=mobile,desktop_profile=desktop,
        ).validate()
        contexts = m23._selected_contexts(workspace,audit_id,cfg.max_pages)
        existing_rows = {
            (str(row["snapshot_id"]), int(row["run_index"])): row
            for row in connection.execute(
                "SELECT * FROM synthetic_apdex_samples WHERE audit_id=? ORDER BY snapshot_id,run_index", (audit_id,)
            ).fetchall()
        }
        host_environment = _json_load(run["host_environment"], static_host_environment())
    finally:
        connection.close()

    gateway = PlaywrightSyntheticNavigationGateway()
    pacer = m23._OriginPacer(cfg.delay_seconds)
    try:
        with M23Persistence(workspace) as store:
            for context_index, context in enumerate(contexts, 1):
                snapshot_id = str(context["snapshot_id"])
                device = DeviceContext(str(context["device"]))
                profile = cfg.mobile_profile if device is DeviceContext.MOBILE else cfg.desktop_profile
                url = str(context["final_url"] or context["normalized_url"])
                rows = [row for (sid, _), row in existing_rows.items() if sid == snapshot_id]
                items = [_m23_item_from_row(row) for row in rows]
                next_index = max((item.run_index for item in items), default=0) + 1
                new_attempts = 0
                while m23._valid_count(items) < cfg.target_valid_samples and new_attempts < cfg.max_attempts_per_context:
                    pacer.wait_for_slot()
                    measurement = gateway.measure(url=url,profile=profile,timeout_seconds=cfg.timeout_seconds)
                    measured = m23._sample(next_index,measurement,float(cfg.threshold_seconds))
                    items.append(measured)
                    store.add_sample(SyntheticApdexSample(
                        sample_id=new_id("APX"),audit_id=audit_id,page_id=str(context["page_id"]),
                        snapshot_id=snapshot_id,device=device.value,url=url,run_index=next_index,
                        task_id=m23.TASK_NAVIGATION_LOAD,profile_id=profile.profile_id,profile_version=PROFILE_VERSION,
                        status=measurement.status,classification=measured.classification,duration_ms=measurement.duration_ms,
                        http_status=measurement.http_status,final_url=measurement.final_url,error_code=measurement.error_code,
                        error_message=m23._bounded(measurement.error_message,256),cpu_method=measurement.cpu_method,
                        network_method=measurement.network_method,browser_diagnostics={"events": list(measurement.browser_diagnostics)},
                        cache_policy="COLD_CONTEXT",captured_at=m23._utc_now(),
                    ))
                    next_index += 1
                    new_attempts += 1
                summary = m23._summary(
                    audit_id=audit_id,page_id=str(context["page_id"]),device=device.value,url=url,profile=profile,
                    threshold=float(cfg.threshold_seconds),target=cfg.target_valid_samples,
                    samples=sorted(items,key=lambda value:value.run_index),
                )
                store.upsert_summary(summary)

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                sample_rows = connection.execute(
                    "SELECT classification FROM synthetic_apdex_samples WHERE audit_id=?", (audit_id,)
                ).fetchall()
                summaries = connection.execute(
                    "SELECT * FROM synthetic_apdex_summaries WHERE audit_id=?", (audit_id,)
                ).fetchall()
            finally:
                connection.close()
            valid_total = sum(row["classification"] is not None for row in sample_rows)
            invalid_total = len(sample_rows) - valid_total
            target_met = sum(int(row["valid_samples"]) >= cfg.target_valid_samples for row in summaries)
            effective_success = bool(contexts) and len(summaries) == len(contexts) and target_met == len(contexts)
            status = "SUCCESS" if effective_success else ("UNAVAILABLE" if valid_total == 0 else "PARTIAL")
            reason = None if effective_success else "RECOVERY_TARGET_NOT_YET_MET"
            store.upsert_run(SyntheticApdexRun(
                audit_id=audit_id,enabled=True,status=status,task_id=m23.TASK_NAVIGATION_LOAD,
                threshold_seconds=float(cfg.threshold_seconds),frustration_seconds=4.0*float(cfg.threshold_seconds),
                target_valid_samples=cfg.target_valid_samples,max_attempts_per_context=cfg.max_attempts_per_context,
                page_limit=cfg.max_pages,pages_considered=len({str(row["page_id"]) for row in contexts}),
                contexts_considered=len(contexts),attempted_samples=len(sample_rows),valid_samples=valid_total,
                invalid_samples=invalid_total,delay_seconds=cfg.delay_seconds,concurrency=int(run["concurrency"]),
                configuration=persisted_cfg if isinstance(persisted_cfg,dict) else {},host_environment=host_environment,
                reason=reason,updated_at=m23._utc_now(),
            ))
    finally:
        gateway.close()
    return effective_success


def _m25_item_from_row(row: sqlite3.Row):
    from rasai.m25_apdex_experience import UxMeasurement, _Classified
    measurement = UxMeasurement(
        status=str(row["status"]),user_action_duration_ms=row["user_action_duration_ms"],
        navigation_duration_ms=row["navigation_duration_ms"],response_start_ms=row["response_start_ms"],
        response_end_ms=row["response_end_ms"],dom_interactive_ms=row["dom_interactive_ms"],
        load_event_start_ms=row["load_event_start_ms"],load_event_end_ms=row["load_event_end_ms"],
        lcp_ms=row["lcp_ms"],cls=row["cls"],http_status=row["http_status"],final_url=row["final_url"],
        xhr_fetch_count=int(row["xhr_fetch_count"]),dynamic_resource_count=int(row["dynamic_resource_count"]),
        javascript_error_count=int(row["javascript_error_count"]),console_error_count=int(row["console_error_count"]),
        request_failed_count=int(row["request_failed_count"]),first_party_request_failed_count=int(row["first_party_request_failed_count"]),
        http_error_count=int(row["http_error_count"]),first_party_http_error_count=int(row["first_party_http_error_count"]),
        network_settled=bool(row["network_settled"]),profile_applied=bool(row["classification"] is not None),
        error_code=row["error_code"],error_message=row["error_message"],cpu_method=row["cpu_method"],network_method=row["network_method"],
    )
    return _Classified(
        int(row["run_index"]),str(row["device"]),measurement,row["classification"],row["kpm_value_ms"],
        bool(row["error_forced_frustrated"]),str(row["captured_at"] or ""),
    )


def recover_experience_apdex(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    item: WorkItem,
) -> bool:
    """Append only missing M25 valid samples, preserving every prior attempt."""
    from rasai import m25_apdex_experience as m25
    from rasai.m25_persistence import M25Persistence, SyntheticUxRun

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute("SELECT * FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,)).fetchone()
        if run is None or not bool(run["enabled"]):
            return False
        config_map = _json_load(run["configuration"], {})
        mix_map = _json_load(run["device_mix"], {})
        cfg = m25.ExperienceApdexConfig(
            enabled=True,target_samples_per_page=int(run["target_samples_per_page"]),
            max_attempts_per_page=int(run["max_attempts_per_page"]),max_pages=int(run["page_limit"]),
            device_mix=tuple((str(key),float(value)) for key,value in dict(mix_map).items()),
            session_mode=str(run["session_mode"]),kpm=str(run["kpm"]),
            satisfied_threshold_seconds=float(run["satisfied_threshold_seconds"]),
            frustrated_threshold_seconds=float(run["frustrated_threshold_seconds"]),
            errors_affect_apdex=bool(run["errors_affect_apdex"]),error_scope=str(run["error_scope"]),
            settle_seconds=float(run["settle_seconds"]),delay_seconds=float(config_map.get("delay_seconds",1.0) or 1.0),
            concurrency=1,
        ).validate()
        calibration = m25.Calibration(
            source=str(run["calibration_source"]),kpm=str(run["kpm"]),
            satisfied_threshold_seconds=float(run["satisfied_threshold_seconds"]),
            frustrated_threshold_seconds=float(run["frustrated_threshold_seconds"]),
            errors_affect_apdex=bool(run["errors_affect_apdex"]),
            metadata=_json_load(run["calibration_metadata"], {}),
        )
        pages = m25._selected_pages(workspace,audit_id,cfg.max_pages)
        targets = m25.allocate_samples(cfg.target_samples_per_page,cfg.device_mix_dict())
        attempt_targets = m25.allocate_attempts(cfg.max_attempts_per_page,cfg.device_mix_dict(),targets)
        rows = connection.execute(
            "SELECT * FROM synthetic_ux_apdex_samples WHERE audit_id=? ORDER BY page_id,device,run_index", (audit_id,)
        ).fetchall()
        existing_by_context: dict[tuple[str,str],list[Any]] = {}
        for row in rows:
            existing_by_context.setdefault((str(row["page_id"]),str(row["device"])),[]).append(_m25_item_from_row(row))
        host_environment = _json_load(run["host_environment"], {})
    finally:
        connection.close()

    gateway = m25.PlaywrightSyntheticUxGateway(session_mode=cfg.session_mode)
    pacer = m25._OriginPacer(cfg.delay_seconds)
    try:
        with M25Persistence(workspace) as store:
            for page in pages:
                page_id = str(page["page_id"])
                url = str(page["url"])
                page_items: list[Any] = []
                for device in m25._DEVICE_ORDER:
                    target = targets.get(device,0)
                    if target <= 0:
                        continue
                    profile = m25._profile_for_device(device)
                    items = list(existing_by_context.get((page_id,device),[]))
                    next_index = max((value.run_index for value in items),default=0)+1
                    new_attempts = 0
                    while sum(value.classification is not None for value in items) < target and new_attempts < attempt_targets[device]:
                        pacer.wait_for_slot()
                        measurement = gateway.measure(
                            url=url,device=device,profile=profile,
                            timeout_seconds=max(cfg.settle_seconds+calibration.frustrated_threshold_seconds+5.0,15.0),
                            settle_seconds=cfg.settle_seconds,
                        )
                        classification,value,forced = m25.classify_measurement(measurement,calibration,error_scope=cfg.error_scope)
                        classified = m25._Classified(next_index,device,measurement,classification,value,forced,m25._utc_now())
                        items.append(classified)
                        store.add_sample(m25._persisted_sample(audit_id,page_id,url,profile,cfg,calibration,classified))
                        next_index += 1
                        new_attempts += 1
                    existing_by_context[(page_id,device)] = items
                    page_items.extend(items)
                    store.upsert_summary(m25._summary(
                        audit_id=audit_id,page_id=page_id,url=url,device=device,profile_id=profile.profile_id,
                        target=target,items=sorted(items,key=lambda value:value.run_index),
                    ))
                store.upsert_summary(m25._summary(
                    audit_id=audit_id,page_id=page_id,url=url,device="POPULATION",profile_id="MIXED_DEVICE_POPULATION",
                    target=cfg.target_samples_per_page,items=sorted(page_items,key=lambda value:(value.run_index,value.device)),
                ))

            connection = sqlite3.connect(workspace.database)
            connection.row_factory = sqlite3.Row
            try:
                sample_rows = connection.execute(
                    "SELECT classification FROM synthetic_ux_apdex_samples WHERE audit_id=?", (audit_id,)
                ).fetchall()
                population = connection.execute(
                    "SELECT * FROM synthetic_ux_apdex_summaries WHERE audit_id=? AND device='POPULATION'", (audit_id,)
                ).fetchall()
            finally:
                connection.close()
            valid_total = sum(row["classification"] is not None for row in sample_rows)
            invalid_total = len(sample_rows)-valid_total
            effective_success = bool(pages) and len(population)==len(pages) and all(int(row["valid_samples"])>=cfg.target_samples_per_page for row in population)
            status = "SUCCESS" if effective_success else ("UNAVAILABLE" if valid_total==0 else "PARTIAL")
            store.upsert_run(SyntheticUxRun(
                audit_id=audit_id,enabled=True,status=status,task_id=m25.TASK_SYNTHETIC_USER_ACTION,
                target_samples_per_page=cfg.target_samples_per_page,max_attempts_per_page=cfg.max_attempts_per_page,
                page_limit=cfg.max_pages,pages_considered=len(pages),attempted_samples=len(sample_rows),
                valid_samples=valid_total,invalid_samples=invalid_total,device_mix=cfg.device_mix_dict(),
                session_mode=cfg.session_mode,kpm=calibration.kpm,
                satisfied_threshold_seconds=calibration.satisfied_threshold_seconds,
                frustrated_threshold_seconds=calibration.frustrated_threshold_seconds,
                errors_affect_apdex=calibration.errors_affect_apdex,error_scope=cfg.error_scope,
                settle_seconds=cfg.settle_seconds,calibration_source=calibration.source,dynatrace_application_id=run["dynatrace_application_id"],
                calibration_metadata=calibration.metadata,configuration=config_map if isinstance(config_map,dict) else {},
                host_environment=host_environment,reason=None if effective_success else "RECOVERY_TARGET_NOT_YET_MET",updated_at=m25._utc_now(),
            ))
    finally:
        gateway.close()
    return effective_success