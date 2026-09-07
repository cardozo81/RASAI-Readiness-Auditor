"""Public entrypoint for the interactive RASAi console.

The established console remains the runtime implementation. This entrypoint
installs additive UI adapters before delegating to it, avoiding a second
audit/configuration engine and keeping consolidated reporting fail-open.
"""
from __future__ import annotations

from searchgeo import interactive_console
from searchgeo.console_config_migration import prepare_console_config
from searchgeo.console_environment import environment_menu
from searchgeo.consolidation.integration import install as install_consolidation
from searchgeo.report_registry import install as install_report_registry


def main() -> int:
    prepare_console_config()
    install_report_registry()
    interactive_console._environment_menu = environment_menu
    install_consolidation(interactive_console)
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
