"""Runtime integration for AUD fulfillment and AI evidence eligibility.

The module is installed by the public entrypoints.  It deliberately composes with
existing audit/M21/M23/runtime wrappers instead of changing scoring formulas.
"""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import replace
import sqlite3
from typing import Any, Mapping

from rasai.audit_fulfillment import (
    BLOCKED,
    DISABLED,
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    NOT_APPLICABLE,
    REPLAY_SAFE,
    SUCCESS,
    WAITING_FOR_DATA,
    begin_attempt,
    consolidation_eligible,
    finish_attempt,
    initialize_contract,
    merge_contract_configuration,
    project_report_validity,
    read_summary,
    register_work_item,
    set_work_item_status,
)

_INSTALLED = False
_INITIAL_OPTIONS: ContextVar[dict[str, Any] | None] = ContextVar("rasai_fulfillment_initial_options", default=None)


def _provider_name(provider: Any) -> str:
    return str(getattr(provider, "name", "NONE") or "NONE").strip().upper()


def _provider_requested(provider: Any) -> bool:
    return _provider_name(provider) not in {"", "NONE"}


def _safe_initial_configuration(target: Any, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    provider = kwargs.get("semantic_provider")
    if isinstance(target, str):
        targets = [target]
    else:
        try:
            targets = [str(item) for item in target]
        except TypeError:
            targets = [str(target)]
    return {
        "targets": targets,
        "project_name": kwargs.get("project_name"),
        "language": kwargs.get("language", "pt-BR"),
        "market": kwargs.get("market", "BR"),
        "max_pages": kwargs.get("max_pages", 100),
        "semantic_ai_requested": _provider_requested(provider),
        "semantic_provider": _provider_name(provider),
        "content_remediation": bool(kwargs.get("content_remediation", False)),
        "technical_remediation": bool(kwargs.get("technical_remediation", False)),
    }


def _semantic_requested() -> bool:
    current = _INITIAL_OPTIONS.get() or {}
    return bool(current.get("semantic_ai_requested"))


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone() is not None


def _semantic_prerequisite_reason(semantic_input: Any) -> str | None:
    content = str(getattr(semantic_input, "main_content", "") or "").strip()
    if not content:
        return "AI_WAITING_FOR_DATA:MAIN_CONTENT_UNAVAILABLE"
    evidence = tuple(getattr(semantic_input, "evidence", ()) or ())
    if not evidence:
        return "AI_WAITING_FOR_DATA:SEMANTIC_EVIDENCE_UNAVAILABLE"
    return None


class _GatedSemanticProvider:
    def __init__(self, base: Any, *, requested: bool, m4_failures: frozenset[str]) -> None:
        self.base = base
        self.name = getattr(base, "name", "NONE")
        self.requested = requested
        self.m4_failures = m4_failures
        self.outcomes: dict[str, Any] = {}

    def analyze(self, semantic_input: Any) -> Any:
        from rasai.semantic import ProviderCallResult, ProviderState

        snapshot_id = str(getattr(semantic_input, "snapshot_id", ""))
        reason = None
        if snapshot_id in self.m4_failures:
            reason = "AI_WAITING_FOR_DATA:EXTRACTION_FAILED"
        if reason is None:
            reason = _semantic_prerequisite_reason(semantic_input)
        # A configured AI can be intentionally suppressed by source-quality fail-fast.
        if reason is None and self.requested and _provider_name(self.base) == "NONE":
            reason = "AI_WAITING_FOR_DATA:SOURCE_EVIDENCE_BLOCKED"
        if reason is not None:
            result = ProviderCallResult(ProviderState.UNAVAILABLE, reason=reason)
        else:
            result = self.base.analyze(semantic_input)
        self.outcomes[snapshot_id] = result
        return result


def _record_semantic_outcome(*, workspace: Any, audit_id: str, snapshot_id: str, result: Any) -> None:
    from rasai.semantic import ProviderState

    state = getattr(result, "state", None)
    reason = str(getattr(result, "reason", "") or "")
    if reason.startswith("AI_WAITING_FOR_DATA:"):
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="SEMANTIC_AI",
            scope_key=snapshot_id,
            status=WAITING_FOR_DATA,
            error_class="PREREQUISITE",
            error_code=reason.split(":", 1)[1],
            error_message=reason,
            retryable=True,
        )
        return
    attempt_id = begin_attempt(
        workspace,
        audit_id=audit_id,
        component="SEMANTIC_AI",
        scope_key=snapshot_id,
        metadata={"provider_state": getattr(state, "value", str(state or ""))},
    )
    if state is ProviderState.AVAILABLE:
        response = getattr(result, "response", None)
        finish_attempt(
            workspace,
            attempt_id,
            status=SUCCESS,
            result_ref=(f"semantic:{getattr(response, 'provider', 'provider')}:{snapshot_id}" if response is not None else f"semantic:{snapshot_id}"),
        )
    else:
        finish_attempt(
            workspace,
            attempt_id,
            status=FAILED_RETRYABLE,
            error_class="AI_PROVIDER",
            error_code=reason or getattr(state, "value", str(state or "UNAVAILABLE")),
            error_message=reason or "semantic provider did not return an available result",
            retryable=True,
        )


def _wrap_m7(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def execute_m7_with_fulfillment(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        m3_result = kwargs.get("m3_result")
        m4_result = kwargs.get("m4_result")
        base_provider = kwargs.get("provider")
        requested = _semantic_requested() or _provider_requested(base_provider)
        if not audit_id or workspace is None or m3_result is None:
            return original(*args, **kwargs)
        if not requested:
            return original(*args, **kwargs)

        merge_contract_configuration(
            workspace,
            audit_id,
            semantic_ai_requested=True,
            semantic_provider=_provider_name(base_provider) if _provider_name(base_provider) != "NONE" else (_INITIAL_OPTIONS.get() or {}).get("semantic_provider"),
        )
        snapshot_ids = [
            str(snapshot_id)
            for per_device in getattr(m3_result, "snapshot_ids", {}).values()
            for snapshot_id in per_device.values()
        ]
        if not snapshot_ids:
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="SEMANTIC_AI",
                scope_key="AUDIT",
                required=True,
                temporal_mode=REPLAY_SAFE,
                status=WAITING_FOR_DATA,
                configuration={"reason": "NO_RENDERED_CONTEXTS"},
            )
            return original(*args, **kwargs)

        for snapshot_id in snapshot_ids:
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="SEMANTIC_AI",
                scope_key=snapshot_id,
                required=True,
                temporal_mode=REPLAY_SAFE,
                configuration={"provider": (_INITIAL_OPTIONS.get() or {}).get("semantic_provider") or _provider_name(base_provider)},
            )
        failures = frozenset(
            str(getattr(item, "snapshot_id", ""))
            for item in (getattr(m4_result, "failures", ()) if m4_result is not None else ())
        )
        gated = _GatedSemanticProvider(base_provider, requested=True, m4_failures=failures)
        patched = dict(kwargs)
        patched["provider"] = gated
        result = original(*args, **patched)
        for snapshot_id in snapshot_ids:
            outcome = gated.outcomes.get(snapshot_id)
            if outcome is None:
                set_work_item_status(
                    workspace,
                    audit_id=audit_id,
                    component="SEMANTIC_AI",
                    scope_key=snapshot_id,
                    status=WAITING_FOR_DATA,
                    error_class="PREREQUISITE",
                    error_code="SEMANTIC_CONTEXT_NOT_EXECUTED",
                    error_message="semantic provider was not eligible/executed for this snapshot",
                )
            else:
                _record_semantic_outcome(
                    workspace=workspace,
                    audit_id=audit_id,
                    snapshot_id=snapshot_id,
                    result=outcome,
                )
        return result

    execute_m7_with_fulfillment._rasai_fulfillment = True
    execute_m7_with_fulfillment._rasai_original = original
    return execute_m7_with_fulfillment


class _GatedContentRouter:
    def __init__(self, base: Any) -> None:
        self.base = base
        self.strategy = getattr(base, "strategy", "UNKNOWN")
        self.providers = getattr(base, "providers", ())

    def analyze(self, request: Any) -> Any:
        from rasai.m20_ai import ContentRemediationResult, ProviderState

        content = str(getattr(request, "main_content", "") or "").strip()
        findings = tuple(getattr(request, "findings", ()) or ())
        evidence = tuple(getattr(request, "evidence", ()) or ())
        known = {str(getattr(item, "evidence_id", "")) for item in evidence}
        complete_links = bool(findings) and all(
            bool(getattr(item, "evidence_ids", ()))
            and set(str(value) for value in getattr(item, "evidence_ids", ())).issubset(known)
            for item in findings
        )
        if not content or not evidence or not complete_links:
            return ContentRemediationResult(
                ProviderState.UNAVAILABLE,
                reason="AI_WAITING_FOR_DATA:CONTENT_EVIDENCE_INSUFFICIENT",
            )
        return self.base.analyze(request)

    def consume_attempts(self):
        method = getattr(self.base, "consume_attempts", None)
        return method() if callable(method) else ()


def _wrap_content_router_factory(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def build(*args: Any, **kwargs: Any):
        return _GatedContentRouter(original(*args, **kwargs))

    build._rasai_fulfillment = True
    build._rasai_original = original
    return build


def _content_run_reason(workspace: Any, audit_id: str) -> str | None:
    connection = sqlite3.connect(workspace.database)
    try:
        row = connection.execute(
            "SELECT reason FROM content_remediation_runs WHERE audit_id=?", (audit_id,)
        ).fetchone()
        return str(row[0]) if row and row[0] else None
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()


def _wrap_m20(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def execute_m20_with_fulfillment(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        enabled = bool(kwargs.get("enabled", False))
        if audit_id and workspace is not None and enabled:
            register_work_item(
                workspace,
                audit_id=audit_id,
                component="CONTENT_REMEDIATION_AI",
                scope_key="AUDIT",
                required=True,
                temporal_mode=REPLAY_SAFE,
                configuration={"enabled": True},
            )
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            if audit_id and workspace is not None and enabled:
                set_work_item_status(
                    workspace,
                    audit_id=audit_id,
                    component="CONTENT_REMEDIATION_AI",
                    status=FAILED_RETRYABLE,
                    error_class="ORCHESTRATION",
                    error_code="CONTENT_REMEDIATION_EXECUTION_FAILURE",
                    error_message=f"content remediation execution failed before terminal result: {type(exc).__name__}",
                    retryable=True,
                )
            raise
        if not audit_id or workspace is None or not enabled:
            return result
        status = str(getattr(result, "status", ""))
        reason = _content_run_reason(workspace, audit_id)
        if status in {"SUCCESS", "NO_SAFE_SUGGESTIONS"}:
            set_work_item_status(
                workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",status=SUCCESS,
                result_ref=f"content-remediation:{status}",
            )
        elif status == "NO_ELIGIBLE_FINDINGS":
            set_work_item_status(
                workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",status=NOT_APPLICABLE,
                result_ref="content-remediation:not-applicable",retryable=False,
            )
        elif (reason or "").startswith("AI_WAITING_FOR_DATA:"):
            set_work_item_status(
                workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",status=WAITING_FOR_DATA,
                error_class="PREREQUISITE",error_code=reason,error_message=reason,
            )
        else:
            attempt_id = begin_attempt(
                workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",
                metadata={"m20_status": status},
            )
            finish_attempt(
                workspace,attempt_id,status=FAILED_RETRYABLE,error_class="AI_PROVIDER",
                error_code=reason or status or "M20_DEGRADED",error_message=reason or status or "content remediation unavailable",
            )
        return result

    execute_m20_with_fulfillment._rasai_fulfillment = True
    execute_m20_with_fulfillment._rasai_original = original
    return execute_m20_with_fulfillment


def _wrap_m24(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def execute_m24_with_fulfillment(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        enabled = bool(kwargs.get("technical_ai", False))
        if audit_id and workspace is not None and enabled:
            register_work_item(
                workspace,audit_id=audit_id,component="TECHNICAL_AI",scope_key="AUDIT",
                required=True,temporal_mode=REPLAY_SAFE,configuration={"enabled": True},
            )
        result = original(*args, **kwargs)
        if audit_id and workspace is not None and enabled:
            state = str(getattr(result, "ai_state", "") or "").upper()
            if state == "AVAILABLE":
                set_work_item_status(
                    workspace,audit_id=audit_id,component="TECHNICAL_AI",status=SUCCESS,
                    result_ref=f"m24-ai:{getattr(result, 'ai_provider', None) or 'provider'}",
                )
            elif state in {"NOT_APPLICABLE", "NO_ELIGIBLE_FINDINGS"}:
                set_work_item_status(
                    workspace,audit_id=audit_id,component="TECHNICAL_AI",status=NOT_APPLICABLE,retryable=False,
                )
            else:
                attempt_id = begin_attempt(workspace,audit_id=audit_id,component="TECHNICAL_AI")
                finish_attempt(
                    workspace,attempt_id,status=FAILED_RETRYABLE,error_class="AI_PROVIDER",
                    error_code=state or "M24_AI_UNAVAILABLE",error_message=f"M24 technical AI state={state or 'UNKNOWN'}",
                )
        return result

    execute_m24_with_fulfillment._rasai_fulfillment = True
    execute_m24_with_fulfillment._rasai_original = original
    return execute_m24_with_fulfillment


def finalize_core_work_item_before_reporting(
    *,
    workspace: Any,
    audit_id: str,
    audited_pages: int,
) -> None:
    """Persist CORE_AUDIT while final derivations are still mutable."""
    config = dict(_INITIAL_OPTIONS.get() or {})
    initialize_contract(workspace, audit_id, config)
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        scope_key="AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=False,
        configuration={"audited_pages": int(audited_pages)},
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{audit_id}",
        retryable=False,
    )


def _wrap_run_audit(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def run_audit_with_fulfillment(target: Any, *args: Any, **kwargs: Any):
        config = _safe_initial_configuration(target, kwargs)
        token = _INITIAL_OPTIONS.set(config)
        try:
            return original(target, *args, **kwargs)
        finally:
            _INITIAL_OPTIONS.reset(token)

    run_audit_with_fulfillment._rasai_fulfillment = True
    run_audit_with_fulfillment._rasai_original = original
    return run_audit_with_fulfillment


def _wrap_m21(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def execute_m21_with_fulfillment(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        config = kwargs.get("config")
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        if not audit_id or workspace is None or not enabled:
            return original(*args, **kwargs)
        cfg = config.validate() if hasattr(config, "validate") else config
        register_work_item(
            workspace,audit_id=audit_id,component="WEB_PERFORMANCE",scope_key="AUDIT",
            required=True,temporal_mode=LIVE_RECOLLECTION,
            configuration={
                "enabled": True,"max_pages": getattr(cfg, "max_pages", 0),
                "timeout_seconds": getattr(cfg, "timeout_seconds", None),
                "categories": list(getattr(cfg, "categories", ()) or ()),
                "field_source": getattr(cfg, "field_source", "auto"),
                "pagespeed_key_configured": bool(getattr(cfg, "pagespeed_api_key", None)),
                "crux_key_configured": bool(getattr(cfg, "crux_api_key", None)),
            },
        )
        attempt_id = begin_attempt(workspace,audit_id=audit_id,component="WEB_PERFORMANCE")
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            finish_attempt(
                workspace,attempt_id,status=FAILED_RETRYABLE,error_class=type(exc).__name__,
                error_code="M21_RUNTIME_FAILURE",error_message=str(exc),
            )
            raise
        status = str(getattr(result, "status", ""))
        if status == "SUCCESS":
            finish_attempt(workspace,attempt_id,status=SUCCESS,result_ref="web-performance:effective")
        elif status == "NO_CONTEXTS":
            finish_attempt(
                workspace,attempt_id,status=WAITING_FOR_DATA,error_class="PREREQUISITE",
                error_code="NO_RENDERED_CONTEXTS",error_message="web performance has no rendered contexts",
            )
        else:
            finish_attempt(
                workspace,attempt_id,status=FAILED_RETRYABLE,error_class="EXTERNAL_SERVICE",
                error_code=status or "M21_UNAVAILABLE",error_message=f"web performance state={status or 'UNKNOWN'}",
            )
        return result

    execute_m21_with_fulfillment._rasai_fulfillment = True
    execute_m21_with_fulfillment._rasai_original = original
    return execute_m21_with_fulfillment


def _m23_effective_success(workspace: Any, audit_id: str, target: int) -> bool:
    connection = sqlite3.connect(workspace.database)
    try:
        run = connection.execute(
            "SELECT contexts_considered FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,)
        ).fetchone()
        if not run or int(run[0]) <= 0:
            return False
        row = connection.execute(
            """SELECT count(*),min(valid_samples) FROM synthetic_apdex_summaries WHERE audit_id=?""",
            (audit_id,),
        ).fetchone()
        return bool(row and int(row[0]) == int(run[0]) and row[1] is not None and int(row[1]) >= int(target))
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


def _wrap_m23(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def execute_m23_with_fulfillment(*args: Any, **kwargs: Any):
        audit_id = str(kwargs.get("audit_id") or "")
        workspace = kwargs.get("workspace")
        config = kwargs.get("config")
        enabled = bool(getattr(config, "enabled", False)) if config is not None else False
        if not audit_id or workspace is None or not enabled:
            return original(*args, **kwargs)
        cfg = config.validate() if hasattr(config, "validate") else config
        target = int(getattr(cfg, "target_valid_samples", 0) or 0)
        register_work_item(
            workspace,audit_id=audit_id,component="SYNTHETIC_APDEX",scope_key="AUDIT",
            required=True,temporal_mode=LIVE_RECOLLECTION,
            configuration={
                "threshold_seconds": getattr(cfg, "threshold_seconds", None),
                "target_valid_samples": target,
                "max_attempts_per_context": getattr(cfg, "max_attempts_per_context", None),
                "max_pages": getattr(cfg, "max_pages", None),
                "timeout_seconds": getattr(cfg, "timeout_seconds", None),
                "delay_seconds": getattr(cfg, "delay_seconds", None),
                "concurrency": getattr(cfg, "concurrency", None),
            },
        )
        attempt_id = begin_attempt(workspace,audit_id=audit_id,component="SYNTHETIC_APDEX")
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            finish_attempt(
                workspace,attempt_id,status=FAILED_RETRYABLE,error_class=type(exc).__name__,
                error_code="M23_RUNTIME_FAILURE",error_message=str(exc),
            )
            raise
        effective = _m23_effective_success(workspace, audit_id, target)
        if effective:
            finish_attempt(workspace,attempt_id,status=SUCCESS,result_ref="synthetic-apdex:effective")
        elif str(getattr(result, "status", "")) == "NO_CONTEXTS":
            finish_attempt(
                workspace,attempt_id,status=WAITING_FOR_DATA,error_class="PREREQUISITE",
                error_code="NO_RENDERED_CONTEXTS",error_message="Synthetic Apdex has no rendered contexts",
            )
        else:
            finish_attempt(
                workspace,attempt_id,status=FAILED_RETRYABLE,error_class="SYNTHETIC_MEASUREMENT",
                error_code=str(getattr(result, "status", "")) or "M23_INCOMPLETE",
                error_message="Synthetic Apdex did not reach the configured valid-sample target for every context",
            )
        return result

    execute_m23_with_fulfillment._rasai_fulfillment = True
    execute_m23_with_fulfillment._rasai_original = original
    return execute_m23_with_fulfillment


def _sync_persisted_components(*, audit_id: str, workspace: Any) -> None:
    initialize_contract(workspace, audit_id)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        if _table_exists(connection, "web_performance_runs"):
            row = connection.execute("SELECT * FROM web_performance_runs WHERE audit_id=?", (audit_id,)).fetchone()
            if row is not None and bool(row["enabled"]):
                register_work_item(
                    workspace,audit_id=audit_id,component="WEB_PERFORMANCE",required=True,
                    temporal_mode=LIVE_RECOLLECTION,configuration={"field_source": row["field_source"], "page_limit": row["page_limit"]},
                )
                if str(row["status"]) == "SUCCESS":
                    set_work_item_status(workspace,audit_id=audit_id,component="WEB_PERFORMANCE",status=SUCCESS,result_ref="web-performance:effective")

        if _table_exists(connection, "synthetic_apdex_runs"):
            row = connection.execute("SELECT * FROM synthetic_apdex_runs WHERE audit_id=?", (audit_id,)).fetchone()
            if row is not None and bool(row["enabled"]):
                target = int(row["target_valid_samples"])
                register_work_item(
                    workspace,audit_id=audit_id,component="SYNTHETIC_APDEX",required=True,
                    temporal_mode=LIVE_RECOLLECTION,configuration={"target_valid_samples": target, "threshold_seconds": row["threshold_seconds"]},
                )
                if _m23_effective_success(workspace, audit_id, target):
                    set_work_item_status(workspace,audit_id=audit_id,component="SYNTHETIC_APDEX",status=SUCCESS,result_ref="synthetic-apdex:effective")

        if _table_exists(connection, "synthetic_ux_apdex_runs"):
            row = connection.execute("SELECT * FROM synthetic_ux_apdex_runs WHERE audit_id=?", (audit_id,)).fetchone()
            if row is not None and bool(row["enabled"]):
                target = int(row["target_samples_per_page"])
                register_work_item(
                    workspace,audit_id=audit_id,component="EXPERIENCE_APDEX",required=True,
                    temporal_mode=LIVE_RECOLLECTION,configuration={
                        "target_samples_per_page": target,"max_attempts_per_page": row["max_attempts_per_page"],
                        "page_limit": row["page_limit"],"session_mode": row["session_mode"],"kpm": row["kpm"],
                    },
                )
                stats = connection.execute(
                    "SELECT count(*),min(valid_samples) FROM synthetic_ux_apdex_summaries WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
                # Experience distributions can create several device summaries per page.
                # A persisted SUCCESS remains the authoritative completeness assertion,
                # while the valid-sample guard prevents a stale/empty run from passing.
                if str(row["status"]) == "SUCCESS" and stats and int(stats[0]) > 0 and stats[1] is not None and int(stats[1]) >= target:
                    set_work_item_status(workspace,audit_id=audit_id,component="EXPERIENCE_APDEX",status=SUCCESS,result_ref="experience-apdex:effective")
                elif str(row["status"]) in {"NO_CONTEXTS", "NO_PAGES"}:
                    set_work_item_status(
                        workspace,audit_id=audit_id,component="EXPERIENCE_APDEX",status=WAITING_FOR_DATA,
                        error_class="PREREQUISITE",error_code=str(row["status"]),error_message="Experience Apdex has no eligible context",
                    )
                else:
                    set_work_item_status(
                        workspace,audit_id=audit_id,component="EXPERIENCE_APDEX",status=FAILED_RETRYABLE,
                        error_class="SYNTHETIC_MEASUREMENT",error_code=str(row["status"]),
                        error_message="Experience Apdex did not reach its configured effective success state",
                    )

        if _table_exists(connection, "m24_runs"):
            row = connection.execute("SELECT * FROM m24_runs WHERE audit_id=?", (audit_id,)).fetchone()
            if row is not None and bool(row["ai_enabled"]):
                register_work_item(workspace,audit_id=audit_id,component="TECHNICAL_AI",required=True,temporal_mode=REPLAY_SAFE)
                if str(row["ai_state"]).upper() == "AVAILABLE":
                    set_work_item_status(workspace,audit_id=audit_id,component="TECHNICAL_AI",status=SUCCESS,result_ref="m24-ai:effective")

        if _table_exists(connection, "content_remediation_runs"):
            row = connection.execute("SELECT * FROM content_remediation_runs WHERE audit_id=?", (audit_id,)).fetchone()
            if row is not None and bool(row["enabled"]):
                register_work_item(workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",required=True,temporal_mode=REPLAY_SAFE)
                status = str(row["status"])
                if status in {"SUCCESS", "NO_SAFE_SUGGESTIONS"}:
                    set_work_item_status(workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",status=SUCCESS,result_ref=f"content-remediation:{status}")
                elif status == "NO_ELIGIBLE_FINDINGS":
                    set_work_item_status(workspace,audit_id=audit_id,component="CONTENT_REMEDIATION_AI",status=NOT_APPLICABLE,retryable=False)
    finally:
        connection.close()


def _wrap_finalizer(original):
    if getattr(original, "_rasai_fulfillment", False):
        return original

    def finalize_with_fulfillment(*args: Any, **kwargs: Any):
        # Durable fulfillment is owned by the pre-report final-derivation boundary.
        return original(*args, **kwargs)

    finalize_with_fulfillment._rasai_fulfillment = True
    finalize_with_fulfillment._rasai_original = original
    return finalize_with_fulfillment


def _install_consolidation_gate() -> None:
    from rasai.consolidation.index import ConsolidationIndex

    original = ConsolidationIndex.candidate_audits
    if getattr(original, "_rasai_fulfillment", False):
        return

    def candidate_audits_final_only(self: Any, filters: Any):
        rows = original(self, filters)
        accepted = []
        for row in rows:
            db_path = self.audits_root / str(row["db_path"])
            if consolidation_eligible(db_path, str(row["audit_id"])):
                accepted.append(row)
        return tuple(accepted)

    candidate_audits_final_only._rasai_fulfillment = True
    candidate_audits_final_only._rasai_original = original
    ConsolidationIndex.candidate_audits = candidate_audits_final_only


def _install_platform_status_projection() -> None:
    try:
        from rasai.platform import indexing
    except ImportError:
        return
    original = indexing.read_audit_snapshot
    if getattr(original, "_rasai_fulfillment", False):
        return

    def read_snapshot_with_fulfillment(workspace: Any):
        snapshot = original(workspace)
        summary = read_summary(workspace, getattr(snapshot, "audit_id", None))
        if summary is None or summary.consolidation_eligible:
            return snapshot
        try:
            return replace(
                snapshot,
                status=summary.processing_status,
                completion_status=summary.report_status,
            )
        except TypeError:
            return snapshot

    read_snapshot_with_fulfillment._rasai_fulfillment = True
    read_snapshot_with_fulfillment._rasai_original = original
    indexing.read_audit_snapshot = read_snapshot_with_fulfillment


def install() -> None:
    """Install fulfillment gates once for initial local/SaaS execution."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import audit_runner, cli, cli_extensions, m20, m21_web_performance, m23_apdex, m24_crawling_discovery, report_completion

    wrapped_run = _wrap_run_audit(audit_runner.run_audit)
    audit_runner.run_audit = wrapped_run
    cli.run_audit = wrapped_run

    audit_runner.execute_m7 = _wrap_m7(audit_runner.execute_m7)
    audit_runner.execute_m20 = _wrap_m20(audit_runner.execute_m20)
    audit_runner.execute_m24 = _wrap_m24(audit_runner.execute_m24)

    wrapped_m21 = _wrap_m21(m21_web_performance.execute_m21)
    m21_web_performance.execute_m21 = wrapped_m21
    cli.execute_m21 = wrapped_m21

    wrapped_m23 = _wrap_m23(m23_apdex.execute_m23_apdex)
    m23_apdex.execute_m23_apdex = wrapped_m23
    cli_extensions.execute_m23_apdex = wrapped_m23

    wrapped_m24 = _wrap_m24(m24_crawling_discovery.execute_m24)
    m24_crawling_discovery.execute_m24 = wrapped_m24
    cli_extensions.execute_m24 = wrapped_m24

    wrapped_router = _wrap_content_router_factory(cli_extensions.build_content_remediation_router)
    cli_extensions.build_content_remediation_router = wrapped_router
    m20.build_content_remediation_router = wrapped_router

    report_completion.finalize_audit_report_site = _wrap_finalizer(report_completion.finalize_audit_report_site)
    _install_consolidation_gate()
    _install_platform_status_projection()
    _INSTALLED = True
