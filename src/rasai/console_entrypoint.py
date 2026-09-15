"""Public entrypoint for the interactive RASAi console.

Local operation remains the default. ``RASAI_CONSOLE_MODE=remote`` switches to a
small HTTP control-plane client without importing or reimplementing the audit engine.
The local path installs the canonical configuration, report and runtime adapters.
"""
from __future__ import annotations

import os

from rasai import console_provider_environment as console_environment
from rasai import console_search_intelligence, interactive_console
from rasai.ai_efficiency_policy import install as install_ai_efficiency_policy
from rasai.ai_model_console import install as install_ai_model_console
from rasai.ai_pricing_console import install as install_ai_pricing_console
from rasai.ai_provider_console_management import install as install_ai_provider_console_management
from rasai.audit_configuration_reuse_console import install as install_audit_configuration_reuse_console
from rasai.audit_management_console import install as install_audit_management_console
from rasai.console_apdex_configuration import configure_apdex
from rasai.console_audit_workflow import install as install_console_audit_workflow
from rasai.console_cancellation_runtime import install as install_console_cancellation_runtime
from rasai.console_config_path import prepare_console_config
from rasai.console_cost_confirmation import install as install_cost_confirmation
from rasai.console_detail_presentation import install as install_console_detail_presentation
from rasai.console_environment_reset import (
    install_ai_secret_cancellation,
    install_environment_reset,
)
from rasai.console_execution_profile_readiness import install as install_execution_profile_readiness
from rasai.console_execution_profiles import install as install_execution_profiles
from rasai.console_first_run_cost_preview import install as install_first_run_cost_preview
from rasai.console_navigation import install as install_console_navigation
from rasai.console_preparation_layout import install as install_console_preparation_layout
from rasai.console_progress_presentation import install as install_console_progress_presentation
from rasai.console_reprocess_parity import install as install_console_reprocess_parity
from rasai.console_search_guidance import install as install_search_guidance
from rasai.console_search_intelligence import install as install_search_intelligence
from rasai.console_secret_input import install_masked_secret_input
from rasai.consolidation.integration import install as install_consolidation
from rasai.context_scope_runtime import install as install_context_scope_runtime
from rasai.execution_context_isolation import install as install_execution_context_isolation
from rasai.external_measurement_runtime import install as install_external_measurement_runtime
from rasai.external_observability_console import install as install_external_observability_console
from rasai.external_observability_runtime import (
    install as install_external_observability_runtime,
    install_service_contract as install_external_observability_service_contract,
)
from rasai.fulfillment_execution_contract import install_console_projection
from rasai.gsc_oauth_console import install as install_gsc_oauth_console
from rasai.gsc_oauth_runtime import install as install_gsc_oauth_runtime
from rasai.gsc_scope_runtime import install as install_gsc_scope_runtime
from rasai.improvement_intelligence_console import (
    install as install_improvement_intelligence_console,
    install_environment as install_improvement_intelligence_environment,
)
from rasai.improvement_intelligence_runtime import install as install_improvement_intelligence_runtime
from rasai.integration_diagnostics_console import install as install_integration_diagnostics_console
from rasai.integration_network_diagnostics import install as install_integration_network_diagnostics
from rasai.integration_state_contract import install as install_integration_state_contract
from rasai.integration_state_refinements import install as install_integration_state_refinements
from rasai.m21_console_progress import install_m21_external_progress
from rasai.m3_console_progress import install_m3_render_progress
from rasai.m3_render_deadline_runtime import install as install_m3_render_deadline_runtime
from rasai.report_observation_reconciliation import install as install_report_observation_reconciliation
from rasai.report_registry import install as install_report_registry
from rasai.report_scope_clarity import install as install_report_scope_clarity
from rasai.runtime_adherence_extensions import install_runtime_adherence_extensions
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.runtime_contract_compatibility import install_console_runtime_contract_compatibility
from rasai.runtime_progress_gate import install_search_progress_gate
from rasai.search_fulfillment_runtime import install as install_search_fulfillment
from rasai.selective_optional_reprocess import install as install_selective_optional_reprocess
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_css_validation import install as install_standards_css_validation
from rasai.standards_gsc_console_progress import install as install_standards_gsc_console_progress
from rasai.standards_gsc_observability_runtime import install as install_standards_gsc_observability_runtime
from rasai.standards_ir_reconciliation import install as install_standards_ir_reconciliation
from rasai.standards_m21_reconciliation import install as install_standards_m21_reconciliation
from rasai.standards_operational_reconciliation import install as install_standards_operational_reconciliation
from rasai.standards_runtime import (
    install_post_context as install_standards_post_context,
    install_pre_context as install_standards_pre_context,
)
from rasai.standards_structured_data_reconciliation import install as install_standards_structured_data_reconciliation
from rasai.system_default_dependencies import install as install_system_default_dependencies
from rasai.system_defaults import install as install_system_defaults
from rasai.target_input_runtime import install as install_target_input_runtime
from rasai.windows_environment import activate_persisted_environment


def _activate_persisted_console_secrets() -> tuple[str, ...]:
    """Hydrate known persisted secrets before readiness/configuration is evaluated."""
    specs = console_environment.refresh_specs()
    return activate_persisted_environment(
        spec.name
        for spec in specs
        if console_environment.base_environment._is_sensitive_spec(spec)
    )


def main() -> int:
    mode = (os.getenv("RASAI_CONSOLE_MODE") or "local").strip().casefold()
    if mode not in {"local", "remote"}:
        raise SystemExit("RASAI_CONSOLE_MODE must be local or remote")
    if mode == "remote":
        from rasai.remote_console import main as remote_main

        return remote_main()

    # Standards metadata is installed before context projection and before INI load so
    # all non-secret service toggles participate in the normal console persistence flow.
    install_standards_pre_context()
    install_external_observability_service_contract()
    install_standards_console_runtime()
    install_external_observability_console()
    install_report_registry()
    install_context_scope_runtime()
    install_m3_render_deadline_runtime()
    install_target_input_runtime()
    install_external_measurement_runtime()
    install_standards_post_context()
    install_standards_structured_data_reconciliation()
    install_standards_ir_reconciliation()
    install_standards_operational_reconciliation()
    install_standards_css_validation()
    install_standards_m21_reconciliation()
    install_standards_gsc_observability_runtime()
    install_gsc_oauth_runtime()
    install_gsc_scope_runtime()
    # OAuth console metadata is part of the current public configuration contract.
    # Install it before INI/default preparation so Client ID is persistable while
    # Client Secret/Refresh Token remain secret-only and never enter the INI.
    install_gsc_oauth_console()
    install_external_observability_runtime()
    install_improvement_intelligence_environment()
    # Windows/User persistence lives in HKCU and does not require elevation. Read known
    # persisted secrets directly before config/readiness evaluation so a stale parent
    # shell environment cannot make a successfully persisted credential appear absent.
    # An explicit non-empty process/session value keeps precedence.
    _activate_persisted_console_secrets()
    prepare_console_config()
    install_ai_efficiency_policy()
    install_runtime_completion_extensions()
    # Runtime-completion extensions may rebuild the base EnvironmentSpec catalog.
    # Standards/external/OAuth installers are repairable; rerun them so the final public
    # console keeps service metadata, validation and secret-safety semantics.
    install_standards_console_runtime()
    install_external_observability_console()
    install_gsc_oauth_console()
    # Model/pricing source and path are operator settings. Both participate in the
    # canonical environment catalog and Restore Defaults, while credentials stay secret.
    install_ai_model_console()
    install_ai_pricing_console()
    install_report_observation_reconciliation()
    install_runtime_adherence_extensions()
    install_integration_state_contract()
    install_integration_state_refinements()
    install_m3_render_progress()
    install_m21_external_progress()
    install_search_progress_gate()
    install_standards_gsc_console_progress()
    install_console_cancellation_runtime()
    install_improvement_intelligence_runtime()
    # Optional RPR recovery must wrap the final Improvement/GSC owners so successful
    # optional work is reused and only pending work is executed again.
    install_selective_optional_reprocess()
    install_masked_secret_input()
    install_environment_reset()
    interactive_console._environment_menu = console_environment.environment_menu
    interactive_console._configure_apdex = configure_apdex
    install_search_guidance(console_search_intelligence)
    install_search_intelligence(interactive_console)
    install_consolidation(interactive_console)
    install_console_runtime_contract_compatibility()
    install_report_scope_clarity()
    install_console_progress_presentation()
    # Provider management resolves the final configured/active catalog first; the
    # deep-analysis surface then wraps that final console without replacing it.
    install_ai_provider_console_management()
    install_ai_secret_cancellation()
    install_improvement_intelligence_console(interactive_console)
    # Cost confirmation must see the final runtime but remain inside the profile
    # wrapper so session profiles are projected before historical matching.
    install_cost_confirmation(interactive_console)
    # When no comparable history exists, still show current tariff/exposure information
    # and require explicit acknowledgement before the first AI-enabled execution.
    install_first_run_cost_preview(interactive_console)
    # System defaults are installed after all persistent state extensions so the
    # packaged baseline and Restore Defaults include their final sections/metadata.
    install_system_defaults(interactive_console)
    # Higher-precedence parent overrides must suppress dependent lower-precedence
    # defaults without weakening validation of explicitly contradictory choices.
    install_system_default_dependencies(interactive_console)
    # Readiness guidance augments the profile catalog before the profile wrapper captures
    # the final console contract. Profiles remain outermost and session-only. External
    # observability services keep their independent service toggles and are not silently
    # enabled/disabled by a profile preset.
    install_execution_profile_readiness()
    install_execution_profiles(interactive_console)
    # Diagnostics wraps only the final integration/environment surface. It remains
    # advisory and does not participate in execution eligibility, AUTO or quarantine.
    install_integration_diagnostics_console(interactive_console)
    # Configuration reuse wraps the complete detailed configuration surface. The task
    # navigation shell is installed after it and delegates back to that surface.
    install_audit_configuration_reuse_console(interactive_console)
    install_console_navigation(interactive_console)
    # Preparation uses one canonical UX contract: numbered configuration, lettered
    # actions/navigation, and semantic section headings. Factory reset remains only in
    # INÍCIO > Sistema / restaurar padrões.
    install_console_preparation_layout(interactive_console)
    install_audit_management_console(interactive_console)
    # AUD loading/reuse synchronization is installed first. Execution isolation is then
    # applied at the console boundary, after profile/reuse/cancellation owners exist and
    # before later result wrappers capture the composed runtime. Reprocessing parity then
    # becomes the final RPR presentation.
    install_console_audit_workflow(interactive_console)
    install_execution_context_isolation()
    install_console_reprocess_parity(interactive_console)
    # Search is executed by the final composed console chain. Project its result into
    # fulfillment before the canonical result screen computes the logical AUD state.
    install_search_fulfillment(interactive_console)
    # Install last: the physical subprocess may be at 100% while the canonical AUD is
    # still PARTIAL_RETRYABLE/BLOCKED. The final screen must show both facts explicitly.
    install_console_projection(interactive_console)
    # Network diagnostics are the final advisory wrapper so execution/reprocessing
    # warnings observe the fully composed console. They do not block by policy: the
    # operator may continue after explicit acknowledgement, and runtime behavior remains
    # authoritative.
    install_integration_network_diagnostics(interactive_console)
    # Presentation-only final pass: optional technical codes must never render an empty
    # prefix such as "Detalhe : : ...". No diagnostic semantics are changed here.
    install_console_detail_presentation()
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
