"""Bounded external corroboration admitted into SARI-001.

Only one external signal is score-eligible: positive Common Crawl historical
observation, materialized as BR-GEO-060 before M9.  CrUX History and Microsoft
Clarity remain observational outcomes and never enter SARI.

Safety invariants:
- automatic Common Crawl calls are restricted to public HTTP(S) URLs without
  credentials, query strings or fragments;
- absence, provider error or no capture never becomes FAIL/zero and never reduces
  Coverage/Confidence;
- BR-GEO-060 is not part of a Critical Readiness Gate;
- the persisted RuleExecution + Evidence is sufficient for offline rescoring;
- post-score report finalization never repeats the Common Crawl network call.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping
from urllib.parse import urlsplit

from rasai.domain import EvidenceType, RuleExecution, RuleResult, new_id, utc_now
from rasai.evidence import EvidenceManager
from rasai.external_observability_policy import (
    COMMON_CRAWL_ENABLED_ENV,
    COMMON_CRAWL_INDEX_COUNT_ENV,
    COMMON_CRAWL_MAX_URLS_ENV,
    common_crawl_index_count,
    common_crawl_max_urls,
)
from rasai.observability.external_sources import (
    SOURCE_COMMON_CRAWL,
    _common_crawl_no_capture_message,
    archive_rows,
    collect_common_crawl_history,
)
from rasai.observability.store import ObservabilityStore
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.score_geo_004 import DIMENSION_WEIGHTS, GROUP_WEIGHTS
from rasai.secret_safety import redact_text
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    STANDARDS_TIMEOUT_ENV,
    service,
    service_state,
)

_LOGGER = logging.getLogger(__name__)
RULE_ID = "BR-GEO-060"
RULE_VERSION = "1"
MIN_OBSERVED_URL_RATIO = 0.50
STATE_FILE = "common-crawl-pre-scoring-state.json"
_DISCOVERY_BLOCKING_RULES = frozenset({
    "BR-GEO-005", "BR-GEO-006", "BR-GEO-007", "BR-GEO-008", "BR-GEO-017", "BR-GEO-018",
})
MAX_OVERALL_IMPACT_POINTS = (
    DIMENSION_WEIGHTS["DISCOVERY_ACCESS"]
    * GROUP_WEIGHTS["DISCOVERY_ACCESS"]["EXTERNAL_CRAWL_CORROBORATION"]
    * 100.0
)


@dataclass(frozen=True, slots=True)
class ExternalSariMaterialization:
    rule_execution_ids: tuple[str, ...]
    state: str
    dataset_id: str | None
    selected_url_count: int
    observed_url_count: int
    observed_ratio: float | None
    reason: str | None = None
    errors: tuple[str, ...] = ()


def common_crawl_dataset_health(
    workspace: AuditWorkspace,
    dataset_id: str,
    *,
    row_count: int | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Classify persisted Common Crawl acquisition without repeating network I/O."""
    dataset = _dataset_row(workspace, dataset_id)
    if dataset is None:
        return "FAILED_RETRYABLE", ("COMMON_CRAWL_DATASET_MISSING",)
    metadata: dict[str, Any] = {}
    try:
        parsed = json.loads(str(dataset["metadata"] or "{}"))
        if isinstance(parsed, dict):
            metadata = parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    errors: list[str] = []
    no_capture_error_count = 0
    artifact_path = str(dataset["artifact_path"] or "")
    if artifact_path:
        path = Path(artifact_path)
        if not path.is_absolute():
            path = workspace.root / path
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
            raw_errors = artifact.get("errors") if isinstance(artifact, Mapping) else None
            if isinstance(raw_errors, list):
                for item in raw_errors:
                    text = str(item or "").strip()
                    if not text:
                        continue
                    if _common_crawl_no_capture_message(text):
                        # Backward compatibility for artifacts produced before no-capture
                        # events were separated from actual provider errors.
                        no_capture_error_count += 1
                        continue
                    errors.append(text)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    try:
        error_count = max(0, int(metadata.get("errors") or 0))
    except (TypeError, ValueError):
        error_count = 0
    effective_error_count = max(0, error_count - no_capture_error_count)
    if effective_error_count and not errors:
        errors.append(f"COMMON_CRAWL_PROVIDER_ERRORS:{effective_error_count}")
    try:
        rows = max(0, int(metadata.get("rows") if metadata.get("rows") is not None else (row_count or 0)))
    except (TypeError, ValueError):
        rows = max(0, int(row_count or 0))
    unique_errors = tuple(dict.fromkeys(errors))
    if unique_errors:
        return ("PARTIAL" if rows > 0 else "FAILED_RETRYABLE"), unique_errors
    return ("SUCCESS" if rows > 0 else "NO_DATA"), ()


def materialize_common_crawl_corroboration(
    *,
    audit_id: str,
    rule_execution_ids: tuple[str, ...],
    persistence: AuditPersistence,
    workspace: AuditWorkspace,
    env: Mapping[str, str] | None = None,
) -> ExternalSariMaterialization:
    """Collect once and optionally persist the positive-only BR-GEO-060 signal."""
    environment = env if env is not None else os.environ
    state_info = service_state(service("common-crawl"), environment)
    existing = _existing_rule_execution(workspace, audit_id)
    if existing:
        result = ExternalSariMaterialization((existing,), "REUSED", None, 0, 0, None, "RULE_ALREADY_MATERIALIZED")
        _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
        return result

    if not bool(state_info["effective_enabled"]):
        result = ExternalSariMaterialization((), str(state_info["state"]), None, 0, 0, None, "SERVICE_NOT_ENABLED")
        _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
        return result

    max_urls = common_crawl_max_urls(environment.get(COMMON_CRAWL_MAX_URLS_ENV))
    if max_urls <= 0:
        result = ExternalSariMaterialization((), "NO_DATA", None, 0, 0, None, "COMMON_CRAWL_MAX_URLS_ZERO")
        _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
        return result

    selected_urls = _selected_audit_urls(workspace, max_urls)
    if not selected_urls:
        result = ExternalSariMaterialization((), "NO_DATA", None, 0, 0, None, "NO_AUDITED_URLS")
        _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
        return result
    if not all(_safe_public_simple_url(url) for url in selected_urls):
        result = ExternalSariMaterialization(
            (), "NO_DATA", None, len(selected_urls), 0, None,
            "AUTOMATIC_PUBLIC_SAFETY_GATE_REJECTED_TARGET",
        )
        _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
        return result

    timeout = _positive_float(environment.get(STANDARDS_TIMEOUT_ENV), DEFAULT_STANDARDS_TIMEOUT_SECONDS)
    try:
        dataset_id = collect_common_crawl_history(
            audit_workspace=workspace.root,
            max_urls=max_urls,
            collection_count=common_crawl_index_count(environment.get(COMMON_CRAWL_INDEX_COUNT_ENV)),
            timeout=timeout,
        )
    except Exception as exc:  # external provider must never fail the audit/scoring pipeline
        result = ExternalSariMaterialization(
            (), "ERROR", None, len(selected_urls), 0, None,
            redact_text(f"{type(exc).__name__}:{str(exc)[:300]}"),
        )
        _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
        _LOGGER.warning("Common Crawl SARI corroboration unavailable: %s", result.reason)
        return result

    rows = [row for row in archive_rows(workspace.root) if str(row.get("dataset_id") or "") == dataset_id]
    observed_urls = sorted({str(row.get("target_url") or "") for row in rows if row.get("target_url")})
    selected_set = set(selected_urls)
    observed_in_scope = sorted(url for url in observed_urls if url in selected_set)
    ratio = (len(observed_in_scope) / len(selected_urls)) if selected_urls else None
    collection_state, provider_errors = common_crawl_dataset_health(
        workspace, dataset_id, row_count=len(rows)
    )

    blocked = _current_discovery_blocked(persistence, rule_execution_ids)
    qualifies = bool(
        rows
        and ratio is not None
        and ratio >= MIN_OBSERVED_URL_RATIO
        and not blocked
    )
    materialized: tuple[str, ...] = ()
    reason: str | None = None
    if provider_errors and not rows:
        reason = "COMMON_CRAWL_PROVIDER_ERRORS"
    elif provider_errors:
        reason = "COMMON_CRAWL_PARTIAL_PROVIDER_ERRORS"
    elif blocked:
        reason = "CURRENT_DISCOVERY_GATE_BLOCKED"
    elif not rows:
        reason = "NO_COMMON_CRAWL_CAPTURE_OBSERVED"
    elif ratio is None or ratio < MIN_OBSERVED_URL_RATIO:
        reason = "OBSERVED_URL_RATIO_BELOW_CORROBORATION_THRESHOLD"

    if qualifies:
        dataset = _dataset_row(workspace, dataset_id)
        manager = EvidenceManager(persistence)
        observed_value = {
            "source": SOURCE_COMMON_CRAWL,
            "dataset_id": dataset_id,
            "selected_url_count": len(selected_urls),
            "observed_url_count": len(observed_in_scope),
            "observed_url_ratio": round(float(ratio), 6),
            "minimum_observed_url_ratio": MIN_OBSERVED_URL_RATIO,
            "historical_only": True,
            "proves_google_or_bing_indexation": False,
            "device_dimension": False,
            "sari_dimension": "DISCOVERY_ACCESS",
            "sari_group": "EXTERNAL_CRAWL_CORROBORATION",
            "group_weight": GROUP_WEIGHTS["DISCOVERY_ACCESS"]["EXTERNAL_CRAWL_CORROBORATION"],
            "maximum_overall_impact_points": MAX_OVERALL_IMPACT_POINTS,
        }
        evidence = manager.record(
            audit_id=audit_id,
            page_id=None,
            snapshot_id=None,
            device=None,
            evidence_type=EvidenceType.COMPARISON,
            source="external:common-crawl:BR-GEO-060",
            observed_value=observed_value,
            artifact_reference=(str(dataset["artifact_path"]) if dataset is not None else None),
        )
        execution = RuleExecution(
            rule_execution_id=new_id("REX"),
            audit_id=audit_id,
            rule_id=RULE_ID,
            rule_version=RULE_VERSION,
            page_id=None,
            snapshot_id=None,
            device=None,
            result=RuleResult.PASS,
            observed_value=observed_value,
            expected_condition=(
                "bounded safe audited URLs have positive historical Common Crawl corroboration "
                f"for at least {MIN_OBSERVED_URL_RATIO:.0%} of the selected set, while current discovery critical signals are not blocked"
            ),
            evidence_ids=(evidence.evidence_id,),
            executed_at=utc_now(),
            error=None,
        )
        persistence.rule_executions.add(execution)
        materialized = (execution.rule_execution_id,)

    result = ExternalSariMaterialization(
        materialized,
        collection_state,
        dataset_id,
        len(selected_urls),
        len(observed_in_scope),
        round(float(ratio), 6) if ratio is not None else None,
        reason,
        provider_errors,
    )
    _write_state(workspace, _state_payload(state_info, result, phase="PRE_SCORING"))
    return result


def install() -> None:
    """Compose pre-M9 corroboration and suppress duplicate post-score collection."""
    from rasai import audit_runner
    from rasai import external_observability_runtime as external_runtime

    if not getattr(audit_runner, "_rasai_external_sari_corroboration", False):
        original_execute_m9 = audit_runner.execute_m9

        def execute_m9_with_external_sari(*, audit_id: str, rule_execution_ids: tuple[str, ...], persistence: AuditPersistence, workspace: AuditWorkspace):
            try:
                materialized = materialize_common_crawl_corroboration(
                    audit_id=audit_id,
                    rule_execution_ids=rule_execution_ids,
                    persistence=persistence,
                    workspace=workspace,
                )
                effective_ids = tuple(dict.fromkeys((*rule_execution_ids, *materialized.rule_execution_ids)))
            except Exception:
                _LOGGER.exception("External SARI corroboration failed safely; deterministic scoring preserved")
                effective_ids = rule_execution_ids
            return original_execute_m9(
                audit_id=audit_id,
                rule_execution_ids=effective_ids,
                persistence=persistence,
                workspace=workspace,
            )

        audit_runner.execute_m9 = execute_m9_with_external_sari
        audit_runner._rasai_external_sari_corroboration = True

    if not getattr(external_runtime, "_rasai_external_sari_no_duplicate_collection", False):
        original_collect = external_runtime.collect_configured_external_observability

        def collect_without_post_score_common_crawl(*, audit_id: str, workspace: Any, env: Mapping[str, str] | None = None):
            actual_environment = dict(env if env is not None else os.environ)
            collection_environment = dict(actual_environment)
            # Common Crawl is owned by the pre-scoring phase so SARI and reports share
            # exactly the same dataset. Disable only this provider in the later pass.
            collection_environment[COMMON_CRAWL_ENABLED_ENV] = "false"
            outcomes = original_collect(audit_id=audit_id, workspace=workspace, env=collection_environment)
            persisted = _read_state(workspace)
            if persisted is None:
                state_info = service_state(service("common-crawl"), actual_environment)
                persisted = {
                    "service_state": str(state_info["state"]),
                    "requested": bool(state_info["requested"]),
                    "configured": bool(state_info["configured"]),
                    "effective_enabled": bool(state_info["effective_enabled"]),
                    "configuration_source": str(state_info["configuration_source"]),
                    "missing_configuration": list(state_info["missing_configuration"]),
                    "targets_attempted": 0,
                    "targets_succeeded": 0,
                    "datasets": [],
                    "errors": [],
                    "collection_state": "NO_DATA",
                    "reason": "PRE_SCORING_COLLECTION_STATE_NOT_FOUND",
                    "phase": "PRE_SCORING",
                    "scope": "URL",
                }
            outcomes["common-crawl"] = persisted
            try:
                external_runtime._upsert_service_run(
                    audit_id=audit_id,
                    workspace=workspace,
                    service_id="common-crawl",
                    result=persisted,
                )
            except Exception:
                _LOGGER.exception("Could not project Common Crawl pre-scoring state to standards_service_runs")
            return outcomes

        external_runtime.collect_configured_external_observability = collect_without_post_score_common_crawl
        external_runtime._rasai_external_sari_no_duplicate_collection = True


def _state_payload(state_info: Mapping[str, Any], result: ExternalSariMaterialization, *, phase: str) -> dict[str, Any]:
    success = 1 if result.dataset_id and result.state in {"SUCCESS", "NO_DATA", "PARTIAL"} else 0
    errors = list(result.errors)
    if not errors and result.state in {"ERROR", "FAILED_RETRYABLE"} and result.reason:
        errors = [result.reason]
    return {
        "service_state": str(state_info.get("state") or "UNKNOWN"),
        "requested": bool(state_info.get("requested")),
        "configured": bool(state_info.get("configured")),
        "effective_enabled": bool(state_info.get("effective_enabled")),
        "configuration_source": str(state_info.get("configuration_source") or ""),
        "missing_configuration": list(state_info.get("missing_configuration") or ()),
        "targets_attempted": 1 if result.selected_url_count else 0,
        "targets_succeeded": success,
        "datasets": [result.dataset_id] if result.dataset_id else [],
        "errors": errors,
        "collection_state": result.state,
        "reason": result.reason,
        "phase": phase,
        "scope": "URL",
        "selected_url_count": result.selected_url_count,
        "observed_url_count": result.observed_url_count,
        "observed_url_ratio": result.observed_ratio,
        "sari_rule": RULE_ID,
        "sari_contribution_materialized": bool(result.rule_execution_ids),
        "maximum_overall_impact_points": MAX_OVERALL_IMPACT_POINTS,
    }


def _write_state(workspace: AuditWorkspace, payload: Mapping[str, Any]) -> None:
    directory = workspace.root / "artifacts" / "observability"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / STATE_FILE).write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_state(workspace: Any) -> dict[str, Any] | None:
    root = Path(workspace.root if hasattr(workspace, "root") else workspace)
    path = root / "artifacts" / "observability" / STATE_FILE
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _selected_audit_urls(workspace: AuditWorkspace, max_urls: int) -> tuple[str, ...]:
    connection = sqlite3.connect(workspace.database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    try:
        rows = connection.execute(
            "SELECT normalized_url FROM pages ORDER BY rowid LIMIT ?",
            (int(max_urls),),
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]) for row in rows if row[0])


def _safe_public_simple_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").strip().casefold()
        if parsed.scheme.casefold() not in {"http", "https"} or not hostname:
            return False
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            return False
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return bool(address.is_global)
    except (TypeError, ValueError):
        return False


def _current_discovery_blocked(persistence: AuditPersistence, execution_ids: tuple[str, ...]) -> bool:
    for execution_id in dict.fromkeys(execution_ids):
        execution = persistence.rule_executions.get(execution_id)
        if execution is None or execution.rule_id not in _DISCOVERY_BLOCKING_RULES:
            continue
        if execution.result is RuleResult.FAIL:
            return True
    return False


def _existing_rule_execution(workspace: AuditWorkspace, audit_id: str) -> str | None:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT rule_execution_id FROM rule_executions WHERE audit_id=? AND rule_id=? ORDER BY executed_at DESC LIMIT 1",
            (audit_id, RULE_ID),
        ).fetchone()
        return str(row[0]) if row else None
    finally:
        connection.close()


def _dataset_row(workspace: AuditWorkspace, dataset_id: str):
    try:
        with ObservabilityStore(workspace.root) as store:
            return next((row for row in store.datasets() if str(row["dataset_id"]) == dataset_id), None)
    except Exception:
        return None


def _positive_float(raw: str | None, default: float) -> float:
    if raw is None or not str(raw).strip():
        return default
    value = float(str(raw).strip())
    if value <= 0 or value >= 3600:
        raise ValueError("external observability timeout must be > 0 and < 3600 seconds")
    return value
