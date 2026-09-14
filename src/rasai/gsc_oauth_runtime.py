"""Compose durable Google Search Console OAuth into current RASAi surfaces.

This layer adds refresh-token credentials without changing the Search Console collectors.
The collectors still receive a normal Bearer access token; when refresh credentials are
configured that token is obtained in memory immediately before use. Public readiness,
scope checks and integration diagnostics understand both credential modes.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import os
from typing import Any, Mapping

from rasai.gsc_oauth import (
    ACCESS_TOKEN_ENV,
    CATEGORY_AUTHENTICATION,
    CATEGORY_CONFIGURATION,
    CATEGORY_TRANSIENT,
    CLIENT_ID_ENV,
    CLIENT_SECRET_ENV,
    MODE_INCOMPLETE,
    MODE_INVALID,
    MODE_MISSING,
    REFRESH_TOKEN_ENV,
    SITE_URL_ENV,
    GscOAuthError,
    auth_configured,
    credential_state,
    environment_with_access_token,
)

_INSTALLED = False


def _gsc_service_state(original, item: Any, env: Mapping[str, str] | None = None) -> dict[str, object]:
    environment = os.environ if env is None else env
    if str(getattr(item, "id", "")) != "google-search-console":
        return original(item, environment)

    # Reuse the registry's existing enabled/auto-enable semantics by giving only its
    # private evaluation copy a synthetic token marker. No generated token or secret is
    # persisted and no network request occurs during configuration/readiness checks.
    effective = {str(key): str(value) for key, value in environment.items()}
    state = credential_state(environment)
    if state.configured:
        effective[ACCESS_TOKEN_ENV] = "__RASAI_GSC_OAUTH_CONFIGURED__"
    info = dict(original(item, effective))
    if not state.configured:
        missing = list(info.get("missing_credentials") or ())
        if state.mode in {MODE_INCOMPLETE, MODE_MISSING}:
            missing = list(state.missing)
        elif state.mode == MODE_INVALID:
            missing = [ACCESS_TOKEN_ENV]
        info["configured"] = False
        info["effective_enabled"] = False
        info["missing_credentials"] = tuple(dict.fromkeys(missing))
        if bool(info.get("requested")):
            info["state"] = "NOT_CONFIGURED"
    info["oauth_mode"] = state.mode
    return info


def _install_service_state() -> None:
    from rasai import standards_service_registry as registry

    original = registry.service_state
    if bool(getattr(original, "_rasai_gsc_oauth", False)):
        return

    def service_state(item: Any, env: Mapping[str, str] | None = None) -> dict[str, object]:
        return _gsc_service_state(original, item, env)

    service_state._rasai_gsc_oauth = True  # type: ignore[attr-defined]
    service_state._rasai_original = original  # type: ignore[attr-defined]
    registry.service_state = service_state

    # Modules that imported service_state by value before this installer was composed.
    for module_name in (
        "rasai.standards_gsc_observability_runtime",
        "rasai.gsc_scope_runtime",
        "rasai.fulfillment_execution_contract",
        "rasai.web.standards_routes",
    ):
        module = __import__(module_name, fromlist=["service_state"])
        if hasattr(module, "service_state"):
            setattr(module, "service_state", service_state)


def _install_scope_readiness() -> None:
    from rasai import gsc_scope

    original = gsc_scope.assess_gsc_target
    if bool(getattr(original, "_rasai_gsc_oauth", False)):
        return

    def assess_gsc_target(target_url: str, environment: Mapping[str, str], *, mode_override: str | None = None):
        effective = {str(key): str(value) for key, value in environment.items()}
        if auth_configured(environment):
            effective[ACCESS_TOKEN_ENV] = "__RASAI_GSC_OAUTH_CONFIGURED__"
        return original(target_url, effective, mode_override=mode_override)

    assess_gsc_target._rasai_gsc_oauth = True  # type: ignore[attr-defined]
    assess_gsc_target._rasai_original = original  # type: ignore[attr-defined]
    gsc_scope.assess_gsc_target = assess_gsc_target
    try:
        from rasai import gsc_scope_runtime
        gsc_scope_runtime.assess_gsc_target = assess_gsc_target
    except ImportError:
        pass


def _oauth_failure_result(state_info: Mapping[str, Any], exc: GscOAuthError) -> dict[str, Any]:
    category = str(exc.category)
    return {
        "service_state": "ERROR",
        "requested": bool(state_info.get("requested")),
        "configured": bool(state_info.get("configured")),
        "effective_enabled": bool(state_info.get("effective_enabled")),
        "configuration_source": str(state_info.get("configuration_source") or ""),
        "operations": [{
            "name": "OAUTH_TOKEN_REFRESH",
            "status": "ERROR",
            "error_category": category,
            "error_code": exc.code,
            "http_status": exc.http_status,
        }],
        "errors": [f"OAUTH_TOKEN_REFRESH:{category}:{exc.code}:{str(exc)[:300]}"],
        "targets_attempted": 1,
        "targets_succeeded": 0,
        "requested_url_inspections": 0,
        "collection_state": "ERROR",
    }


def _install_collection_refresh() -> None:
    from rasai import standards_gsc_observability_runtime as runtime
    from rasai.standards_service_registry import service, service_state

    original = runtime.collect_configured_search_console
    if bool(getattr(original, "_rasai_gsc_oauth", False)):
        return

    def collect_configured_search_console(
        *,
        audit_id: str,
        workspace: Any,
        env: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        environment = os.environ if env is None else env
        info = service_state(service("google-search-console"), environment)
        if not bool(info.get("effective_enabled")):
            return original(audit_id=audit_id, workspace=workspace, env=environment)
        try:
            effective = environment_with_access_token(environment)
        except GscOAuthError as exc:
            return _oauth_failure_result(info, exc)
        return original(audit_id=audit_id, workspace=workspace, env=effective)

    collect_configured_search_console._rasai_gsc_oauth = True  # type: ignore[attr-defined]
    collect_configured_search_console._rasai_original = original  # type: ignore[attr-defined]
    runtime.collect_configured_search_console = collect_configured_search_console


def _diagnostic_from_oauth_error(diagnostics: Any, spec: Any, env: Mapping[str, str], exc: GscOAuthError):
    if exc.category == CATEGORY_AUTHENTICATION:
        status = diagnostics.STATUS_AUTHENTICATION_ERROR
        category = "AUTHENTICATION"
        action = "Revise Client ID, Client Secret e Refresh Token; gere uma nova autorização OAuth se o grant foi revogado."
    elif exc.category == CATEGORY_TRANSIENT:
        status = diagnostics.STATUS_TRANSIENT_FAILURE
        category = "OAUTH_TRANSIENT"
        action = "Reteste posteriormente; se persistir, verifique rede/proxy e disponibilidade do endpoint OAuth do Google."
    else:
        status = diagnostics.STATUS_CONFIGURATION_ERROR
        category = "OAUTH_CONFIGURATION"
        action = "Complete/corrija a configuração OAuth do Search Console e execute o teste novamente."
    return diagnostics.IntegrationDiagnostic(
        spec.id,
        spec.label,
        datetime.now(timezone.utc).isoformat(),
        status,
        category,
        str(exc),
        action,
        diagnostics.configuration_fingerprint(spec, env),
        None,
        exc.http_status,
        spec.probe_cost,
        ("configuration", "oauth") if status != diagnostics.STATUS_TRANSIENT_FAILURE else ("configuration", "connectivity"),
    )


def _install_integration_diagnostics() -> None:
    from rasai import integration_diagnostics as diagnostics

    original_specs = diagnostics.integration_specs
    if not bool(getattr(original_specs, "_rasai_gsc_oauth", False)):
        def integration_specs():
            output = []
            for spec in original_specs():
                if spec.id != "service:google-search-console":
                    output.append(spec)
                    continue
                dependencies = (
                    diagnostics.IntegrationDependency(
                        ACCESS_TOKEN_ENV, False, True,
                        "OAuth access token manual; opcional quando Client ID + Client Secret + Refresh Token estão configurados",
                    ),
                    diagnostics.IntegrationDependency(
                        CLIENT_ID_ENV, False, False,
                        "OAuth Client ID usado para renovar o access token automaticamente",
                    ),
                    diagnostics.IntegrationDependency(
                        CLIENT_SECRET_ENV, False, True,
                        "OAuth Client Secret usado somente na renovação em memória",
                    ),
                    diagnostics.IntegrationDependency(
                        REFRESH_TOKEN_ENV, False, True,
                        "OAuth Refresh Token usado para renovar o access token automaticamente",
                    ),
                    diagnostics.IntegrationDependency(
                        SITE_URL_ENV, True, False,
                        "property sc-domain ou URL-prefix cadastrada no Search Console",
                    ),
                )
                output.append(replace(spec, dependencies=dependencies))
            return tuple(output)

        integration_specs._rasai_gsc_oauth = True  # type: ignore[attr-defined]
        integration_specs._rasai_original = original_specs  # type: ignore[attr-defined]
        diagnostics.integration_specs = integration_specs

    original_local = diagnostics._local_validation
    if not bool(getattr(original_local, "_rasai_gsc_oauth", False)):
        def local_validation(spec: Any, env: Mapping[str, str]):
            if spec.probe_kind == "GSC":
                # SITE_URL remains a normal required dependency; authentication is an
                # OR contract evaluated here instead of pretending all OAuth fields are mandatory.
                site = str(env.get(SITE_URL_ENV) or "").strip()
                if not site:
                    return diagnostics.IntegrationDiagnostic(
                        spec.id, spec.label, datetime.now(timezone.utc).isoformat(),
                        diagnostics.STATUS_NOT_CONFIGURED, "DEPENDENCY",
                        f"Dependência obrigatória ausente: {SITE_URL_ENV}.",
                        "Configure a property do Search Console e execute o teste novamente.",
                        diagnostics.configuration_fingerprint(spec, env), None, None, spec.probe_cost, ("configuration",),
                    )
                state = credential_state(env)
                if not state.configured:
                    status = diagnostics.STATUS_CONFIGURATION_ERROR if state.mode in {MODE_INCOMPLETE, MODE_INVALID} else diagnostics.STATUS_NOT_CONFIGURED
                    return diagnostics.IntegrationDiagnostic(
                        spec.id, spec.label, datetime.now(timezone.utc).isoformat(), status, "OAUTH_CONFIGURATION",
                        state.detail or "OAuth do Search Console não configurado.",
                        "Informe um OAuth access token ou configure Client ID + Client Secret + Refresh Token.",
                        diagnostics.configuration_fingerprint(spec, env), None, None, spec.probe_cost, ("configuration",),
                    )
            return original_local(spec, env)

        local_validation._rasai_gsc_oauth = True  # type: ignore[attr-defined]
        local_validation._rasai_original = original_local  # type: ignore[attr-defined]
        diagnostics._local_validation = local_validation

    original_probe = diagnostics._probe_gsc
    if not bool(getattr(original_probe, "_rasai_gsc_oauth", False)):
        def probe_gsc(spec: Any, env: Mapping[str, str], *, timeout: float, opener: Any):
            try:
                effective = environment_with_access_token(env, timeout=timeout, opener=opener)
            except GscOAuthError as exc:
                return _diagnostic_from_oauth_error(diagnostics, spec, env, exc)
            return original_probe(spec, effective, timeout=timeout, opener=opener)

        probe_gsc._rasai_gsc_oauth = True  # type: ignore[attr-defined]
        probe_gsc._rasai_original = original_probe  # type: ignore[attr-defined]
        diagnostics._probe_gsc = probe_gsc


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_service_state()
    _install_scope_readiness()
    _install_collection_refresh()
    _install_integration_diagnostics()
    _INSTALLED = True
