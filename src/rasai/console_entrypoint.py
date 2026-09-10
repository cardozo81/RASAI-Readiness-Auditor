"""Public entrypoint for the interactive RASAi console.

Local operation remains the default. ``RASAI_CONSOLE_MODE=remote`` switches to a
small HTTP control-plane client without importing or reimplementing the audit engine.
"""
from __future__ import annotations

import os

from rasai import interactive_console
from rasai.console_config_path import prepare_console_config
from rasai.console_environment import environment_menu
from rasai.consolidation.integration import install as install_consolidation
from rasai.report_registry import install as install_report_registry


def main() -> int:
    mode = (os.getenv("RASAI_CONSOLE_MODE") or "local").strip().casefold()
    if mode not in {"local", "remote"}:
        raise SystemExit("RASAI_CONSOLE_MODE must be local or remote")
    if mode == "remote":
        from rasai.remote_console import main as remote_main

        return remote_main()
    prepare_console_config()
    install_report_registry()
    interactive_console._environment_menu = environment_menu
    install_consolidation(interactive_console)
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
