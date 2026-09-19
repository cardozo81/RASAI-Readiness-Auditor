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
from rasai.ai_execution_configuration import install as install_ai_execution_configuration
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
from rasai.console_environment_reset import install_ai_secret_cancellation, install_environment_reset
from rasai.console_execution_profile_readiness import install as install_execution_profile_readiness
from rasai.console_execution_profiles import install as install_execution_profiles
from rasai.console_first_run_cost_preview import install as install_first_run_cost_preview
from rasai.console_governed_progress import install as install_console_governed_progress
from rasai.console_governed_search_runtime import install as install_console_governed_search_runtime
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
from rasai.external_observability_runtime import install as install_external_observability_runtime, install_service_contract as install_external_observability_service_contract
from rasai.final_smoke_closure import install as install_final_smoke_closure
from rasai.fulfillment_execution_contract import install_console_projection
from rasai.governed_analysis_runtime import (
    install_post as install_governed_analysis_post,
    install_pre as install_governed_analysis_pre,
)
from rasai.governed_report_projection_runtime import install as install_governed_report_projection
from rasai.gsc_oauth_console import install as install_gsc_oauth_console
from rasai.gsc_oauth_runtime import install as install_gsc_oauth_runtime
from rasai.gsc_scope_runtime import install as install_gsc_scope_runtime
from rasai.improvement_intelligence_console import install as install_improvement_intelligence_console, install_environment as install_improvement_intelligence_environment
from rasai.improvement_intelligence_runtime import install as install_improvement_intelligence_runtime
from rasai.passive_security_console import install as install_passive_security_environment
from rasai.passive_security_runtime import install as install_passive_security_runtime
from rasai.integration_diagnostics_console import install as install_integration_diagnostics_console
from rasai.integration_network_diagnostics import install as install_integration_network_diagnostics
from rasai.integration_state_contract import install as install_integration_state_contract
from rasai.m21_console_progress import install_m21_external_progress
from rasai.m3_console_progress import install_m3_render_progress
from rasai.m3_render_deadline_runtime import install as install_m3_render_deadline_runtime
from rasai.runtime_adherence_extensions import install_runtime_adherence_extensions
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.runtime_contract_compatibility import install_console_runtime_contract_compatibility
from rasai.runtime_progress_gate import install_search_progress_gate
from rasai.search_fulfillment_runtime import install as install_search_fulfillment
from rasai.selective_optional_reprocess import install as install_selective_optional_reprocess
from rasai.semantic_context_console import install as install_semantic_context_console
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_css_validation import install as install_standards_css_validation
from rasai.standards_gsc_console_progress import install as install_standards_gsc_console_progress
from rasai.standards_gsc_observability_runtime import install as install_standards_gsc_observability_runtime
from rasai.standards_ir_reconciliation import install as install_standards_ir_reconciliation
from rasai.standards_m21_reconciliation import install as install_standards_m21_reconciliation
from rasai.standards_operational_reconciliation import install as install_standards_operational_reconciliation
from rasai.standards_runtime import install_post_context as install_standards_post_context, install_pre_context as install_standards_pre_context
from rasai.standards_structured_data_reconciliation import install as install_standards_structured_data_reconciliation
from rasai.system_default_dependencies import install as install_system_default_dependencies
from rasai.system_defaults import install as install_system_defaults
from rasai.target_input_runtime import install as install_target_input_runtime
from rasai.windows_environment import activate_persisted_environment


def _activate_persisted_console_secrets() -> tuple[str, ...]:
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

    # Install governance before runtime adapters capture collector functions.
    # Re-assert the post boundary after console composition so no later wrapper can
    # execute network/AI or mutate audit.db during catalog projection.
    install_governed_analysis_pre()
    install_standards_pre_context()
    install_external_observability_service_contract()
    install_standards_console_runtime()
    install_external_observability_console()
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
    install_gsc_oauth_console()
    install_external_observability_runtime()
    install_improvement_intelligence_environment()
    install_passive_security_environment()
    install_semantic_context_console()
    _activate_persisted_console_secrets()
    prepare_console_config()
    install_ai_efficiency_policy()
    install_runtime_completion_extensions()
    install_standards_console_runtime()
    install_external_observability_console()
    install_gsc_oauth_console()
    install_ai_model_console()
    install_ai_pricing_console()
    install_runtime_adherence_extensions()
    install_integration_state_contract()
    install_m3_render_progress()
    install_m21_external_progress()
    install_search_progress_gate()
    install_standards_gsc_console_progress()
    install_console_cancellation_runtime()
    install_improvement_intelligence_runtime()
    install_passive_security_runtime()
    install_selective_optional_reprocess()
    install_masked_secret_input()
    install_environment_reset()
    interactive_console._environment_menu = console_environment.environment_menu
    interactive_console._configure_apdex = configure_apdex
    install_search_guidance(console_search_intelligence)
    install_search_intelligence(interactive_console)
    install_consolidation(interactive_console)
    install_console_runtime_contract_compatibility()
    install_console_progress_presentation()
    install_console_governed_progress()
    install_ai_provider_console_management()
    install_ai_secret_cancellation()
    install_improvement_intelligence_console(interactive_console)
    install_cost_confirmation(interactive_console)
    install_first_run_cost_preview(interactive_console)
    install_system_defaults(interactive_console)
    install_system_default_dependencies(interactive_console)
    install_execution_profile_readiness()
    install_execution_profiles(interactive_console)
    install_integration_diagnostics_console(interactive_console)
    install_audit_configuration_reuse_console(interactive_console)
    install_console_navigation(interactive_console)
    install_console_preparation_layout(interactive_console)
    install_audit_management_console(interactive_console)
    install_console_audit_workflow(interactive_console)
    install_execution_context_isolation()
    install_console_reprocess_parity(interactive_console)
    install_search_fulfillment(interactive_console)
    install_console_governed_search_runtime(interactive_console)
    install_console_projection(interactive_console)
    install_integration_network_diagnostics(interactive_console)
    install_console_detail_presentation()
    install_ai_execution_configuration(interactive_console)
    # Final runtime/catalog bindings must win after all console adapters are composed.
    install_final_smoke_closure()
    install_governed_analysis_post()
    install_governed_report_projection()
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
