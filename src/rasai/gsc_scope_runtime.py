"""Runtime gate for Google Search Console property/audit scope compatibility.

The normal GSC collector remains authoritative for OAuth/provider errors. This wrapper
only prevents a structurally impossible property/target combination from reaching the
Google APIs. Explicit GSC remains a required fulfillment item and therefore produces a
configuration failure; credential-driven auto mode becomes NOT_APPLICABLE instead of a
spurious external-service failure.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from rasai.gsc_scope import (
    GSC_SITE_URL_ENV,
    MODE_AUTO,
    MODE_REQUIRED,
    STATE_PROPERTY_URL_MISMATCH,
    assess_gsc_target,
    gsc_request_mode,
)

_INSTALLED = False


def _audit_urls(workspace: Any, audit_id: str) -> tuple[str, ...]:
    database = getattr(workspace, "database", None)
    if database is None:
        return ()
    connection = sqlite3.connect(database)
    try:
        rows = connection.execute(
            "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()
    return tuple(str(row[0]).strip() for row in rows if row and str(row[0]).strip())


def _scope_mismatch_result(
    *,
    state_info: Mapping[str, Any],
    site_url: str,
    urls: tuple[str, ...],
    mode: str,
    mismatched: tuple[str, ...],
) -> dict[str, Any]:
    required = mode == MODE_REQUIRED
    target_sample = mismatched[0] if mismatched else (urls[0] if urls else "")
    reason = (
        f"A propriedade Google Search Console {site_url!r} não cobre a URL auditada {target_sample!r}. "
        + (
            "GSC foi solicitado como obrigatório; o AUD permanecerá parcial/não final até a configuração ser corrigida."
            if required
            else "GSC está em modo automático/compatível e será ignorado nesta execução sem bloquear a conclusão do AUD."
        )
    )
    collection_state = STATE_PROPERTY_URL_MISMATCH if required else "NOT_APPLICABLE"
    return {
        "service_state": collection_state,
        "requested": bool(state_info.get("requested")),
        "configured": bool(state_info.get("configured")),
        "effective_enabled": required,
        "configuration_source": str(state_info.get("configuration_source") or ""),
        "operations": [
            {
                "name": "SCOPE_VALIDATION",
                "status": "ERROR" if required else "NOT_APPLICABLE",
                "property": site_url,
                "audited_urls": len(urls),
                "mismatched_urls": len(mismatched),
            }
        ],
        "errors": [reason] if required else [],
        "targets_attempted": 0,
        "targets_succeeded": 0,
        "requested_url_inspections": len(urls),
        "collection_state": collection_state,
        "reason": reason,
        "scope_validation": {
            "state": STATE_PROPERTY_URL_MISMATCH,
            "property": site_url,
            "audited_urls": list(urls),
            "mismatched_urls": list(mismatched),
            "required": required,
        },
    }


def _scope_mismatch_reason(run: Mapping[str, Any]) -> str:
    reason = "Google Search Console obrigatório: propriedade configurada não cobre a URL auditada"
    try:
        details = json.loads(str(run.get("details_json") or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        details = {}
    if isinstance(details, dict) and str(details.get("reason") or "").strip():
        return str(details["reason"]).strip()[:1000]
    return reason


def _set_scope_mismatch_fulfillment(
    *,
    workspace: Any,
    audit_id: str,
    contract: Any,
    run: Mapping[str, Any],
) -> None:
    contract.set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="GOOGLE_SEARCH_CONSOLE",
        status=contract.NOT_CONFIGURED,
        error_class="CONFIGURATION",
        error_code=STATE_PROPERTY_URL_MISMATCH,
        error_message=_scope_mismatch_reason(run),
        retryable=True,
    )


def _install_selective_reprocess_detail() -> None:
    """Keep PROPERTY_URL_MISMATCH a configuration diagnosis during RPR too."""
    try:
        from rasai import fulfillment_execution_contract as contract
        from rasai import selective_optional_reprocess as selective
    except ImportError:
        return
    original = getattr(selective, "_reconcile_gsc_rpr", None)
    if not callable(original) or bool(getattr(original, "_rasai_gsc_scope_detail", False)):
        return

    def reconcile_gsc_rpr_with_scope_detail(workspace: Any, audit_id: str) -> None:
        original(workspace, audit_id)
        try:
            run = selective._gsc_service_run(workspace, audit_id)
        except Exception:
            return
        if not run or str(run.get("state") or "").upper() != STATE_PROPERTY_URL_MISMATCH:
            return
        _set_scope_mismatch_fulfillment(
            workspace=workspace,
            audit_id=audit_id,
            contract=contract,
            run=run,
        )

    reconcile_gsc_rpr_with_scope_detail._rasai_gsc_scope_detail = True  # type: ignore[attr-defined]
    reconcile_gsc_rpr_with_scope_detail._rasai_original = original  # type: ignore[attr-defined]
    selective._reconcile_gsc_rpr = reconcile_gsc_rpr_with_scope_detail


def _install_fulfillment_detail() -> None:
    """Project property mismatch as a configuration diagnosis in report fulfillment."""
    try:
        from rasai import fulfillment_execution_contract as contract
    except ImportError:
        return
    original = getattr(contract, "_reconcile_explicit_services", None)
    if callable(original) and not bool(getattr(original, "_rasai_gsc_scope_detail", False)):
        def reconcile_with_scope_detail(workspace: Any, audit_id: str) -> None:
            original(workspace, audit_id)
            try:
                run = contract._service_run(workspace, audit_id, "google-search-console")
            except Exception:
                return
            if not run or str(run.get("state") or "").upper() != STATE_PROPERTY_URL_MISMATCH:
                return
            _set_scope_mismatch_fulfillment(
                workspace=workspace,
                audit_id=audit_id,
                contract=contract,
                run=run,
            )

        reconcile_with_scope_detail._rasai_gsc_scope_detail = True  # type: ignore[attr-defined]
        reconcile_with_scope_detail._rasai_original = original  # type: ignore[attr-defined]
        contract._reconcile_explicit_services = reconcile_with_scope_detail
    _install_selective_reprocess_detail()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        _install_fulfillment_detail()
        return

    from rasai import standards_gsc_observability_runtime as runtime

    original = runtime.collect_configured_search_console
    if bool(getattr(original, "_rasai_gsc_scope_gate", False)):
        _INSTALLED = True
        _install_fulfillment_detail()
        return

    def collect_with_scope_gate(
        *,
        audit_id: str,
        workspace: Any,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        environment = env if env is not None else runtime.os.environ
        state_info = runtime.service_state(runtime.service("google-search-console"), environment)
        if not bool(state_info.get("effective_enabled")):
            return original(audit_id=audit_id, workspace=workspace, env=env)

        mode = gsc_request_mode(environment)
        if mode not in {MODE_AUTO, MODE_REQUIRED}:
            return original(audit_id=audit_id, workspace=workspace, env=env)

        site_url = str(environment.get(GSC_SITE_URL_ENV) or "").strip()
        urls = _audit_urls(workspace, audit_id)
        if not site_url or not urls:
            return original(audit_id=audit_id, workspace=workspace, env=env)

        mismatched: list[str] = []
        for url in urls:
            assessment = assess_gsc_target(url, environment, mode_override=mode)
            if assessment.state == STATE_PROPERTY_URL_MISMATCH:
                mismatched.append(url)
            elif assessment.blocking:
                # Keep canonical collector/error handling authoritative for malformed
                # configuration that is not specifically a property/target mismatch.
                return original(audit_id=audit_id, workspace=workspace, env=env)
        if not mismatched:
            return original(audit_id=audit_id, workspace=workspace, env=env)

        return _scope_mismatch_result(
            state_info=state_info,
            site_url=site_url,
            urls=urls,
            mode=mode,
            mismatched=tuple(mismatched),
        )

    collect_with_scope_gate._rasai_gsc_scope_gate = True  # type: ignore[attr-defined]
    collect_with_scope_gate._rasai_original = original  # type: ignore[attr-defined]
    runtime.collect_configured_search_console = collect_with_scope_gate
    _INSTALLED = True
    _install_fulfillment_detail()
