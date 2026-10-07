"""Causal diagnostics for governed AI during selective RPR.

This adapter does not own provider routing or CAT-08 execution. It preserves causal
states around the registered-AI boundary so pre-provider failures cannot be rewritten
as synthetic execution failures.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    NOT_CONFIGURED,
    REQUESTED_NOT_EXECUTED,
    SUCCESS,
    list_work_items,
    set_work_item_status,
)
from rasai.operational_log import try_append_operational_event
from rasai.secret_safety import redact_text

_INSTALLED = False
_GENERIC_NOT_MATERIALIZED = "IMPROVEMENT_RETRY_NOT_MATERIALIZED"
_MISSING_HOOK = "AI_HOOK_NOT_REGISTERED"
_PRESERVABLE_STATUSES = frozenset(
    {"FAILED_RETRYABLE", "NOT_CONFIGURED", "REQUESTED_NOT_EXECUTED"}
)


def _specific_failure(item: Any | None) -> dict[str, Any] | None:
    if item is None:
        return None
    status = str(getattr(item, "status", "") or "").upper()
    code = str(getattr(item, "last_error_code", "") or "").strip()
    error_class = str(getattr(item, "last_error_class", "") or "").strip()
    message = str(getattr(item, "last_error_message", "") or "").strip()
    if (
        status not in _PRESERVABLE_STATUSES
        or not code
        or code == _GENERIC_NOT_MATERIALIZED
        or not (error_class or message)
    ):
        return None
    return {
        "status": status,
        "error_class": error_class or None,
        "error_code": code,
        "error_message": message or None,
        "retryable": bool(getattr(item, "retryable", True)),
    }


def _purpose_work_item(workspace: Any, audit_id: str, purpose: str) -> Any | None:
    wanted = str(purpose or "").strip().upper()
    return next(
        (
            item
            for item in list_work_items(workspace, audit_id)
            if str(getattr(item, "component", "") or "").upper() == wanted
            and str(getattr(item, "scope_key", "AUDIT") or "AUDIT") == "AUDIT"
        ),
        None,
    )


def _project_missing_hook(workspace: Any, audit_id: str, purpose: str) -> None:
    item = _purpose_work_item(workspace, audit_id, purpose)
    if item is not None and str(getattr(item, "status", "") or "").upper() != SUCCESS:
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component=str(getattr(item, "component", purpose)),
            scope_key=str(getattr(item, "scope_key", "AUDIT") or "AUDIT"),
            status=REQUESTED_NOT_EXECUTED,
            error_class="ORCHESTRATION",
            error_code=_MISSING_HOOK,
            error_message=(
                f"Purpose de IA {str(purpose).upper()} foi autorizado, mas nenhum "
                "hook executável está registrado neste processo"
            ),
            retryable=True,
        )
    try_append_operational_event(
        workspace,
        "AI_PURPOSE_HOOK_MISSING",
        level="WARNING",
        audit_id=audit_id,
        purpose=str(purpose).upper(),
        provider_called=False,
    )


def _install_registered_ai_dispatch_guard() -> None:
    from rasai import audit_phase_runtime as phase

    original = phase.run_registered_ai_phase
    if bool(getattr(original, "_rasai_missing_ai_hook_guard", False)):
        return

    def run(
        *,
        audit_id: str,
        workspace: Any,
        evidence_snapshot: Any,
        purposes: Iterable[str] | None = None,
    ) -> dict[str, Mapping[str, Any]]:
        if purposes is None:
            return dict(
                original(
                    audit_id=audit_id,
                    workspace=workspace,
                    evidence_snapshot=evidence_snapshot,
                    purposes=None,
                )
            )
        requested = {
            str(value).strip().upper()
            for value in purposes
            if str(value).strip()
        }
        registered = requested.intersection(phase._AI_HOOKS)
        missing = requested.difference(phase._AI_HOOKS)
        outcomes = dict(
            original(
                audit_id=audit_id,
                workspace=workspace,
                evidence_snapshot=evidence_snapshot,
                purposes=registered,
            )
        )
        for purpose in sorted(missing):
            _project_missing_hook(workspace, audit_id, purpose)
            outcomes[purpose] = {
                "status": "SKIPPED",
                "reason": _MISSING_HOOK,
                "provider_called": False,
            }
        return outcomes

    run._rasai_missing_ai_hook_guard = True
    run._rasai_original = original
    phase.run_registered_ai_phase = run

    # These modules import the dispatcher by value, so rebind their canonical
    # references after the final runtime composition is installed.
    try:
        from rasai import governed_reprocess_runtime as governed
        governed.run_registered_ai_phase = run
    except ImportError:
        pass
    try:
        from rasai import audit_runner
        audit_runner.run_registered_ai_phase = run
    except ImportError:
        pass


def _improvement_configuration_error(
    workspace: Any,
    audit_id: str,
) -> str | None:
    """Validate the exact frozen/settings + execution-local CAT-08 configuration."""
    try:
        from rasai import final_smoke_closure as closure
        from rasai import improvement_intelligence as improvement
        from rasai import improvement_intelligence_runtime as runtime
        from rasai import post_smoke_alignment as alignment
        from rasai.execution_environment import resolve_environment

        environment = dict(resolve_environment())
        if alignment._cat08_required(workspace, audit_id):
            feature = closure._saved_improvement_feature(workspace, audit_id)
            environment[improvement.ENABLED_ENV] = "true"
            mapping = {
                improvement.DOMAINS_ENV: feature.get("domains"),
                improvement.MAX_RECOMMENDATIONS_ENV: feature.get("max_recommendations"),
                improvement.TIMEOUT_ENV: feature.get("timeout_seconds"),
            }
            for name, value in mapping.items():
                if value not in (None, ""):
                    environment[name] = str(value)
        config = runtime.ImprovementConfig.from_environment(environment)
        runtime._apply_reprocess_ai_policy(config)
        return None
    except Exception as exc:
        return redact_text(str(exc))[:1000] or type(exc).__name__


def _install_governed_hook_guard() -> None:
    from rasai import audit_phase_runtime as phase

    hook = phase._AI_HOOKS.get("IMPROVEMENT_INTELLIGENCE")
    if hook is None:
        return
    current = hook.callback
    if bool(getattr(current, "_rasai_improvement_exception_guard", False)):
        return

    def guarded(*, audit_id: str, workspace: Any, evidence_snapshot: Any):
        configuration_error = _improvement_configuration_error(workspace, audit_id)
        if configuration_error:
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=NOT_CONFIGURED,
                error_class="CONFIGURATION",
                error_code="IMPROVEMENT_CONFIGURATION_INVALID",
                error_message=configuration_error,
                retryable=True,
            )
            try_append_operational_event(
                workspace,
                "IMPROVEMENT_INTELLIGENCE_CONFIGURATION_INVALID",
                level="WARNING",
                audit_id=audit_id,
                error_message=configuration_error[:512],
                provider_called=False,
                scoring_impact="NONE",
            )
            return {
                "status": "NOT_CONFIGURED",
                "reason": "IMPROVEMENT_CONFIGURATION_INVALID",
                "provider_called": False,
            }

        try:
            result = dict(
                current(
                    audit_id=audit_id,
                    workspace=workspace,
                    evidence_snapshot=evidence_snapshot,
                )
                or {}
            )
        except Exception as exc:
            code = f"IMPROVEMENT_GOVERNED_HOOK_{type(exc).__name__.upper()}"
            safe_message = redact_text(str(exc))[:1000]
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=FAILED_RETRYABLE,
                error_class="ORCHESTRATION",
                error_code=code,
                error_message=safe_message,
                retryable=True,
            )
            try_append_operational_event(
                workspace,
                "IMPROVEMENT_INTELLIGENCE_FAILURE",
                level="WARNING",
                audit_id=audit_id,
                stage="GOVERNED_HOOK",
                error_type=type(exc).__name__,
                error_message=safe_message[:512],
                scoring_impact="NONE",
            )
            return {
                "status": "ERROR",
                "reason": code,
            }

        status = str(result.get("status") or "").upper()
        reason = str(result.get("reason") or "").upper()
        if status == "SKIPPED" and reason == "CONFIGURATION_INVALID":
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=NOT_CONFIGURED,
                error_class="CONFIGURATION",
                error_code="IMPROVEMENT_CONFIGURATION_INVALID",
                error_message=(
                    "A configuração efetiva da análise profunda é inválida; "
                    "nenhum provider foi chamado"
                ),
                retryable=True,
            )
            result["status"] = "NOT_CONFIGURED"
            result["reason"] = "IMPROVEMENT_CONFIGURATION_INVALID"
            result["provider_called"] = False
        elif status == "SKIPPED" and reason == "DISABLED":
            item = _purpose_work_item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
            if item is not None and bool(getattr(item, "required", False)):
                set_work_item_status(
                    workspace,
                    audit_id=audit_id,
                    component="IMPROVEMENT_INTELLIGENCE",
                    status=REQUESTED_NOT_EXECUTED,
                    error_class="EXECUTION_POLICY",
                    error_code="IMPROVEMENT_REQUIRED_BUT_DISABLED",
                    error_message=(
                        "A análise profunda é obrigatória para esta AUD/RPR, mas o "
                        "runtime efetivo chegou ao hook com a capacidade desabilitada"
                    ),
                    retryable=True,
                )
                result["reason"] = "IMPROVEMENT_REQUIRED_BUT_DISABLED"
                result["provider_called"] = False
        return result

    guarded._rasai_improvement_exception_guard = True
    guarded._rasai_original = current
    phase.register_ai_hook("IMPROVEMENT_INTELLIGENCE", guarded, order=hook.order)


def _install_optional_attempt_guard() -> None:
    from rasai import selective_optional_reprocess as optional

    original = optional._record_optional_attempts
    if bool(getattr(original, "_rasai_nonexecution_attempt_guard", False)):
        return

    def record(workspace: Any, audit_id: str, components: set[str]) -> None:
        executable: set[str] = set()
        for component in components:
            item = optional._item(workspace, audit_id, component)
            if (
                item is not None
                and str(getattr(item, "status", "") or "").upper()
                == REQUESTED_NOT_EXECUTED
            ):
                continue
            executable.add(component)
        original(workspace, audit_id, executable)

    record._rasai_nonexecution_attempt_guard = True
    record._rasai_original = original
    optional._record_optional_attempts = record


def _install_reconciliation_guard() -> None:
    from rasai import selective_optional_reprocess as optional

    original = optional._reconcile_improvement_rpr
    if bool(getattr(original, "_rasai_improvement_causal_guard", False)):
        return

    def reconcile(workspace: Any, audit_id: str) -> None:
        before = _specific_failure(
            optional._item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
        )
        original(workspace, audit_id)
        if before is None:
            return
        if optional._improvement_run(workspace, audit_id) is not None:
            return
        after = optional._item(workspace, audit_id, "IMPROVEMENT_INTELLIGENCE")
        if str(getattr(after, "last_error_code", "") or "") != _GENERIC_NOT_MATERIALIZED:
            return
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=str(before["status"]),
            error_class=before["error_class"],
            error_code=str(before["error_code"]),
            error_message=before["error_message"],
            retryable=bool(before["retryable"]),
        )
        try_append_operational_event(
            workspace,
            "IMPROVEMENT_INTELLIGENCE_CAUSE_PRESERVED",
            level="INFO",
            audit_id=audit_id,
            error_class=before["error_class"],
            error_code=before["error_code"],
            provider_attempt_synthesized=False,
        )

    reconcile._rasai_improvement_causal_guard = True
    reconcile._rasai_original = original
    optional._reconcile_improvement_rpr = reconcile


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_reconciliation_guard()
    _install_registered_ai_dispatch_guard()
    _install_governed_hook_guard()
    _install_optional_attempt_guard()
    _INSTALLED = True


__all__ = ["install"]
