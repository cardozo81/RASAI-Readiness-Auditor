"""Reliability fixes for execution completion without changing scoring formulas.

This integration layer closes three false/infinite-partial paths observed in real AUDs:

* CrUX HTTP 404/NOT_FOUND means that Chrome UX Report has no eligible field-data
  population for the requested URL/form factor. It is a deterministic NO_DATA outcome,
  not a retryable transport failure when Lighthouse/lab evidence is otherwise usable.
* A session execution profile owns its GSC policy for the whole active profile session,
  including report/finalization wrappers that execute after the inner audit call returns.
* M24 technical-AI structured output receives a resource-scoped JSON Schema so a provider
  cannot legally attach SITEMAP evidence to a ROBOTS assessment or vice versa.

The module is intentionally additive. It does not alter SARI-001/SCORE-GEO-004, AI AUTO
ranking, pricing, quarantine, retry limits, provider selection, or deterministic findings.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import os
import sqlite3
from typing import Any, Iterator, Mapping

_INSTALLED = False
_CRUX_NO_DATA_HTTP = 404
_CRUX_NO_DATA_CODES = frozenset({"NOT_FOUND", "NOTFOUND"})
_GSC_BASELINE_BY_STATE: dict[int, tuple[bool, str | None]] = {}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone() is not None


def _is_crux_no_data(row: Mapping[str, Any]) -> bool:
    if str(row.get("service") or "").upper() != "CRUX_API":
        return False
    try:
        status = int(row.get("http_status")) if row.get("http_status") is not None else None
    except (TypeError, ValueError):
        status = None
    code = str(row.get("error_code") or "").strip().upper().replace("-", "_")
    message = str(row.get("error_message") or "").casefold()
    return status == _CRUX_NO_DATA_HTTP and (
        code in _CRUX_NO_DATA_CODES or "not found" in message or "no record" in message
    )


def _clean_crux_no_data_errors(value: Any) -> str | None:
    parts = [part.strip() for part in str(value or "").split(";") if part.strip()]
    kept = []
    for part in parts:
        normalized = part.upper().replace("-", "_")
        if normalized in {"CRUX:NOT_FOUND", "CRUX:NOTFOUND", "CRUX:404"}:
            continue
        kept.append(part)
    return ";".join(kept) if kept else None


def _observation_usable(row: Mapping[str, Any]) -> bool:
    columns = (
        "performance_score",
        "accessibility_score",
        "best_practices_score",
        "seo_score",
        "agentic_browsing_score",
        "fcp_lab_ms",
        "speed_index_lab_ms",
        "lcp_lab_ms",
        "tbt_lab_ms",
        "cls_lab",
        "lcp_p75_ms",
        "inp_p75_ms",
        "cls_p75",
    )
    return any(row.get(name) is not None for name in columns)


def _reconcile_crux_no_data(workspace: Any, audit_id: str, result: Any) -> Any:
    """Reclassify provider-confirmed CrUX population absence as NO_DATA.

    The direct CrUX API uses HTTP 404/NOT_FOUND when no record is available for the
    requested URL/form factor. Repeating the same request does not make this a technical
    retry. Lab/Lighthouse evidence remains valid and can complete Web Performance.
    """
    database = getattr(workspace, "database", None)
    if database is None:
        return result
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    corrected = 0
    run_status: str | None = None
    usable = partial = 0
    try:
        if not _table_exists(connection, "web_performance_attempts") or not _table_exists(
            connection, "web_performance_observations"
        ):
            return result
        attempts = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM web_performance_attempts WHERE audit_id=? AND service='CRUX_API'",
                (audit_id,),
            ).fetchall()
        ]
        no_data = [row for row in attempts if _is_crux_no_data(row)]
        if not no_data:
            return result

        with connection:
            for attempt in no_data:
                connection.execute(
                    """UPDATE web_performance_attempts
                       SET status='NO_DATA',error_code='NO_DATA'
                       WHERE attempt_id=?""",
                    (str(attempt.get("attempt_id") or ""),),
                )
                snapshot_id = str(attempt.get("snapshot_id") or "")
                observation = connection.execute(
                    "SELECT * FROM web_performance_observations WHERE audit_id=? AND snapshot_id=?",
                    (audit_id, snapshot_id),
                ).fetchone()
                if observation is None:
                    corrected += 1
                    continue
                current = dict(observation)
                cleaned = _clean_crux_no_data_errors(current.get("error_summary"))
                if _observation_usable(current):
                    status = "SUCCESS" if not cleaned else "PARTIAL"
                else:
                    status = "UNAVAILABLE"
                connection.execute(
                    """UPDATE web_performance_observations
                       SET status=?,error_summary=?
                       WHERE observation_id=?""",
                    (status, cleaned, str(current.get("observation_id") or "")),
                )
                corrected += 1

            if _table_exists(connection, "web_performance_runs"):
                run = connection.execute(
                    "SELECT * FROM web_performance_runs WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
                observations = connection.execute(
                    "SELECT status FROM web_performance_observations WHERE audit_id=?",
                    (audit_id,),
                ).fetchall()
                statuses = [str(row["status"] or "") for row in observations]
                usable = sum(status in {"SUCCESS", "PARTIAL"} for status in statuses)
                partial = sum(status == "PARTIAL" for status in statuses)
                attempts_count = int(run["context_attempts"] or 0) if run is not None else len(statuses)
                if attempts_count == 0:
                    run_status = str(run["status"] or "NO_CONTEXTS") if run is not None else "NO_CONTEXTS"
                    reason = run["reason"] if run is not None else "NO_RENDERED_CONTEXTS"
                elif usable == 0:
                    run_status, reason = "UNAVAILABLE", "EXTERNAL_WEB_PERFORMANCE_UNAVAILABLE"
                elif partial or usable < attempts_count:
                    run_status, reason = "PARTIAL", "ONE_OR_MORE_EXTERNAL_COMPONENTS_UNAVAILABLE"
                else:
                    run_status, reason = "SUCCESS", None
                connection.execute(
                    "UPDATE web_performance_runs SET status=?,successful_contexts=?,reason=? WHERE audit_id=?",
                    (run_status, usable, reason, audit_id),
                )
    finally:
        connection.close()

    if not corrected or run_status is None:
        return result
    try:
        return replace(
            result,
            status=run_status,
            successful_contexts=usable,
            partial_contexts=partial,
        )
    except TypeError:
        return result


def _install_crux_no_data_semantics() -> None:
    from rasai import m21_web_performance as m21

    original = m21.execute_m21
    if bool(getattr(original, "_rasai_crux_no_data_semantics", False)):
        return

    def execute_m21_with_crux_no_data(*args: Any, **kwargs: Any):
        result = original(*args, **kwargs)
        workspace = kwargs.get("workspace")
        audit_id = str(kwargs.get("audit_id") or "")
        if workspace is None or not audit_id:
            return result
        return _reconcile_crux_no_data(workspace, audit_id, result)

    execute_m21_with_crux_no_data._rasai_crux_no_data_semantics = True  # type: ignore[attr-defined]
    execute_m21_with_crux_no_data._rasai_original = original  # type: ignore[attr-defined]
    m21.execute_m21 = execute_m21_with_crux_no_data

    # Several public surfaces import execute_m21 by value. Point them to the same final
    # callable before fulfillment wraps it, so console/CLI/recovery observe one contract.
    for module_name in ("cli", "cli_extensions", "audit_runner"):
        try:
            module = __import__(f"rasai.{module_name}", fromlist=[module_name])
        except ImportError:
            continue
        if hasattr(module, "execute_m21"):
            module.execute_m21 = execute_m21_with_crux_no_data


def _resource_schema(resource: str, evidence_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "resource": {"type": "string", "enum": [resource]},
            "verdict": {"type": "string", "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "evidence_ids": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "string", "enum": list(evidence_ids)},
            },
            "rationale_pt": {"type": "string", "minLength": 1, "maxLength": 1600},
        },
        "required": ["resource", "verdict", "confidence", "evidence_ids", "rationale_pt"],
    }


def _harden_m24_schema(schema: Mapping[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    hardened = deepcopy(dict(schema))
    resource_evidence: dict[str, list[str]] = {}
    allowed_codes: list[str] = []
    allowed_evidence: list[str] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        code = str(fact.get("code") or "").strip()
        if code and code not in allowed_codes:
            allowed_codes.append(code)
        evidence_ids = [
            str(item).strip()
            for item in (fact.get("evidence_ids") or [])
            if str(item).strip()
        ]
        for evidence_id in evidence_ids:
            if evidence_id not in allowed_evidence:
                allowed_evidence.append(evidence_id)
        if str(fact.get("scoring_role") or "") != "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE":
            continue
        resource = str(fact.get("category") or "").strip().upper()
        if resource not in {"ROBOTS", "SITEMAP"} or not evidence_ids:
            continue
        bucket = resource_evidence.setdefault(resource, [])
        for evidence_id in evidence_ids:
            if evidence_id not in bucket:
                bucket.append(evidence_id)

    properties = hardened.get("properties")
    if not isinstance(properties, dict):
        return hardened

    actions = properties.get("actions")
    if isinstance(actions, dict) and isinstance(actions.get("items"), dict):
        action_properties = actions["items"].get("properties")
        if isinstance(action_properties, dict):
            if allowed_codes and isinstance(action_properties.get("diagnostic_code"), dict):
                action_properties["diagnostic_code"]["enum"] = allowed_codes
            evidence_schema = action_properties.get("evidence_ids")
            if allowed_evidence and isinstance(evidence_schema, dict) and isinstance(evidence_schema.get("items"), dict):
                evidence_schema["items"]["enum"] = allowed_evidence

    resource_assessments = properties.get("resource_assessments")
    if isinstance(resource_assessments, dict) and resource_evidence:
        branches = [
            _resource_schema(resource, tuple(resource_evidence[resource]))
            for resource in ("ROBOTS", "SITEMAP")
            if resource in resource_evidence
        ]
        resource_assessments["items"] = branches[0] if len(branches) == 1 else {"anyOf": branches}
        resource_assessments["maxItems"] = len(branches)
        resource_assessments["uniqueItems"] = True
    return hardened


def _install_m24_resource_schema() -> None:
    from rasai import m24_ai

    original = m24_ai._candidate_payload
    if bool(getattr(original, "_rasai_resource_schema_hardened", False)):
        return

    def candidate_payload_hardened(
        candidate: Any,
        *,
        schema: dict[str, Any],
        instructions: str,
        facts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return original(
            candidate,
            schema=_harden_m24_schema(schema, facts),
            instructions=instructions,
            facts=facts,
        )

    candidate_payload_hardened._rasai_resource_schema_hardened = True  # type: ignore[attr-defined]
    candidate_payload_hardened._rasai_original = original  # type: ignore[attr-defined]
    m24_ai._candidate_payload = candidate_payload_hardened
    # Schema semantics changed materially; keep attempt/report provenance explicit.
    m24_ai.CONTRACT_VERSION = "M24-TECHNICAL-REMEDIATION-v3"


def _apply_gsc_policy_to_environment(readiness: Any, policy: str) -> None:
    from rasai.gsc_scope import GSC_ENABLED_ENV

    if policy == readiness.GSC_PROFILE_IF_COMPATIBLE:
        os.environ.pop(GSC_ENABLED_ENV, None)
    elif policy == readiness.GSC_PROFILE_REQUIRED:
        os.environ[GSC_ENABLED_ENV] = "true"
    elif policy == readiness.GSC_PROFILE_DISABLED:
        os.environ[GSC_ENABLED_ENV] = "false"


def _install_console_gsc_profile_lifetime() -> None:
    """Keep the active profile's GSC decision alive through outer finalizers.

    The existing profile context correctly changes RASAI_GSC_ENABLED while the inner
    audit function runs, but later-installed console wrappers can finalize/enrich the
    report after that context has restored the global environment. The active profile is
    still in force at that point, so restore-on-context-exit is too early.
    """
    try:
        from rasai import console_execution_profile_readiness as readiness
        from rasai import console_execution_profiles as profiles
    except ImportError:
        return

    original_installer = readiness._install_profile_gsc_overlay
    if bool(getattr(original_installer, "_rasai_gsc_profile_lifetime", False)):
        return

    def install_profile_gsc_overlay_with_lifetime() -> None:
        original_installer()
        effective = profiles.effective_profile
        clear = profiles.clear_profile
        if bool(getattr(effective, "_rasai_gsc_profile_lifetime", False)):
            return

        @contextmanager
        def effective_profile_persistent(
            state: Any,
            session: Any | None = None,
        ) -> Iterator[None]:
            current = session or profiles.active_profile(state)
            active = profiles.active_profile(state)
            persist = current is not None and active is current
            if persist and id(state) not in _GSC_BASELINE_BY_STATE:
                from rasai.gsc_scope import GSC_ENABLED_ENV

                _GSC_BASELINE_BY_STATE[id(state)] = (
                    GSC_ENABLED_ENV in os.environ,
                    os.environ.get(GSC_ENABLED_ENV),
                )
            try:
                with effective(state, current):
                    yield
            finally:
                if persist:
                    _apply_gsc_policy_to_environment(readiness, readiness.gsc_profile_policy(current))

        def clear_profile_restoring_gsc(state: Any) -> None:
            baseline = _GSC_BASELINE_BY_STATE.pop(id(state), None)
            clear(state)
            if baseline is None:
                return
            from rasai.gsc_scope import GSC_ENABLED_ENV

            existed, value = baseline
            if existed and value is not None:
                os.environ[GSC_ENABLED_ENV] = value
            else:
                os.environ.pop(GSC_ENABLED_ENV, None)

        effective_profile_persistent._rasai_gsc_profile_lifetime = True  # type: ignore[attr-defined]
        effective_profile_persistent._rasai_original = effective  # type: ignore[attr-defined]
        clear_profile_restoring_gsc._rasai_gsc_profile_lifetime = True  # type: ignore[attr-defined]
        clear_profile_restoring_gsc._rasai_original = clear  # type: ignore[attr-defined]
        profiles.effective_profile = effective_profile_persistent
        profiles.clear_profile = clear_profile_restoring_gsc

    install_profile_gsc_overlay_with_lifetime._rasai_gsc_profile_lifetime = True  # type: ignore[attr-defined]
    install_profile_gsc_overlay_with_lifetime._rasai_original = original_installer  # type: ignore[attr-defined]
    readiness._install_profile_gsc_overlay = install_profile_gsc_overlay_with_lifetime


def _install_gsc_scope_for_console() -> None:
    # CLI already installs this gate explicitly. The interactive console historically
    # installed the collector/OAuth wrappers but omitted the property-scope gate.
    from rasai.gsc_scope_runtime import install as install_gsc_scope_runtime

    install_gsc_scope_runtime()


def install() -> None:
    """Install completion/retry classification fixes exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_crux_no_data_semantics()
    _install_m24_resource_schema()
    _install_console_gsc_profile_lifetime()
    _install_gsc_scope_for_console()
    _INSTALLED = True
