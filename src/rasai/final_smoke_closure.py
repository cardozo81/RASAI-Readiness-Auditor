"""Final closure for defects exposed by the last governed-pipeline human smoke.

This module is intentionally narrow. It reasserts final ownership after runtime
installers have run and keeps catalog projection deterministic.
"""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

_INSTALLED = False


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone() is not None


def _saved_improvement_feature(workspace: Any, audit_id: str) -> dict[str, Any]:
    from rasai.post_smoke_alignment import _saved_configuration

    payload = _saved_configuration(workspace, audit_id)
    settings = payload.get("settings")
    if not isinstance(settings, Mapping):
        return {}
    feature = settings.get("improvement_intelligence")
    return dict(feature) if isinstance(feature, Mapping) else {}


def _install_improvement_final_binding() -> None:
    """Rebind CAT-08 after the runtime installer and project its frozen settings."""
    from rasai import audit_phase_runtime as phase
    from rasai import improvement_intelligence as improvement
    from rasai import post_smoke_alignment as alignment

    alignment._install_improvement_governed_hook()
    hook = phase._AI_HOOKS.get("IMPROVEMENT_INTELLIGENCE")
    if hook is None:
        return
    current = hook.callback
    if bool(getattr(current, "_rasai_final_smoke_improvement", False)):
        return

    def governed(*, audit_id: str, workspace: Any, evidence_snapshot: Any):
        required = alignment._cat08_required(workspace, audit_id)
        feature = _saved_improvement_feature(workspace, audit_id) if required else {}
        names = (
            improvement.ENABLED_ENV,
            improvement.DOMAINS_ENV,
            improvement.MAX_RECOMMENDATIONS_ENV,
            improvement.TIMEOUT_ENV,
        )
        previous = {name: os.environ.get(name) for name in names}
        if required:
            os.environ[improvement.ENABLED_ENV] = "true"
            mapping = {
                improvement.DOMAINS_ENV: feature.get("domains"),
                improvement.MAX_RECOMMENDATIONS_ENV: feature.get("max_recommendations"),
                improvement.TIMEOUT_ENV: feature.get("timeout_seconds"),
            }
            for name, value in mapping.items():
                if value not in (None, ""):
                    os.environ[name] = str(value)
        try:
            return current(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=evidence_snapshot,
            )
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

    governed._rasai_final_smoke_improvement = True
    governed._rasai_original = current
    phase.register_ai_hook("IMPROVEMENT_INTELLIGENCE", governed, order=hook.order)


def _install_common_crawl_final_binding() -> None:
    """Own Common Crawl in collection and BR-GEO-060 in deterministic pre-seal."""
    from rasai import audit_phase_runtime as phase
    from rasai import external_observability_runtime as external
    from rasai import external_sari
    from rasai.external_observability_policy import COMMON_CRAWL_ENABLED_ENV
    from rasai.governed_optional_runtime import _aggregate
    from rasai.persistence import AuditPersistence
    from rasai.standards_service_registry import service, service_state

    existing = phase._COLLECTION_HOOKS.get("EXTERNAL_OBSERVABILITY")
    if existing is None:
        return
    base = existing.callback
    if bool(getattr(base, "_rasai_final_smoke_common_crawl", False)):
        return

    def collector(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        result = dict(
            base(
                audit_id=audit_id,
                workspace=workspace,
                source_blocked=source_blocked,
            )
            or {}
        )
        services = dict(result.get("services") or {})
        environment = dict(os.environ)
        state_info = service_state(service("common-crawl"), environment)
        common = external._base_result(state_info)

        if source_blocked:
            common.update(
                targets_attempted=0,
                targets_succeeded=0,
                datasets=[],
                errors=[],
                collection_state="BLOCKED",
                reason="SOURCE_BLOCKED",
            )
        elif not bool(state_info.get("effective_enabled")):
            state = str(state_info.get("state") or "DISABLED").upper()
            common.update(
                targets_attempted=0,
                targets_succeeded=0,
                datasets=[],
                errors=[],
                collection_state=state,
                reason="SERVICE_NOT_ENABLED",
            )
        else:
            max_urls = external.common_crawl_max_urls(
                environment.get(external.COMMON_CRAWL_MAX_URLS_ENV)
            )
            if max_urls <= 0:
                common.update(
                    targets_attempted=0,
                    targets_succeeded=0,
                    datasets=[],
                    errors=[],
                    collection_state="NO_DATA",
                    reason="COMMON_CRAWL_MAX_URLS_ZERO",
                )
            else:
                try:
                    dataset_id = external.collect_common_crawl_history(
                        audit_workspace=workspace.root,
                        max_urls=max_urls,
                        collection_count=external.common_crawl_index_count(
                            environment.get(external.COMMON_CRAWL_INDEX_COUNT_ENV)
                        ),
                        timeout=external._positive_float(
                            environment.get(external.STANDARDS_TIMEOUT_ENV),
                            external.DEFAULT_STANDARDS_TIMEOUT_SECONDS,
                        ),
                    )
                    dataset_state, dataset_errors = external_sari.common_crawl_dataset_health(
                        workspace, dataset_id
                    )
                    common.update(
                        targets_attempted=1,
                        targets_succeeded=0 if dataset_state == "FAILED_RETRYABLE" else 1,
                        datasets=[dataset_id],
                        errors=list(dataset_errors),
                        collection_state=dataset_state,
                        reason=(
                            "COMMON_CRAWL_PROVIDER_ERRORS"
                            if dataset_state == "FAILED_RETRYABLE"
                            else "COMMON_CRAWL_PARTIAL_PROVIDER_ERRORS"
                            if dataset_state == "PARTIAL"
                            else "NO_COMMON_CRAWL_CAPTURE_OBSERVED"
                            if dataset_state == "NO_DATA"
                            else None
                        ),
                        scope="URL",
                    )
                except Exception as exc:
                    common.update(
                        targets_attempted=1,
                        targets_succeeded=0,
                        datasets=[],
                        errors=[external._safe_error("COMMON_CRAWL", exc)],
                        collection_state="ERROR",
                        reason=type(exc).__name__,
                    )

        services["common-crawl"] = common
        external._upsert_service_run(
            audit_id=audit_id,
            workspace=workspace,
            service_id="common-crawl",
            result=common,
        )
        states = [
            str(item.get("collection_state") or item.get("service_state") or "UNKNOWN")
            for item in services.values()
        ]
        return {"collection_state": _aggregate(states), "services": services}

    collector._rasai_final_smoke_common_crawl = True
    collector._rasai_original = base
    phase.register_collection_hook("EXTERNAL_OBSERVABILITY", collector, order=existing.order)

    def persisted_only(*, audit_workspace: Any, **_kwargs: Any) -> str:
        from rasai.post_smoke_hotfix import _latest_common_crawl_dataset

        return _latest_common_crawl_dataset(audit_workspace)

    persisted_only._rasai_final_smoke_persisted_only = True
    external_sari.collect_common_crawl_history = persisted_only

    def materialize(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        if source_blocked:
            return {"status": "SKIPPED", "reason": "SOURCE_BLOCKED"}
        connection = sqlite3.connect(workspace.database)
        try:
            rule_ids = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT rule_execution_id FROM rule_executions "
                    "WHERE audit_id=? ORDER BY executed_at,rule_execution_id",
                    (audit_id,),
                ).fetchall()
                if row[0]
            )
        finally:
            connection.close()
        with AuditPersistence(workspace) as persistence:
            result = external_sari.materialize_common_crawl_corroboration(
                audit_id=audit_id,
                rule_execution_ids=rule_ids,
                persistence=persistence,
                workspace=workspace,
            )
        return {
            "status": result.state,
            "dataset_id": result.dataset_id,
            "rule_execution_ids": list(result.rule_execution_ids),
            "observed_url_count": result.observed_url_count,
            "reason": result.reason,
        }

    materialize._rasai_final_smoke_common_crawl = True
    phase.register_deterministic_hook("COMMON_CRAWL_CORROBORATION", materialize, order=90)



def _deduplicate_request_remediation_events(events: Any) -> list[dict[str, Any]]:
    """Remove only derived request symptoms when the same sample/resource has CORS."""
    normalized = [dict(item) for item in events]
    cors_keys = {
        (
            str(item.get("sample_key") or ""),
            str(item.get("normalized_url") or item.get("source_url") or ""),
        )
        for item in normalized
        if str(item.get("family") or "").upper() == "CORS"
    }
    filtered: list[dict[str, Any]] = []
    for item in normalized:
        key = (
            str(item.get("sample_key") or ""),
            str(item.get("normalized_url") or item.get("source_url") or ""),
        )
        is_request_symptom = (
            str(item.get("error_type") or "").upper() == "REQUEST_FAILED"
            and str(item.get("family") or "").upper() in {"REQUEST_OTHER", "CONSOLE_RUNTIME"}
        )
        if is_request_symptom and key in cors_keys:
            continue
        filtered.append(item)
    return filtered


def _install_request_remediation_dedup() -> None:
    """Keep raw events, but do not count a CORS cause and its request symptom twice."""
    from rasai import request_remediation_intelligence as request

    current = request.group_request_error_evidence
    if bool(getattr(current, "_rasai_final_smoke_dedup", False)):
        return

    def grouped(events: Any, sample_universe: Any, *, audit_id: str = ""):
        filtered = _deduplicate_request_remediation_events(events)
        return current(filtered, sample_universe, audit_id=audit_id)

    grouped._rasai_final_smoke_dedup = True
    grouped._rasai_original = current
    request.group_request_error_evidence = grouped


def _install_cat05_partial_projection() -> None:
    """Do not call CAT-05 complete when requested Common Crawl never executed."""
    from rasai import catalog_report_governance as governance
    from rasai import catalog_report_page as page

    current = page._catalog_status
    if bool(getattr(current, "_rasai_final_smoke_cat05", False)):
        return

    def status(database: Any, data: Any, catalog_id: str):
        value, tone, detail = current(database, data, catalog_id)
        if catalog_id != "CAT-05" or catalog_id not in getattr(data, "selected", set()):
            return value, tone, detail
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        try:
            if not _table_exists(connection, "standards_service_runs"):
                return value, tone, detail
            row = connection.execute(
                "SELECT * FROM standards_service_runs "
                "WHERE audit_id=? AND service_id='common-crawl' ORDER BY rowid DESC LIMIT 1",
                (data.audit_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return value, tone, detail
        state = str(row["state"] or "").upper()
        requested = bool(row["requested"])
        enabled = bool(row["effective_enabled"])
        attempted = int(row["targets_attempted"] or 0)
        details: dict[str, Any] = {}
        try:
            parsed = json.loads(str(row["details_json"] or "{}"))
            if isinstance(parsed, dict):
                details = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        reason = str(details.get("reason") or "")
        raw_errors = details.get("errors")
        has_errors = isinstance(raw_errors, list) and bool(raw_errors)
        broken_collection = requested and enabled and (
            state in {"ERROR", "FAILED_RETRYABLE", "PARTIAL", "BLOCKED"}
            or has_errors
            or (
                attempted == 0
                and reason in {
                    "PRE_SCORING_COLLECTION_STATE_NOT_FOUND",
                    "COMMON_CRAWL_PRESEAL_DATASET_MISSING",
                }
            )
        )
        if broken_collection:
            return (
                "PARCIAL",
                "warn",
                "Search Intelligence possui resultados, mas Common Crawl foi solicitado e não concluiu a coleta planejada nesta AUD.",
            )
        return value, tone, detail

    status._rasai_final_smoke_cat05 = True
    status._rasai_original = current
    page._catalog_status = status
    governance._catalog_status = status


def _install_cost_fulfillment_guard() -> None:
    """Cost adherence is not comparable while any required work item is incomplete."""
    from rasai import console_cost_confirmation as cost

    current = cost._build_outcome
    if bool(getattr(current, "_rasai_final_smoke_fulfillment", False)):
        return

    def build(state: Any, forecast: Any):
        outcome = current(state, forecast)
        if outcome is None:
            return None
        workspace, _ = cost.artifact_status(state)
        if workspace is None:
            return outcome
        database = Path(workspace) / "audit.db"
        if not database.is_file():
            return outcome
        connection = sqlite3.connect(database)
        try:
            if not _table_exists(connection, "audit_fulfillment_work_items"):
                return outcome
            row = connection.execute(
                """SELECT COUNT(*) FROM audit_fulfillment_work_items
                   WHERE audit_id=? AND required=1
                     AND UPPER(COALESCE(status,'')) NOT IN
                         ('SUCCESS','COMPLETE','COMPLETED','FINAL')""",
                (str(getattr(state, "audit_id", "") or ""),),
            ).fetchone()
            incomplete = int(row[0] or 0) if row else 0
        finally:
            connection.close()
        if incomplete <= 0:
            return outcome
        notes = tuple(outcome.notes) + (
            f"{incomplete} requisito(s) obrigatório(s) permanece(m) incompleto(s); "
            "o custo observado não recebe classificação de aderência até o fulfillment finalizar.",
        )
        return replace(
            outcome,
            comparable=False,
            deviation=None,
            deviation_percent=None,
            status="NÃO COMPARÁVEL",
            relation="execução obrigatória incompleta; custo observado é apenas parcial",
            notes=notes,
        )

    build._rasai_final_smoke_fulfillment = True
    build._rasai_original = current
    cost._build_outcome = build


def install() -> None:
    global _INSTALLED
    _install_improvement_final_binding()
    _install_common_crawl_final_binding()
    _install_request_remediation_dedup()
    _install_cat05_partial_projection()
    _install_cost_fulfillment_guard()
    _INSTALLED = True


__all__ = ["install"]
