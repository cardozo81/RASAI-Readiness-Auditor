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
from rasai.ai_provider_console_management import install as install_ai_provider_console_management
from rasai.console_apdex_configuration import configure_apdex
from rasai.console_cancellation_runtime import install as install_console_cancellation_runtime
from rasai.console_config_path import prepare_console_config
from rasai.console_search_guidance import install as install_search_guidance
from rasai.console_search_intelligence import install as install_search_intelligence
from rasai.consolidation.integration import install as install_consolidation
from rasai.context_scope_runtime import install as install_context_scope_runtime
from rasai.external_measurement_runtime import install as install_external_measurement_runtime
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
from rasai.standards_console_runtime import install as install_standards_console_runtime
from rasai.standards_css_validation import install as install_standards_css_validation
from rasai.standards_gsc_observability_runtime import install as install_standards_gsc_observability_runtime
from rasai.standards_ir_reconciliation import install as install_standards_ir_reconciliation
from rasai.standards_m21_reconciliation import install as install_standards_m21_reconciliation
from rasai.standards_operational_reconciliation import install as install_standards_operational_reconciliation
from rasai.standards_runtime import (
    install_post_context as install_standards_post_context,
    install_pre_context as install_standards_pre_context,
)
from rasai.standards_structured_data_reconciliation import install as install_standards_structured_data_reconciliation
from rasai.target_input_runtime import install as install_target_input_runtime


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
    install_standards_console_runtime()
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
    prepare_console_config()
    install_ai_efficiency_policy()
    install_runtime_completion_extensions()
    install_report_observation_reconciliation()
    install_runtime_adherence_extensions()
    install_integration_state_contract()
    install_integration_state_refinements()
    install_m3_render_progress()
    install_m21_external_progress()
    install_search_progress_gate()
    install_console_cancellation_runtime()
    interactive_console._environment_menu = console_environment.environment_menu
    interactive_console._configure_apdex = configure_apdex
    install_search_guidance(console_search_intelligence)
    install_search_intelligence(interactive_console)
    install_consolidation(interactive_console)
    install_console_runtime_contract_compatibility()
    install_report_scope_clarity()
    # Install last so provider availability, configuration and credential changes are
    # resolved by one final selector before the user starts an execution.
    install_ai_provider_console_management()
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
