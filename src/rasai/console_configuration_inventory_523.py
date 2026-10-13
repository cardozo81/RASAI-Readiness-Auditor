"""Offline configuration-source inventory for RASAi operator audit (#523).

Use: python -m rasai.console_configuration_inventory_523
The output is METADATA ONLY: never emits secret values, query content,
credentials, concrete URLs, user paths, or session consent.
"""
from __future__ import annotations

import argparse
from configparser import ConfigParser, Error as ConfigError
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from rasai.console_config import is_secret
from rasai.console_config_path import canonical_console_config_path
from rasai.console_provider_environment import refresh_specs


def _safe_ini(path: Path) -> ConfigParser | None:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        if not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        with path.open(encoding="utf-8") as stream:
            parser.read_file(stream)
    except (OSError, UnicodeError, ConfigError):
        return None
    return parser


def _origin(key: str, parser: ConfigParser | None, environ: Mapping[str, str]) -> str:
    """Return only provenance, not the setting, for registered nonsecret vars."""
    from_ini = (
        parser.get("environment", key, fallback="").strip()
        if parser is not None else ""
    )
    from_session = str(environ.get(key) or "").strip()
    if from_session and from_ini and from_session != from_ini:
        return "SESSION_OVERRIDES_INI"
    if from_session and from_ini:
        return "SESSION_EQUALS_INI"
    if from_session:
        return "SESSION_OR_PROCESS_ENV"
    if from_ini:
        return "INI"
    return "RUNTIME_DEFAULT_OR_ABSENT"


def inventory(
    *,
    path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Reconcile live EnvironmentSpec with persisted names without any writes."""
    from rasai.console_search_intelligence import SearchConsoleState
    from rasai import console_settings
    from rasai.console_ui_refactor import _install_search_persistence
    from rasai.console_complete_persistence import install as install_complete_persistence

    _install_search_persistence()
    install_complete_persistence()
    environment = os.environ if environ is None else environ
    file = Path(path) if path is not None else canonical_console_config_path(env=environment)
    parser = _safe_ini(file)

    specs = refresh_specs()
    seen: set[str] = set()
    variables = []
    for spec in specs:
        key = str(spec.name)
        if key in seen:
            raise ValueError(f"duplicate canonical environment variable: {key}")
        seen.add(key)
        sensitive = bool(spec.sensitive or is_secret(key))
        variables.append({
            "name": key,
            "category": str(spec.category),
            "value_type": str(spec.value_type),
            "sensitive": sensitive,
            "scope": "OS_SECRET_OR_SESSION" if sensitive else "INI_AND_SESSION",
            "persist_ini": not sensitive,
            "runtime_default_declared": spec.default is not None,
            "status": (
                "SECRET_PRESENT" if str(environment.get(key) or "").strip() else "SECRET_ABSENT"
            ) if sensitive else _origin(key, parser, environment),
            "runtime_consumer": "NOT_PROVEN_BY_REGISTRY",
            "audit_snapshot": "AUD_DEPENDENT_NOT_INFERRED",
        })
    # These are execution inputs, NOT EnvironmentSpecs. No values ever emitted.
    execution_inputs = [
        {
            "name": "search_intelligence.queries",
            "scope": "REUSABLE_INI_EXECUTION_INPUT",
            "new_audit_consent_inherited": False,
        },
        {
            "name": "perplexity_queries",
            "scope": "SESSION_ONLY_EXECUTION_OPT_IN",
            "new_audit_consent_inherited": False,
        },
        {
            "name": "perplexity_search_type",
            "scope": "SESSION_ONLY_EXECUTION_OPT_IN",
            "new_audit_consent_inherited": False,
        },
    ]
    state = SearchConsoleState()
    state_fields = []
    for section, options in console_settings._state_values(state).items():
        for option in options:
            state_fields.append({
                "name": f"{section}.{option}",
                "scope": (
                    "INI_EXECUTION_INPUT" if section == "search_intelligence"
                    else "INI_TYPED_STATE"
                ),
                "ini_section": section,
                "ini_present": bool(parser is not None and parser.has_option(section, option)),
            })
    return {
        "contract": "RASAI-CONSOLE-CONFIG-INVENTORY-523-1",
        "registry_size": len(specs),
        "environment_variables": variables,
        "typed_state_fields": state_fields,
        "execution_inputs": execution_inputs,
        "file_readable": parser is not None,
        "metadata_only": True,
        "values_exposed": False,
        "live_consumers_verified": False,
        "audit_snapshot_coverage_verified": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List the RASAi console registry and safe INI/session provenance offline."
    )
    parser.add_argument("--ini", type=Path, help="optional configuration file for metadata inspection")
    args = parser.parse_args(argv)
    print(json.dumps(inventory(path=args.ini), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
