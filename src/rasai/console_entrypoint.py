"""Public entrypoint for the interactive RASAi console.

Local operation remains the default. ``RASAI_CONSOLE_MODE=remote`` switches to a
small HTTP control-plane client without importing or reimplementing the audit engine.
The local path installs the canonical configuration, report and runtime adapters.
"""
from __future__ import annotations

import os

from rasai import console_search_intelligence, interactive_console
from rasai.console_apdex_configuration import configure_apdex
from rasai.console_config_path import prepare_console_config
from rasai.console_environment import environment_menu
from rasai.console_search_guidance import install as install_search_guidance
from rasai.console_search_intelligence import install as install_search_intelligence
from rasai.consolidation.integration import install as install_consolidation
from rasai.documented_contract_reconciliation import install_console_documented_contract_reconciliation
from rasai.report_registry import install as install_report_registry
from rasai.runtime_adherence_extensions import install_runtime_adherence_extensions
from rasai.runtime_completion_extensions import install_runtime_completion_extensions
from rasai.runtime_progress_gate import install_search_progress_gate


def main() -> int:
    mode = (os.getenv("RASAI_CONSOLE_MODE") or "local").strip().casefold()
    if mode not in {"local", "remote"}:
        raise SystemExit("RASAI_CONSOLE_MODE must be local or remote")
    if mode == "remote":
        from rasai.remote_console import main as remote_main

        return remote_main()
    prepare_console_config()
    install_report_registry()
    install_runtime_completion_extensions()
    install_runtime_adherence_extensions()
    install_search_progress_gate()
    interactive_console._environment_menu = environment_menu
    interactive_console._configure_apdex = configure_apdex
    install_search_guidance(console_search_intelligence)
    install_search_intelligence(interactive_console)
    install_consolidation(interactive_console)
    install_console_documented_contract_reconciliation()
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
