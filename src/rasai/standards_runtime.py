"""Runtime composition for standards services and derived metrics.

The module keeps the implementation additive: public audit payloads remain secret-free,
console INI persists only non-secret toggles, and score contracts are not modified.
"""
from __future__ import annotations

from dataclasses import replace
import os
import sys
from typing import Any, Mapping

from rasai.standards_service_registry import (
    CRUX_ENABLED_ENV,
    DEFAULT_STANDARDS_MAX_URLS,
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    DERIVED_READINESS_METRICS_ENV,
    GSC_ENABLED_ENV,
    MDN_OBSERVATORY_ENV,
    OPEN_WEB_METRICS_ENV,
    PAGESPEED_ENABLED_ENV,
    RETRIEVAL_METRICS_ENV,
    STANDARDS_MAX_URLS_ENV,
    STANDARDS_TIMEOUT_ENV,
    WEB_FEATURES_DATASET_ENV,
    WEB_PLATFORM_BASELINE_ENV,
    W3C_CSS_VALIDATOR_ENV,
    W3C_VALIDATOR_ENV,
    boolean_value,
    service,
    service_environment_names,
    service_state,
    services,
)

_SERVICE_PAYLOAD_TO_ENV = {
    "open_web_metrics": OPEN_WEB_METRICS_ENV,
    "derived_readiness_metrics": DERIVED_READINESS_METRICS_ENV,
    "retrieval_metrics": RETRIEVAL_METRICS_ENV,
    "w3c_validator": W3C_VALIDATOR_ENV,
    "w3c_css_validator": W3C_CSS_VALIDATOR_ENV,
    "mdn_observatory": MDN_OBSERVATORY_ENV,
    "web_platform_baseline": WEB_PLATFORM_BASELINE_ENV,
    "pagespeed_enabled": PAGESPEED_ENABLED_ENV,
    "crux_enabled": CRUX_ENABLED_ENV,
    "gsc_enabled": GSC_ENABLED_ENV,
}
_SERVICE_PAYLOAD_DEFAULTS: dict[str, bool | None] = {
    "open_web_metrics": True,
    "derived_readiness_metrics": True,
    "retrieval_metrics": True,
    "w3c_validator": True,
    "w3c_css_validator": True,
    "mdn_observatory": True,
    "web_platform_baseline": True,
    # None is deliberate: omitted credential-driven controls mean
    # "auto when all service requirements are available on the worker".
    "pagespeed_enabled": None,
    "crux_enabled": None,
    "gsc_enabled": None,
}
_SERVICE_FIELDS = frozenset({*_SERVICE_PAYLOAD_TO_ENV, "standards_max_urls", "standards_timeout_seconds"})


def _bool_payload(payload: Mapping[str, Any], name: str, default: bool | None) -> bool | None:
    value = payload.get(name, default)
    if value is None and default is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"AUDIT payload field {name} must be boolean or null for auto")
    return value


def _int_payload(payload: Mapping[str, Any], name: str, default: int) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 100000:
        raise ValueError(f"AUDIT payload field {name} must be an integer between 0 and 100000")
    return value


def _number_payload(payload: Mapping[str, Any], name: str, default: float) -> float:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"AUDIT payload field {name} must be numeric")
    value = float(value)
    if not value > 0 or not value < 3600:
        raise ValueError(f"AUDIT payload field {name} must be > 0 and < 3600 seconds")
    return value


def install_service_contract() -> None:
    """Extend the current secret-free SaaS job options and imported references."""
    from rasai import audit_execution_contract as contract
    if getattr(contract, "_rasai_standards_service_contract", False):
        _rebind_contract_consumers(contract)
        return

    original_options = contract.audit_job_options
    original_defaults = contract.audit_job_defaults
    original_normalize = contract.normalize_audit_job_payload
    original_environment = contract.audit_job_environment_overrides
    original_fields = contract.AUDIT_JOB_FIELDS
    contract.AUDIT_JOB_FIELDS = frozenset((*original_fields, *_SERVICE_FIELDS))

    def options_with_services():
        options = list(original_options())
        options.extend((
            contract.AuditJobOption("open_web_metrics", True, "boolean", description="Browser-native W3C performance metrics; zero external calls."),
            contract.AuditJobOption("derived_readiness_metrics", True, "boolean", description="Crawlability/indexability/canonical/sitemap/structured-data consolidations."),
            contract.AuditJobOption("retrieval_metrics", True, "boolean", description="MRR and relevance-based IR metrics when judgments exist."),
            contract.AuditJobOption("w3c_validator", True, "boolean", description="W3C Nu HTML Checker; bounded external validation."),
            contract.AuditJobOption(
                "w3c_css_validator", True, "boolean",
                description="W3C CSS Validation Service; bounded and throttled to at least one second between public-service requests.",
            ),
            contract.AuditJobOption("mdn_observatory", True, "boolean", description="MDN HTTP Observatory security posture scan."),
            contract.AuditJobOption("web_platform_baseline", True, "boolean", description="WebDX/Baseline integration; requires versioned dataset on worker to materialize compatibility results."),
            contract.AuditJobOption(
                "pagespeed_enabled", None, "boolean",
                required_when="Auto requires RASAI_PAGESPEED_API_KEY in worker/deployment environment.",
                description="null/omitted=auto by requirements; false=explicitly disabled; true=requested explicitly.",
            ),
            contract.AuditJobOption(
                "crux_enabled", None, "boolean",
                required_when="Auto requires RASAI_CRUX_API_KEY in worker/deployment environment.",
                description="null/omitted=auto by requirements; false=explicitly disabled; true=requested explicitly.",
            ),
            contract.AuditJobOption(
                "gsc_enabled", None, "boolean",
                required_when="Auto requires Search Console OAuth token and job-scoped property context.",
                description="null/omitted=auto by requirements; false=explicitly disabled; true=requested explicitly.",
            ),
            contract.AuditJobOption("standards_max_urls", DEFAULT_STANDARDS_MAX_URLS, "integer", description="Bounded URL cap for external standards checks; 0 means all audited URLs."),
            contract.AuditJobOption("standards_timeout_seconds", DEFAULT_STANDARDS_TIMEOUT_SECONDS, "number", description="Timeout per standards-service request."),
        ))
        return tuple(options)

    def defaults_with_services():
        result = dict(original_defaults())
        result.update(_SERVICE_PAYLOAD_DEFAULTS)
        result["standards_max_urls"] = DEFAULT_STANDARDS_MAX_URLS
        result["standards_timeout_seconds"] = DEFAULT_STANDARDS_TIMEOUT_SECONDS
        return result

    def normalize_with_services(payload: Mapping[str, Any]):
        base_payload = {key: value for key, value in payload.items() if key not in _SERVICE_FIELDS}
        normalized = dict(original_normalize(base_payload))
        for name, default in _SERVICE_PAYLOAD_DEFAULTS.items():
            normalized[name] = _bool_payload(payload, name, default)
        normalized["standards_max_urls"] = _int_payload(payload, "standards_max_urls", DEFAULT_STANDARDS_MAX_URLS)
        normalized["standards_timeout_seconds"] = _number_payload(payload, "standards_timeout_seconds", DEFAULT_STANDARDS_TIMEOUT_SECONDS)
        return normalized

    def environment_with_services(payload: Mapping[str, Any]):
        base_payload = {key: value for key, value in payload.items() if key not in _SERVICE_FIELDS}
        overrides = dict(original_environment(base_payload))
        normalized = normalize_with_services(payload)
        for name, env_name in _SERVICE_PAYLOAD_TO_ENV.items():
            value = normalized[name]
            if value is None:
                # Keep worker/deployment environment authoritative in auto mode.
                continue
            overrides[env_name] = "true" if value else "false"
        overrides[STANDARDS_MAX_URLS_ENV] = str(normalized["standards_max_urls"])
        overrides[STANDARDS_TIMEOUT_ENV] = f"{normalized['standards_timeout_seconds']:g}"
        return overrides

    contract.audit_job_options = options_with_services
    contract.audit_job_defaults = defaults_with_services
    contract.normalize_audit_job_payload = normalize_with_services
    contract.audit_job_environment_overrides = environment_with_services
    contract._rasai_standards_service_contract = True
    _rebind_contract_consumers(contract)


def _rebind_contract_consumers(contract: Any) -> None:
    bindings = {
        "rasai.execution_contract": ("normalize_audit_job_payload", contract.normalize_audit_job_payload),
        "rasai.worker": (
            ("normalize_audit_job_payload", contract.normalize_audit_job_payload),
            ("audit_job_environment_overrides", contract.audit_job_environment_overrides),
        ),
        "rasai.saas_context_integration": ("normalize_audit_job_payload", contract.normalize_audit_job_payload),
        "rasai.web.saas_management_routes": ("audit_job_options", contract.audit_job_options),
    }
    for module_name, assignments in bindings.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        if assignments and isinstance(assignments[0], str):
            assignments = (assignments,)  # type: ignore[assignment]
        for name, value in assignments:  # type: ignore[misc]
            setattr(module, name, value)


def install_console_service_catalog() -> None:
    """Enrich the import-time console catalog with standards-specific metadata."""
    from rasai import console_config, console_environment
    if getattr(console_environment, "_rasai_standards_service_catalog", False):
        return
    source = "docs/STANDARDS_METRICS_AND_SERVICES.md"
    category = "Métricas e padrões"
    specs = list(console_environment.SPECS)
    by_name = {spec.name: index for index, spec in enumerate(specs)}

    def upsert(spec: Any) -> None:
        index = by_name.get(spec.name)
        if index is None:
            by_name[spec.name] = len(specs)
            specs.append(spec)
        else:
            specs[index] = spec

    for item in services():
        default = None if item.auto_enable_with_credentials else ("true" if item.default_enabled else "false")
        upsert(console_environment.EnvironmentSpec(
            item.enabled_env,
            category,
            f"Liga/desliga {item.label}. {item.purpose}",
            "booleano",
            ("true", "false"),
            default,
            required_when=(
                "Override opcional; em auto exige credencial/configuração obrigatória para execução."
                if item.credential_envs else "Nunca; pode ser desligado explicitamente pelo usuário."
            ),
            impact=item.network_behavior,
            source=source,
            notes=f"Relação com RASAi: {item.relation_degree}/5. Escopo: {', '.join(item.scopes)}.",
        ))
        if item.dataset_env:
            upsert(console_environment.EnvironmentSpec(
                item.dataset_env,
                category,
                "Caminho para dataset WebDX/web-features versionado usado na compatibilidade Baseline.",
                "caminho de arquivo",
                required_when="Somente para materializar Web Platform Baseline.",
                source=source,
                notes="Não é segredo e pode ser persistido no INI.",
            ))

    for name, purpose, default in (
        (STANDARDS_MAX_URLS_ENV, "Máximo de URLs submetidas a validadores externos; 0=todas.", str(DEFAULT_STANDARDS_MAX_URLS)),
        (STANDARDS_TIMEOUT_ENV, "Timeout por request de serviço de padrões.", f"{DEFAULT_STANDARDS_TIMEOUT_SECONDS:g}"),
    ):
        upsert(console_environment.EnvironmentSpec(name, category, purpose, "número", default=default, source=source))

    names = tuple(dict.fromkeys((*console_environment.ENV_NAMES, *service_environment_names())))
    console_environment.ENV_NAMES = names
    spec_map = {spec.name: spec for spec in specs}
    console_environment.SPECS = tuple(spec_map[name] for name in names if name in spec_map)
    console_environment.SPEC_BY_NAME = {spec.name: spec for spec in console_environment.SPECS}
    if category not in console_environment.CATEGORIES:
        categories = list(console_environment.CATEGORIES)
        try:
            index = categories.index("Control plane / SaaS")
        except ValueError:
            index = len(categories)
        categories.insert(index, category)
        console_environment.CATEGORIES = tuple(categories)

    console_config.ENV_NAMES = tuple(dict.fromkeys((*console_config.ENV_NAMES, *service_environment_names())))
    console_environment._rasai_standards_service_catalog = True


def install_report_contract() -> None:
    """Keep standards detail auxiliary to the stable canonical report navigation.

    ``standards.html`` is generated and linked from thematic report panels, but the
    pre-publication canonical navigation remains owned exclusively by report_contract.
    This avoids import-order-dependent mutations and duplicate top-level surfaces.
    """
    return None


def _explicit_false(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip()
    return bool(raw) and not boolean_value(raw, default=True)


def install_collection_runtime() -> None:
    """Apply per-service enablement without duplicating canonical collectors."""
    from rasai import cli as audit_cli
    from rasai import m21_web_performance as m21
    from rasai import open_web_metrics
    if getattr(audit_cli, "_rasai_standards_collection_runtime", False):
        return

    original_capture = open_web_metrics.capture_open_web_metrics
    def capture_with_toggle(page: Any):
        state = service_state(service("open-web-metrics"))
        if not bool(state["effective_enabled"]):
            return {
                "contract_version": open_web_metrics.OPEN_WEB_METRICS_CONTRACT_VERSION,
                "state": "DISABLED",
                "enabled_by_default": True,
                "scope": "DEVICE_SNAPSHOT",
                "additional_navigation_requests": 0,
                "additional_external_api_calls": 0,
                "score_impact": "NONE",
                "reason": "RASAI_OPEN_WEB_METRICS_DISABLED",
            }
        return original_capture(page)
    open_web_metrics.capture_open_web_metrics = capture_with_toggle

    original_configured = audit_cli._configured_web_performance
    def configured_with_services(args: Any):
        psi = service_state(service("pagespeed"))
        crux = service_state(service("crux"))
        explicit_global_off = args.web_performance is False or (args.web_performance is None and _explicit_false("RASAI_WEB_PERFORMANCE"))
        if explicit_global_off:
            return original_configured(args)
        any_ready = bool(psi["effective_enabled"] or crux["effective_enabled"])
        if args.web_performance is None and any_ready and not (os.environ.get("RASAI_WEB_PERFORMANCE") or "").strip():
            shadow = type("Args", (), vars(args).copy())()
            shadow.web_performance = True
            config = original_configured(shadow)
        else:
            config = original_configured(args)
        if not any_ready:
            return replace(config, enabled=False).validate()
        field_source = config.field_source
        crux_key = config.crux_api_key if bool(crux["effective_enabled"]) else None
        if field_source == "crux" and not crux_key:
            field_source = "none"
        return replace(config, crux_api_key=crux_key, field_source=field_source).validate()
    audit_cli._configured_web_performance = configured_with_services

    original_execute = m21.execute_m21
    class DisabledPageSpeed:
        def run(self, **_: Any):
            raise m21.ExternalServiceError(
                "PAGESPEED_INSIGHTS", "PageSpeed service disabled or not configured",
                error_code="SERVICE_DISABLED", duration_ms=0,
            )
    def execute_with_services(*args: Any, **kwargs: Any):
        psi = service_state(service("pagespeed"))
        if not bool(psi["effective_enabled"]) and kwargs.get("pagespeed_client") is None:
            kwargs["pagespeed_client"] = DisabledPageSpeed()
        return original_execute(*args, **kwargs)
    execute_with_services._rasai_standards_services = True
    m21.execute_m21 = execute_with_services
    audit_cli.execute_m21 = execute_with_services
    audit_cli._rasai_standards_collection_runtime = True


def install_report_runtime() -> None:
    """Materialize standards observations and enrich canonical report surfaces."""
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_metrics import execute_standards_metrics, enrich_existing_reports, write_standards_report
    if getattr(report_completion, "_rasai_standards_runtime", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_standards(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            execute_standards_metrics(audit_id=audit_id, workspace=workspace)
            write_standards_report(audit_id=audit_id, workspace=workspace)
            enrich_existing_reports(audit_id=audit_id, workspace=workspace)
            report_dir = workspace.root / "report"
            report_navigation.normalize_report_navigation(report_dir)
            enhance_report_directory(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"standards:{type(exc).__name__}:{str(exc)[:240]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )
    report_completion.finalize_audit_report_site = finalize_with_standards
    report_completion._rasai_standards_runtime = True


def install_pre_context() -> None:
    install_service_contract()
    install_console_service_catalog()
    install_report_contract()


def install_post_context() -> None:
    install_service_contract()
    install_collection_runtime()
    install_report_runtime()
