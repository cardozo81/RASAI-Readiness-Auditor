"""Selective recovery for live M21/M23/M25 work-items.

Successful external calls and valid synthetic samples are never repeated. Recovery
only acquires the missing effective evidence needed by the original configuration.
Historical failures remain persisted for cost/reliability/operational analysis.
"""
from __future__ import annotations

import json
import math
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
        try:
            run = connection.execute(
                "SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,)
            ).fetchone()
        except sqlite3.OperationalError:
            run = None
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
            psi_artifact_sha256 = (
                str(psi_row["artifact_sha256"])
                if psi_row
                and "artifact_sha256" in psi_row.keys()
                and psi_row["artifact_sha256"]
                and psi_payload is not None
                else None
            )
            psi_http_status = int(psi_row["http_status"]) if psi_row and psi_row["http_status"] is not None and psi_payload is not None else None
            if psi_payload is None:
                try:
                    response = psi.run(url=url,strategy=strategy,categories=cfg.categories,timeout_seconds=cfg.timeout_seconds)
                    psi_payload = response.payload
                    psi_http_status = response.http_status
                    psi_artifact, psi_artifact_sha256 = m21._write_json_artifact(
                        workspace, observation_id, "pagespeed", psi_payload
                    )
                    store.add_attempt(WebPerformanceAttempt(
                        attempt_id=new_id("WPA"),audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                        device=device.value,url=url,service="PAGESPEED_INSIGHTS",status="SUCCESS",
                        http_status=response.http_status,duration_ms=response.duration_ms,error_code=None,
                        error_message=None,artifact_reference=psi_artifact,artifact_sha256=psi_artifact_sha256,created_at=m21._utc_now(),
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
            crux_artifact_sha256 = (
                str(crux_row["artifact_sha256"])
                if crux_row
                and "artifact_sha256" in crux_row.keys()
                and crux_row["artifact_sha256"]
                and prior_crux_success
                else None
            )
            crux_http_status = int(crux_row["http_status"]) if crux_row and crux_row["http_status"] is not None and prior_crux_success else None
            if direct_crux_required:
                if crux_payload is None and crux is not None:
                    try:
                        response = crux.query(url=url,form_factor=form_factor,timeout_seconds=cfg.timeout_seconds)
                        crux_payload = response.payload
                        crux_http_status = response.http_status
                        crux_artifact, crux_artifact_sha256 = m21._write_json_artifact(
                            workspace, observation_id, "crux", crux_payload
                        )
                        store.add_attempt(WebPerformanceAttempt(
                            attempt_id=new_id("WPA"),audit_id=audit_id,page_id=page_id,snapshot_id=snapshot_id,
                            device=device.value,url=url,service="CRUX_API",status="SUCCESS",
                            http_status=response.http_status,duration_ms=response.duration_ms,error_code=None,
                            error_message=None,artifact_reference=crux_artifact,artifact_sha256=crux_artifact_sha256,created_at=m21._utc_now(),
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

            observation, status = m21.build_web_performance_observation(
                observation_id=observation_id,
                audit_id=audit_id,
                page_id=page_id,
                snapshot_id=snapshot_id,
                device=device,
                url=url,
                strategy=strategy,
                psi_payload=psi_payload,
                field_data=field_data,
                field_source=field_source,
                field_scope=field_scope,
                errors=errors,
                psi_http_status=psi_http_status,
                crux_http_status=crux_http_status,
                psi_artifact=psi_artifact,
                crux_artifact=crux_artifact,
                psi_artifact_sha256=psi_artifact_sha256,
                crux_artifact_sha256=crux_artifact_sha256,
            )
            if status in {"SUCCESS", "PARTIAL"}:
                successful_contexts += 1
            if status == "PARTIAL":
                partial_contexts += 1
            store.add_observation(observation)

        run_status, reason = m21.summarize_web_performance_run(
            context_count=len(contexts),
            usable_contexts=successful_contexts,
            partial_contexts=partial_contexts,
        )
        store.upsert_run(WebPerformanceRun(
            audit_id=audit_id,enabled=True,status=run_status,field_source=cfg.field_source,page_limit=cfg.max_pages,
            pages_considered=len({str(row["page_id"]) for row in contexts}),context_attempts=len(contexts),
            successful_contexts=successful_contexts,pagespeed_successes=effective_psi_successes,
            crux_successes=effective_crux_successes,categories=cfg.categories,reason=reason,updated_at=m21._utc_now(),
        ))
    # RPR may replace the effective PageSpeed/Lighthouse observation without going
    # through the initial M21 CLI wrapper. Rebuild the derived integrity artifact from
    # the persisted final state so database, raw evidence and report package cannot
    # describe different moments of the same AUD. This performs no network request.
    from rasai.external_metrics_integrity import refresh_external_metrics_integrity_artifact
    refresh_external_metrics_integrity_artifact(audit_id=audit_id, workspace=workspace)
    return run_status == "SUCCESS"


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


def _m25_persisted_profile_selection(
    config_map: dict[str, Any],
    sample_rows: tuple[sqlite3.Row, ...] | list[sqlite3.Row] = (),
) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Resolve frozen M25 profile IDs without consulting the current environment."""
    from rasai.synthetic_runtime_profiles import default_preset, validate_preset

    raw_profiles = config_map.get("runtime_profiles")
    raw_profiles = dict(raw_profiles) if isinstance(raw_profiles, dict) else {}
    resolved: dict[str, dict[str, str]] = {}
    provenance: dict[str, str] = {}

    for device in ("MOBILE", "DESKTOP", "TABLET"):
        raw = raw_profiles.get(device)
        if isinstance(raw, dict):
            try:
                resolved[device] = {
                    kind: validate_preset(kind, device, str(raw[kind]))
                    for kind in ("client", "hardware", "network")
                }
                provenance[device] = "AUD_CONFIGURATION"
                continue
            except (KeyError, TypeError, ValueError):
                pass

        # Modern samples persist a composite profile_id.  This is an evidence-backed
        # fallback for AUDs created before runtime_profiles was added to the run config.
        for row in sample_rows:
            try:
                row_device = str(row["device"] or "").upper()
                profile_id = str(row["profile_id"] or "")
            except (IndexError, KeyError, TypeError):
                continue
            if row_device != device or not profile_id.startswith(f"RASAI_{device}_"):
                continue
            parts = profile_id.split("_", 4)
            if len(parts) != 5:
                continue
            try:
                resolved[device] = {
                    "client": validate_preset("client", device, parts[2]),
                    "hardware": validate_preset("hardware", device, parts[3]),
                    "network": validate_preset("network", device, parts[4]),
                }
                provenance[device] = "PERSISTED_SAMPLE_PROFILE_ID"
                break
            except ValueError:
                continue

        if device not in resolved:
            resolved[device] = {
                kind: default_preset(kind, device)
                for kind in ("client", "hardware", "network")
            }
            provenance[device] = "LEGACY_DEFAULT_FALLBACK"

    return resolved, provenance


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


def _restart_interrupted_m23_stage(
    workspace: AuditWorkspace,
    audit_id: str,
    run: sqlite3.Row,
    connection: sqlite3.Connection,
    item: WorkItem,
) -> bool:
    """Restart only an unfinished M23 stage after preserving its partial history."""
    if str(run["status"]).upper() != "RUNNING":
        return False
    from rasai import m23_apdex as m23
    from rasai.m23_cli import DEFAULT_APDEX_SAMPLES_PER_CONTEXT
    from rasai.audit_fulfillment import archive_rows
    from rasai.governed_reprocess_runtime import _current_reprocess_id
    from rasai.m23_persistence import M23Persistence
    from rasai.operational_log import try_append_operational_event

    reprocess_id = _current_reprocess_id(workspace, audit_id)
    if not reprocess_id:
        # Fail closed: clearing a stage without a durable archive loses evidence.
        raise RuntimeError("interrupted M23 stage requires an active RPR archive")
    persisted = _json_load(run["configuration"], {})
    persisted = dict(persisted) if isinstance(persisted, dict) else {}
    cfg = m23.SyntheticApdexConfig(
        enabled=True,
        threshold_seconds=float(run["threshold_seconds"]),
        target_valid_samples=int(run["target_valid_samples"]),
        max_attempts_per_context=int(run["max_attempts_per_context"]),
        max_pages=int(run["page_limit"]),
        timeout_seconds=float(
            persisted.get("timeout_seconds")
            or item.configuration.get("timeout_seconds")
            or 45.0
        ),
        delay_seconds=float(run["delay_seconds"]),
        concurrency=int(run["concurrency"]),
        mobile_profile=_profile_from_persisted(
            persisted.get("mobile_profile"), device="MOBILE"
        ),
        desktop_profile=_profile_from_persisted(
            persisted.get("desktop_profile"), device="DESKTOP"
        ),
    ).validate()

    # Old rows are facts of the abandoned attempt, not the new population.
    for table, identifier in (
        ("synthetic_apdex_runs", "audit_id"),
        ("synthetic_apdex_samples", "sample_id"),
        ("synthetic_apdex_summaries", "summary_id"),
    ):
        rows = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM {table} WHERE audit_id=?", (audit_id,)
            ).fetchall()
        ]
        if rows:
            archive_rows(
                workspace,
                audit_id=audit_id,
                reprocess_id=reprocess_id,
                component="SYNTHETIC_APDEX",
                entity_type=table,
                id_field=identifier,
                rows=rows,
            )
    with M23Persistence(workspace) as store:
        store.clear_audit(audit_id)
    try_append_operational_event(
        workspace,
        "M23_INTERRUPTED_STAGE_RESTARTED",
        audit_id=audit_id,
        reprocess_id=reprocess_id,
        policy="RESTART_UNFINISHED_STAGE",
        target_valid_samples=cfg.target_valid_samples,
    )
    m23.execute_m23_apdex(audit_id=audit_id, workspace=workspace, config=cfg)
    return m23.persisted_target_fulfilled(
        workspace, audit_id, cfg.target_valid_samples
    )


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
        try:
            run = connection.execute("SELECT * FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,)).fetchone()
        except sqlite3.OperationalError:
            run = None
        if run is not None and str(run["status"]).upper() == "RUNNING":
            return _restart_interrupted_m23_stage(
                workspace, audit_id, run, connection, item
            )
        if run is None:
            cfg_map = dict(item.configuration or {})
            if not bool(cfg_map.get("enabled", True)):
                return False
            mobile = _profile_from_persisted(cfg_map.get("mobile_profile"), device="MOBILE")
            desktop = _profile_from_persisted(cfg_map.get("desktop_profile"), device="DESKTOP")
            cfg = m23.SyntheticApdexConfig(
                enabled=True,
                threshold_seconds=float(cfg_map.get("threshold_seconds")),
                target_valid_samples=int(cfg_map.get("target_valid_samples") or DEFAULT_APDEX_SAMPLES_PER_CONTEXT),
                max_attempts_per_context=int(cfg_map.get("max_attempts_per_context") or max(DEFAULT_APDEX_SAMPLES_PER_CONTEXT, int(math.ceil(DEFAULT_APDEX_SAMPLES_PER_CONTEXT * 1.25)))),
                max_pages=int(cfg_map.get("max_pages") or 0),
                timeout_seconds=float(cfg_map.get("timeout_seconds") or 45.0),
                delay_seconds=float(cfg_map.get("delay_seconds") or 1.0),
                concurrency=int(cfg_map.get("concurrency") or 1),
                mobile_profile=mobile,
                desktop_profile=desktop,
            ).validate()
            connection.close()
            result = m23.execute_m23_apdex(
                audit_id=audit_id,
                workspace=workspace,
                config=cfg,
            )
            return m23.persisted_target_fulfilled(
                workspace, audit_id, cfg.target_valid_samples
            )
        if not bool(run["enabled"]):
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
                # The original attempt ceiling is cumulative across AUD and all
                # RPRs, not a fresh budget for every recovery attempt.
                remaining_budget = max(cfg.max_attempts_per_context - len(items), 0)
                while m23._valid_count(items) < cfg.target_valid_samples and new_attempts < remaining_budget:
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
            final_contexts = sum(bool(row["final_group"]) for row in summaries)
            small_groups = sum(bool(row["small_group"]) and bool(row["valid_samples"]) for row in summaries)
            # The same M23 status contract governs the initial AUD and the RPR;
            # reaching a small-group target does not silently become SUCCESS.
            status, reason = m23._run_status(
                context_count=len(contexts),
                final_contexts=final_contexts if len(summaries) == len(contexts) else 0,
                target_met_contexts=target_met,
                small_groups=small_groups,
                valid_total=valid_total,
                invalid_total=invalid_total,
            )
            # The statistical PARTIAL warning does not invalidate a fulfilled
            # configured sample target; decide only from committed evidence.
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
    return m23.persisted_target_fulfilled(
        workspace, audit_id, cfg.target_valid_samples
    )


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
        csp_violation_count=int(row["csp_violation_count"]) if "csp_violation_count" in row.keys() else 0,
        first_party_csp_violation_count=int(row["first_party_csp_violation_count"]) if "first_party_csp_violation_count" in row.keys() else 0,
        failed_image_request_count=int(row["failed_image_request_count"]) if "failed_image_request_count" in row.keys() else 0,
        first_party_failed_image_request_count=int(row["first_party_failed_image_request_count"]) if "first_party_failed_image_request_count" in row.keys() else 0,
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
        try:
            run = connection.execute("SELECT * FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,)).fetchone()
        except sqlite3.OperationalError:
            run = None
        if run is None:
            cfg_map = dict(item.configuration or {})
            if not bool(cfg_map.get("enabled", True)):
                return False
            raw_mix = cfg_map.get("device_mix") or {}
            if isinstance(raw_mix, dict):
                mix = tuple((str(key), float(value)) for key, value in raw_mix.items())
            else:
                mix = tuple((str(key), float(value)) for key, value in raw_mix)
            cfg = m25.ExperienceApdexConfig(
                enabled=True,
                target_samples_per_page=int(cfg_map.get("target_samples_per_page") or 100),
                max_attempts_per_page=int(cfg_map.get("max_attempts_per_page") or 125),
                max_pages=int(cfg_map.get("max_pages") or 0),
                device_mix=mix,
                session_mode=str(cfg_map.get("session_mode") or "cold"),
                kpm=str(cfg_map.get("kpm") or "USER_ACTION_DURATION"),
                satisfied_threshold_seconds=(
                    float(cfg_map["satisfied_threshold_seconds"])
                    if cfg_map.get("satisfied_threshold_seconds") is not None
                    else None
                ),
                frustrated_threshold_seconds=(
                    float(cfg_map["frustrated_threshold_seconds"])
                    if cfg_map.get("frustrated_threshold_seconds") is not None
                    else None
                ),
                errors_affect_apdex=bool(cfg_map.get("errors_affect_apdex", True)),
                javascript_errors_affect_apdex=bool(cfg_map.get("javascript_errors_affect_apdex", True)),
                request_errors_affect_apdex=bool(cfg_map.get("request_errors_affect_apdex", True)),
                console_errors_affect_apdex=bool(cfg_map.get("console_errors_affect_apdex", False)),
                javascript_error_capture=bool(cfg_map.get("javascript_error_capture", True)),
                xhr_capture=bool(cfg_map.get("xhr_capture", True)),
                fetch_capture=bool(cfg_map.get("fetch_capture", True)),
                console_error_capture=bool(cfg_map.get("console_error_capture", False)),
                max_error_details=int(cfg_map.get("max_error_details", 10) if cfg_map.get("max_error_details") is not None else 10),
                error_scope=str(cfg_map.get("error_scope") or "all"),
                settle_seconds=float(cfg_map.get("settle_seconds") or 5.0),
                delay_seconds=float(cfg_map.get("delay_seconds") or 1.0),
                concurrency=int(cfg_map.get("concurrency") or 1),
                dynatrace_import=bool(cfg_map.get("dynatrace_import", False)),
                dynatrace_base_url=str(cfg_map.get("dynatrace_base_url") or "") or None,
                dynatrace_application_id=str(cfg_map.get("dynatrace_application_id") or "") or None,
                dynatrace_config_json=str(cfg_map.get("dynatrace_config_json") or "") or None,
            ).validate()
            profile_selection, profile_provenance = _m25_persisted_profile_selection(cfg_map)
            connection.close()
            from rasai.operational_log import try_append_operational_event
            from rasai.synthetic_profile_runtime import profile_selection_scope

            try_append_operational_event(
                workspace,
                "M25_RPR_PROFILE_SELECTION",
                audit_id=audit_id,
                provenance=profile_provenance,
                runtime_profiles=profile_selection,
            )
            with profile_selection_scope(profile_selection):
                result = m25.execute_m25_experience(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=cfg,
                )
            return str(result.status).upper() == "SUCCESS"
        if not bool(run["enabled"]):
            return False
        config_map = _json_load(run["configuration"], {})
        config_map = dict(config_map) if isinstance(config_map, dict) else {}
        mix_map = _json_load(run["device_mix"], {})
        error_scope = str(run["error_scope"])
        granular_keys = {
            "javascript_errors_affect_apdex",
            "request_errors_affect_apdex",
            "console_errors_affect_apdex",
            "javascript_error_capture",
            "xhr_capture",
            "fetch_capture",
            "console_error_capture",
            "max_error_details",
        }
        legacy_policy = not any(key in config_map for key in granular_keys)
        # Audits created before #65 must preserve the policy that originally scored
        # their samples. In the legacy runtime JS/console only forced frustration in
        # scope=all, while both event families were still captured diagnostically.
        javascript_errors_affect = bool(
            config_map.get("javascript_errors_affect_apdex", error_scope == "all" if legacy_policy else True)
        )
        request_errors_affect = bool(config_map.get("request_errors_affect_apdex", True))
        console_errors_affect = bool(
            config_map.get("console_errors_affect_apdex", error_scope == "all" if legacy_policy else False)
        )
        javascript_capture = bool(config_map.get("javascript_error_capture", True))
        xhr_capture = bool(config_map.get("xhr_capture", True))
        fetch_capture = bool(config_map.get("fetch_capture", True))
        console_capture = bool(config_map.get("console_error_capture", True if legacy_policy else False))
        max_error_details = int(config_map.get("max_error_details", 50 if legacy_policy else 10) or 0)
        max_error_details = max(0, min(max_error_details, 50))

        cfg = m25.ExperienceApdexConfig(
            enabled=True,target_samples_per_page=int(run["target_samples_per_page"]),
            max_attempts_per_page=int(run["max_attempts_per_page"]),max_pages=int(run["page_limit"]),
            device_mix=tuple((str(key),float(value)) for key,value in dict(mix_map).items()),
            session_mode=str(run["session_mode"]),kpm=str(run["kpm"]),
            satisfied_threshold_seconds=float(run["satisfied_threshold_seconds"]),
            frustrated_threshold_seconds=float(run["frustrated_threshold_seconds"]),
            errors_affect_apdex=bool(run["errors_affect_apdex"]),
            javascript_errors_affect_apdex=javascript_errors_affect,
            request_errors_affect_apdex=request_errors_affect,
            console_errors_affect_apdex=console_errors_affect,
            javascript_error_capture=javascript_capture,
            xhr_capture=xhr_capture,
            fetch_capture=fetch_capture,
            console_error_capture=console_capture,
            max_error_details=max_error_details,
            error_scope=error_scope,
            settle_seconds=float(run["settle_seconds"]),
            delay_seconds=float(config_map.get("delay_seconds",1.0) or 1.0),
            concurrency=int(config_map.get("concurrency",1) or 1),
            dynatrace_import=bool(config_map.get("dynatrace_import", False)),
            dynatrace_base_url=str(config_map.get("dynatrace_base_url") or "") or None,
            dynatrace_application_id=str(config_map.get("dynatrace_application_id") or "") or None,
            dynatrace_config_json=str(config_map.get("dynatrace_config_json") or "") or None,
        ).validate()

        calibration_metadata = _json_load(run["calibration_metadata"], {})
        calibration_metadata = dict(calibration_metadata) if isinstance(calibration_metadata, dict) else {}
        imported_policy = calibration_metadata.get("error_policy")
        imported_policy = dict(imported_policy) if isinstance(imported_policy, dict) else {}
        capture = calibration_metadata.get("dynatrace_capture_contract")
        capture = dict(capture) if isinstance(capture, dict) else {}

        def _effective_bool(mapping: dict[str, Any], key: str, fallback: bool) -> bool:
            value = mapping.get(key)
            return bool(value) if isinstance(value, bool) else fallback

        imported_max = capture.get("max_errors_to_capture")
        try:
            effective_max_details = int(imported_max) if imported_max is not None else cfg.max_error_details
        except (TypeError, ValueError):
            effective_max_details = cfg.max_error_details
        effective_max_details = max(0, min(effective_max_details, 50))

        calibration = m25.Calibration(
            source=str(run["calibration_source"]),kpm=str(run["kpm"]),
            satisfied_threshold_seconds=float(run["satisfied_threshold_seconds"]),
            frustrated_threshold_seconds=float(run["frustrated_threshold_seconds"]),
            errors_affect_apdex=bool(run["errors_affect_apdex"]),
            metadata=calibration_metadata,
            javascript_errors_affect_apdex=_effective_bool(
                imported_policy, "javascript_errors_affect_apdex", cfg.javascript_errors_affect_apdex
            ),
            request_errors_affect_apdex=_effective_bool(
                imported_policy, "request_errors_affect_apdex", cfg.request_errors_affect_apdex
            ),
            console_errors_affect_apdex=_effective_bool(
                imported_policy, "console_errors_affect_apdex", cfg.console_errors_affect_apdex
            ),
            javascript_error_capture=_effective_bool(capture, "javascript_errors", cfg.javascript_error_capture),
            xhr_capture=_effective_bool(capture, "xhr_enabled", cfg.xhr_capture),
            fetch_capture=_effective_bool(capture, "fetch_enabled", cfg.fetch_capture),
            console_error_capture=_effective_bool(capture, "console_errors", cfg.console_error_capture),
            max_error_details=effective_max_details,
        )
        pages = m25._selected_pages(workspace,audit_id,cfg.max_pages)
        targets = m25.allocate_samples(cfg.target_samples_per_page,cfg.device_mix_dict())
        attempt_targets = m25.allocate_attempts(cfg.max_attempts_per_page,cfg.device_mix_dict(),targets)
        rows = tuple(connection.execute(
            "SELECT * FROM synthetic_ux_apdex_samples WHERE audit_id=? ORDER BY page_id,device,run_index", (audit_id,)
        ).fetchall())
        existing_by_context: dict[tuple[str,str],list[Any]] = {}
        for row in rows:
            existing_by_context.setdefault((str(row["page_id"]),str(row["device"])),[]).append(_m25_item_from_row(row))
        profile_selection, profile_provenance = _m25_persisted_profile_selection(config_map, rows)
        host_environment = _json_load(run["host_environment"], {})
    finally:
        connection.close()

    from rasai.operational_log import try_append_operational_event
    from rasai.synthetic_profile_runtime import profile_selection_scope

    try_append_operational_event(
        workspace,
        "M25_RPR_PROFILE_SELECTION",
        audit_id=audit_id,
        provenance=profile_provenance,
        runtime_profiles=profile_selection,
        concurrency=cfg.concurrency,
        delay_seconds=cfg.delay_seconds,
    )

    base_factory = lambda: m25.PlaywrightSyntheticUxGateway(session_mode=cfg.session_mode)
    factory = lambda: m25._apply_gateway_capture_policy(base_factory(), calibration)
    shared_gateway = factory() if cfg.concurrency == 1 else None
    pacer = m25._OriginPacer(cfg.delay_seconds)
    try:
        with profile_selection_scope(profile_selection):
            with M25Persistence(workspace) as store:
                for page_index, page in enumerate(pages, 1):
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
                        missing_valid = max(
                            target - sum(value.classification is not None for value in items),
                            0,
                        )
                        if missing_valid:
                            new_items = m25._measure_device(
                                audit_id=audit_id,
                                workspace=workspace,
                                url=url,
                                device=device,
                                target=missing_valid,
                                max_attempts=attempt_targets[device],
                                page_index=page_index,
                                page_total=len(pages),
                                calibration=calibration,
                                config=cfg,
                                pacer=pacer,
                                shared_gateway=shared_gateway,
                                factory=factory,
                                profile=profile,
                                start_index=next_index,
                            )
                            for classified in new_items:
                                store.add_sample(
                                    m25._persisted_sample(
                                        audit_id,page_id,url,profile,cfg,calibration,classified
                                    )
                                )
                            items.extend(new_items)
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
            # The sample writer was closed above; run finalization needs its
            # own live transaction (also on a zero-deficit repeated recovery).
            with M25Persistence(workspace) as run_store:
                run_store.upsert_run(SyntheticUxRun(
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
        if shared_gateway is not None:
            shared_gateway.close()
    return effective_success