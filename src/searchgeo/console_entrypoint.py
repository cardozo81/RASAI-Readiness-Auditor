"""Public entrypoint for the interactive SearchGEO console.

The established console remains the runtime implementation. This entrypoint
installs additive UI adapters before delegating to it, avoiding a second
audit/configuration engine and keeping consolidated reporting fail-open.
"""
from __future__ import annotations

from searchgeo import interactive_console
from searchgeo.console_environment import environment_menu
from searchgeo.consolidation.integration import install as install_consolidation


def main() -> int:
    interactive_console._environment_menu = environment_menu
    install_consolidation(interactive_console)
    return interactive_console.main()


if __name__ == "__main__":
    raise SystemExit(main())
