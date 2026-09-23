"""Final integration alignment for completion and selective reprocessing.

These fixes sit deliberately outside scoring policy:

* M24 provider schema/prompt and local validator must consume one canonical per-resource
  evidence universe, including both deterministic baseline evidence and diagnostic
  evidence for that same resource.
* Selective M21 recovery must classify a latest CrUX 404/NOT_FOUND as NO_DATA in AUTO
  field mode, exactly like initial execution, instead of manufacturing a retryable
  ``CRUX:UNAVAILABLE`` after the provider has explicitly reported no population record.
"""
from __future__ import annotations

from types import SimpleNamespace
import sqlite3
from typing import Any, Mapping

_INSTALLED = False


def canonical_resource_evidence(
    facts: list[dict[str, Any]],
) -> dict[str, frozenset[str]]:
    buckets: dict[str, list[str]] = {}
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        if str(fact.get("scoring_role") or "") != "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE":
            continue
        resource = str(fact.get("category") or "").strip().upper()
        if resource not in {"ROBOTS", "SITEMAP"}:
            continue
        raw_ids = fact.get("evidence_ids")
        if not isinstance(raw_ids, (list, tuple, set, frozenset)):
            continue
        bucket = buckets.setdefault(resource, [])
        for raw in raw_ids:
            evidence_id = str(raw or "").strip()
            if evidence_id and evidence_id not in bucket:
                bucket.append(evidence_id)
    return {
        resource: frozenset(values)
        for resource, values in buckets.items()
        if values
    }


def _install_final_m24_resource_alignment() -> None:
    """Wrap the final M24 call chain after routing/fulfillment hooks are installed."""
    from rasai import m24_ai

    original = m24_ai._call
    if bool(getattr(original, "_rasai_final_resource_universe_alignment", False)):
        return

    def call_with_final_resource_alignment(candidate: Any, *args: Any, **kwargs: Any):
        facts = kwargs.get("facts")
        if isinstance(facts, list):
            canonical = canonical_resource_evidence(facts)
            if canonical:
                kwargs = dict(kwargs)
                kwargs["resource_evidence"] = canonical
        return original(candidate, *args, **kwargs)

    call_with_final_resource_alignment._rasai_final_resource_universe_alignment = True  # type: ignore[attr-defined]
    call_with_final_resource_alignment._rasai_original = original  # type: ignore[attr-defined]
    m24_ai._call = call_with_final_resource_alignment


def _clean_auto_crux_no_data_errors(value: Any) -> str | None:
    kept: list[str] = []
    for part in (item.strip() for item in str(value or "").split(";") if item.strip()):
        normalized = part.upper().replace("-", "_")
        if normalized in {
            "CRUX:NOT_FOUND",
            "CRUX:NOTFOUND",
            "CRUX:404",
            "CRUX:NO_DATA",
            "CRUX:UNAVAILABLE",
        }:
            continue
        kept.append(part)
    return ";".join(dict.fromkeys(kept)) if kept else None


def _latest_crux_attempts(connection: sqlite3.Connection, audit_id: str) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """SELECT * FROM web_performance_attempts
           WHERE audit_id=? AND service='CRUX_API'
           ORDER BY snapshot_id,created_at DESC,rowid DESC""",
        (audit_id,),
    ).fetchall()
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = dict(row)
        snapshot_id = str(current.get("snapshot_id") or "")
        if snapshot_id and snapshot_id not in output:
            output[snapshot_id] = current
    return output


def _latest_observations(connection: sqlite3.Connection, audit_id: str) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """SELECT * FROM web_performance_observations
           WHERE audit_id=?
           ORDER BY snapshot_id,captured_at DESC,rowid DESC""",
        (audit_id,),
    ).fetchall()
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = dict(row)
        snapshot_id = str(current.get("snapshot_id") or "")
        if snapshot_id and snapshot_id not in output:
            output[snapshot_id] = current
    return output


def _reconcile_recovery_crux_no_data(workspace: Any, audit_id: str) -> bool | None:
    """Return completion after reconciling AUTO-mode latest CrUX NO_DATA, or None."""
    from rasai.execution_completion_reliability import _is_crux_no_data, _observation_usable

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            "SELECT * FROM web_performance_runs WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        if run is None or str(run["field_source"] or "").casefold() != "auto":
            return None

        latest_attempts = _latest_crux_attempts(connection, audit_id)
        no_data_snapshots = {
            snapshot_id: attempt
            for snapshot_id, attempt in latest_attempts.items()
            if str(attempt.get("status") or "").upper() == "NO_DATA" or _is_crux_no_data(attempt)
        }
        if not no_data_snapshots:
            return None

        latest_observations = _latest_observations(connection, audit_id)
        with connection:
            for snapshot_id, attempt in no_data_snapshots.items():
                attempt_id = str(attempt.get("attempt_id") or "")
                if attempt_id:
                    connection.execute(
                        "UPDATE web_performance_attempts SET status='NO_DATA',error_code='NO_DATA' WHERE attempt_id=?",
                        (attempt_id,),
                    )
                observation = latest_observations.get(snapshot_id)
                if observation is None:
                    continue
                cleaned = _clean_auto_crux_no_data_errors(observation.get("error_summary"))
                if _observation_usable(observation):
                    status = "SUCCESS" if not cleaned else "PARTIAL"
                else:
                    status = "UNAVAILABLE"
                connection.execute(
                    """UPDATE web_performance_observations
                       SET status=?,error_summary=?,crux_http_status=?
                       WHERE observation_id=?""",
                    (
                        status,
                        cleaned,
                        attempt.get("http_status"),
                        str(observation.get("observation_id") or ""),
                    ),
                )
                observation["status"] = status
                observation["error_summary"] = cleaned

            # Re-read latest observations after the updates and recompute only the run
            # completion projection. Historical attempts remain append-only for audit/cost.
            latest_observations = _latest_observations(connection, audit_id)
            statuses = [str(item.get("status") or "") for item in latest_observations.values()]
            contexts = int(run["context_attempts"] or len(statuses))
            successful = sum(status == "SUCCESS" for status in statuses)
            partial = sum(status == "PARTIAL" for status in statuses)
            usable = successful + partial
            if contexts == 0:
                run_status, reason = "NO_CONTEXTS", "NO_RENDERED_CONTEXTS"
            elif successful >= contexts:
                run_status, reason = "SUCCESS", None
            elif usable:
                run_status, reason = "PARTIAL", "ONE_OR_MORE_CONTEXTS_INCOMPLETE"
            else:
                run_status, reason = "UNAVAILABLE", "NO_SUCCESSFUL_WEB_PERFORMANCE_CONTEXTS"
            connection.execute(
                """UPDATE web_performance_runs
                   SET status=?,successful_contexts=?,reason=?
                   WHERE audit_id=?""",
                (run_status, successful, reason, audit_id),
            )
        return contexts > 0 and run_status == "SUCCESS"
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def _install_web_performance_recovery_alignment() -> None:
    from rasai import reprocess_measurements

    original = reprocess_measurements.recover_web_performance
    if bool(getattr(original, "_rasai_crux_no_data_recovery_alignment", False)):
        return

    def recover_web_performance_aligned(*, workspace: Any, audit_id: str, item: Any) -> bool:
        original_success = bool(original(workspace=workspace, audit_id=audit_id, item=item))
        if original_success:
            return True

        # The normal execution reconciler may already know how to relabel the latest
        # attempt. Invoke it for consistent persistence, then remove only the synthetic
        # recovery-side CRUX:UNAVAILABLE that accompanies the same 404 NO_DATA outcome.
        try:
            from rasai.execution_completion_reliability import _reconcile_crux_no_data

            _reconcile_crux_no_data(
                workspace,
                audit_id,
                SimpleNamespace(
                    status="PARTIAL",
                    successful_contexts=0,
                    partial_contexts=0,
                ),
            )
        except (ImportError, sqlite3.Error, TypeError, ValueError):
            pass

        reconciled = _reconcile_recovery_crux_no_data(workspace, audit_id)
        return original_success if reconciled is None else bool(reconciled)

    recover_web_performance_aligned._rasai_crux_no_data_recovery_alignment = True  # type: ignore[attr-defined]
    recover_web_performance_aligned._rasai_original = original  # type: ignore[attr-defined]
    reprocess_measurements.recover_web_performance = recover_web_performance_aligned


def install() -> None:
    """Install after fulfillment and dynamic AI routing so these are final alignments."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_final_m24_resource_alignment()
    _install_web_performance_recovery_alignment()
    _INSTALLED = True
