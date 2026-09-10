"""Execution worker for durable RASAi control-plane jobs.

Workers are separate from the HTTP process. Jobs use structured, secret-free payloads;
no persisted shell command or arbitrary argv is accepted. SaaS schedules materialize
into the same durable queue before a worker claims work.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping

from rasai.platform.database import open_platform_store
from rasai.platform.reporting import write_platform_site
from rasai.platform.saas_scheduling import normalize_scheduled_urls
from rasai.platform.usage_ingestion import ingest_audit_usage, record_search_monitor_usage
from rasai.search_intelligence.monitoring import execute_registered_query
from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository
from rasai.secret_safety import redact_text


@dataclass(frozen=True, slots=True)
class WorkerResult:
    result_ref: str | None
    metadata: dict[str, Any]


def _text(payload: Mapping[str, Any], name: str, default: str | None = None) -> str | None:
    value = payload.get(name, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"execution payload field {name} must be text")
    return value.strip()


def _integer(payload: Mapping[str, Any], name: str, default: int, *, minimum: int, maximum: int) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"execution payload field {name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"execution payload field {name} must be between {minimum} and {maximum}")
    return value


def _boolean(payload: Mapping[str, Any], name: str, default: bool = False) -> bool:
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(f"execution payload field {name} must be boolean")
    return value


def _audit_arguments(store: Any, job: Any, audits_root: Path) -> list[str]:
    prop = next((item for item in store.list_properties(job.project_id) if item.property_id == job.property_id), None)
    if prop is None:
        raise KeyError(f"execution property not found: {job.property_id}")
    environment = next(
        (item for item in store.list_environments(prop.property_id) if item.environment_id == job.environment_id),
        None,
    )
    if environment is None:
        raise KeyError(f"execution environment not found: {job.environment_id}")
    project = next((item for item in store.list_projects() if item.project_id == job.project_id), None)
    if project is None:
        raise KeyError(f"execution project not found: {job.project_id}")

    payload = job.payload
    language = _text(payload, "language", "pt-BR") or "pt-BR"
    market = _text(payload, "market", "BR") or "BR"
    max_pages = _integer(payload, "max_pages", 100, minimum=1, maximum=100000)
    device = _text(payload, "device_context")
    if device is not None and device not in {"mobile", "desktop", "both"}:
        raise ValueError("execution payload device_context must be mobile, desktop or both")
    ai_provider = _text(payload, "ai_provider", "none") or "none"
    if ai_provider not in {"none", "openai", "deepseek", "mimo", "auto"}:
        raise ValueError("execution payload contains unsupported ai_provider")
    ai_model = _text(payload, "ai_model")
    web_performance = _boolean(payload, "web_performance", False)
    content_remediation = _boolean(payload, "ai_content_remediation", False)

    raw_urls = payload.get("urls")
    if raw_urls is None:
        targets = (environment.base_origin,)
    else:
        if not isinstance(raw_urls, list) or any(not isinstance(item, str) for item in raw_urls):
            raise ValueError("execution payload urls must be an array of strings")
        targets = normalize_scheduled_urls(
            raw_urls,
            property_hostname=prop.hostname,
            environment_origin=environment.base_origin,
        )

    allowed = {
        "language", "market", "max_pages", "device_context", "ai_provider", "ai_model",
        "web_performance", "ai_content_remediation", "urls",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError("unsupported AUDIT execution payload field(s): " + ", ".join(unknown))

    argv = [
        "audit",
        *targets,
        "--project", project.name,
        "--language", language,
        "--market", market,
        "--max-pages", str(max_pages),
        "--audits-root", str(audits_root),
        "--ai-provider", ai_provider,
    ]
    if device is not None:
        argv.extend(("--device-context", device))
    if ai_model is not None:
        argv.extend(("--ai-model", ai_model))
    argv.append("--ai-content-remediation" if content_remediation else "--no-ai-content-remediation")
    argv.append("--web-performance" if web_performance else "--no-web-performance")
    return argv


def _run_audit(store: Any, job: Any, audits_root: Path) -> WorkerResult:
    from rasai.entrypoint import main as rasai_main

    previous_ids = {
        item.audit_id
        for item in store.list_audits(property_id=job.property_id, environment_id=job.environment_id)
    }
    code = rasai_main(_audit_arguments(store, job, audits_root))
    if code != 0:
        raise RuntimeError(f"RASAi audit execution returned exit code {code}")
    audits = store.list_audits(property_id=job.property_id, environment_id=job.environment_id)
    new_audits = [item for item in audits if item.audit_id not in previous_ids]
    latest = max(new_audits or audits, key=lambda item: item.event_time) if audits else None
    metadata: dict[str, Any] = {"audit_id": latest.audit_id if latest is not None else None}
    if latest is not None and hasattr(store, "record_usage_once"):
        try:
            ingest_audit_usage(
                store,
                latest,
                organization_id=job.organization_id,
                project_id=job.project_id,
                property_id=job.property_id,
                environment_id=job.environment_id,
                user_id=job.requested_by,
                job_id=job.job_id,
            )
        except Exception as exc:
            # Usage projection is derived. It must never invalidate successful audit
            # evidence, and can be replayed idempotently later.
            metadata["usage_projection_warning"] = redact_text(str(exc))
    return WorkerResult(result_ref=(latest.audit_id if latest is not None else None), metadata=metadata)


def _run_search_monitor(store: Any, job: Any, audits_root: Path) -> WorkerResult:
    query_id = _text(job.payload, "query_id")
    if not query_id:
        raise ValueError("SEARCH_MONITOR execution requires payload.query_id")
    if set(job.payload) != {"query_id"}:
        raise ValueError("SEARCH_MONITOR execution accepts only payload.query_id")
    with open_search_monitoring_repository(audits_root=audits_root) as repository:
        query = repository.get_query(query_id)
        if query is None:
            raise KeyError(f"Search monitor query not found: {query_id}")
        if (
            query.project_id != job.project_id
            or query.property_id != job.property_id
            or query.environment_id != job.environment_id
        ):
            raise ValueError("Search monitor query does not belong to execution job scope")
        run = execute_registered_query(
            repository,
            query,
            audits_root=audits_root,
            environment=os.environ,
        )
    if run.status == "FAILED":
        raise RuntimeError(run.error_message or run.error_code or "Search monitor execution failed")
    metadata: dict[str, Any] = {
        "monitor_run_id": run.monitor_run_id,
        "query_id": query_id,
        "status": run.status,
    }
    if hasattr(store, "record_usage_once"):
        try:
            record_search_monitor_usage(store, job, run)
        except Exception as exc:
            metadata["usage_projection_warning"] = redact_text(str(exc))
    return WorkerResult(result_ref=run.manifest_ref, metadata=metadata)


def _run_report_refresh(store: Any, job: Any, audits_root: Path) -> WorkerResult:
    surface = _text(job.payload, "surface", "portfolio") or "portfolio"
    if surface != "portfolio" or set(job.payload) - {"surface"}:
        raise ValueError("REPORT_REFRESH currently supports only payload.surface=portfolio")
    report = write_platform_site(store, audits_root / "platform-report")
    try:
        result_ref = report.relative_to(audits_root).as_posix()
    except ValueError:
        result_ref = report.name
    if hasattr(store, "record_usage_once"):
        try:
            store.record_usage_once(
                source_key=f"job:{job.job_id}:report-refresh",
                organization_id=job.organization_id,
                project_id=job.project_id,
                property_id=job.property_id,
                category="REPORT_REFRESH",
                quantity=1,
                unit="execution",
                metadata={
                    "environment_id": job.environment_id,
                    "user_id": job.requested_by,
                    "job_id": job.job_id,
                    "operation": "REPORT_REFRESH",
                    "resource_type": "REPORT",
                    "status": "SUCCESS",
                },
            )
        except Exception:
            pass
    return WorkerResult(result_ref=result_ref, metadata={"surface": "portfolio"})


def execute_job(store: Any, job: Any, *, audits_root: str | Path = "audits") -> WorkerResult:
    root = Path(audits_root)
    if job.job_type == "AUDIT":
        return _run_audit(store, job, root)
    if job.job_type == "SEARCH_MONITOR":
        return _run_search_monitor(store, job, root)
    if job.job_type == "REPORT_REFRESH":
        return _run_report_refresh(store, job, root)
    raise ValueError(f"unsupported execution job type: {job.job_type}")


def _finish(store: Any, job_id: str, worker_id: str, **kwargs: Any) -> Any:
    final = store.finish_execution_job(job_id, worker_id, **kwargs)
    if hasattr(store, "reconcile_schedule_job"):
        try:
            store.reconcile_schedule_job(job_id)
        except Exception:
            # Occurrence reconciliation is derived from the durable job and may be
            # retried; it never rewrites the execution result.
            pass
    return final


def run_one(
    worker_id: str,
    *,
    audits_root: str | Path = "audits",
    lease_seconds: int = 900,
) -> Any | None:
    """Materialize due schedules, claim and execute one durable job."""
    with open_platform_store(audits_root=audits_root) as store:
        if hasattr(store, "materialize_due_schedules"):
            store.materialize_due_schedules(limit=100)
        job = store.claim_execution_job(worker_id, lease_seconds=lease_seconds)
        if job is None:
            return None
        store.start_execution_job(job.job_id, worker_id)
        try:
            result = execute_job(store, job, audits_root=audits_root)
        except Exception as exc:
            return _finish(
                store,
                job.job_id,
                worker_id,
                succeeded=False,
                error=redact_text(str(exc)),
            )
        return _finish(
            store,
            job.job_id,
            worker_id,
            succeeded=True,
            result_ref=result.result_ref,
            result_metadata=result.metadata,
        )
