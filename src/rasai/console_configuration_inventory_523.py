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


def _ini_with_status(path: Path) -> tuple[ConfigParser | None, str]:
    """Metadata-only physical-source inspection with bounded immutable read.

    The file can change concurrently; only report a loaded INI if its
    opened descriptor and path metadata still match the pre-read source.
    This is not a cryptographic seal or effective-consumer verification.
    """
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        if path.is_symlink():
            return None, "SOURCE_SYMLINK_DISALLOWED"
        if not path.is_file():
            return None, "SOURCE_NOT_FOUND_OR_NOT_A_FILE"
        before = path.stat()
        if before.st_size > 2_000_000:
            return None, "SOURCE_TOO_LARGE"
        with path.open("rb") as stream:
            import os as _os
            descriptor = _os.fstat(stream.fileno())
            data = stream.read(2_000_001)
        after = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        if (
            path.is_symlink()
            or any(
                getattr(before, field) != getattr(other, field)
                for other in (descriptor, after) for field in fields
            )
            or len(data) != before.st_size
        ):
            return None, "SOURCE_CHANGED_DURING_READ"
        if len(data) > 2_000_000:
            return None, "SOURCE_TOO_LARGE"
        parser.read_string(data.decode("utf-8"))
    except (OSError, UnicodeError):
        return None, "SOURCE_UNREADABLE"
    except ConfigError:
        return None, "SOURCE_INVALID_INI"
    return parser, "SOURCE_PARSED_NO_RUNTIME_CONSUMER_PROOF"


def _safe_ini(path: Path) -> ConfigParser | None:
    """Compatibility inspection helper; do not expose source values."""
    parser, _ = _ini_with_status(path)
    return parser


def _origin(key: str, parser: ConfigParser | None, environ: Mapping[str, str]) -> str:
    """Return only provenance, not the setting, for registered nonsecret vars."""
    from_ini = (
        parser.get("environment", key, fallback="").strip()
        if parser is not None else ""
    )
    from_session = str(environ.get(key) or "").strip()
    if from_session and from_ini and from_session != from_ini:
        return "SESSION_DIFFERS_FROM_INI_EFFECTIVE_PRIORITY_UNVERIFIED"
    if from_session and from_ini:
        return "SESSION_EQUALS_INI"
    if from_session:
        return "SESSION_OR_PROCESS_ENV"
    if from_ini:
        return "INI"
    return "RUNTIME_DEFAULT_OR_ABSENT"



def _declared_apdex_consumer_surface() -> dict[str, str]:
    """Classify source-declared adapter INPUTS, not real executed consumers.

    This map is derived from actual M23/M25 CLI constants. It deliberately
    does not turn registry metadata into a claim about executed collectors,
    persisted AUD snapshots, paid integrations, or operator authorization.
    """
    from rasai import m23_cli, m25_cli

    navigation = (
        m23_cli.APDEX_ENABLED_ENV,
        m23_cli.APDEX_THRESHOLD_ENV,
        m23_cli.APDEX_SAMPLES_ENV,
        m23_cli.APDEX_MAX_ATTEMPTS_ENV,
        m23_cli.APDEX_MAX_PAGES_ENV,
        m23_cli.APDEX_TIMEOUT_ENV,
        m23_cli.APDEX_DELAY_ENV,
        m23_cli.APDEX_CONCURRENCY_ENV,
    )
    declared: dict[str, str] = {}
    for name in navigation:
        declared[name] = "M23_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF"
    for name in m25_cli.M25_ENV_NAMES:
        if name in (m25_cli.UX_ARCHITECTURE_ENV, m25_cli.UX_PROFILE_MODE_ENV):
            declared[name] = "CAT07_DECLARATIVE_INPUT_NOT_M25_MEASUREMENT"
        elif name == m25_cli.UX_DEVICE_MIX_ENV:
            declared[name] = "INERT_DEVICE_MIX_DERIVED_FROM_CONSOLE_DEVICE"
        else:
            declared[name] = "M25_CLI_INPUT_CANDIDATE_NOT_EXECUTION_PROOF"
    for name in m23_cli.profile_environment_names():
        declared[name] = "SHARED_APDEX_PROFILE_INPUT_NOT_EXECUTION_PROOF"
    return declared


def _declared_search_consumer_surface() -> dict[str, str]:
    """Only statically declared SERP config and Perplexity readiness inputs.

    SERP config's canonical env names are read by SerpRuntimeConfig; they
    are NOT proof of a real provider request. Perplexity activation/key and
    optional filters are recognized by its readiness layer, which does not
    authorize a paid request or inherit per-AUD consent.
    """
    from rasai.search_intelligence.config import (
        SERP_ENV_NAMES, SERP_PROVIDER_KEY_ENVS,
    )
    from rasai.search_intelligence.perplexity import API_KEY_ENV
    from rasai.console_perplexity_readiness_318 import _FILTERS

    result: dict[str, str] = {}
    secret_keys = set(SERP_PROVIDER_KEY_ENVS)
    for name in SERP_ENV_NAMES:
        result[name] = (
            "SERP_PROVIDER_SECRET_DECLARED_NOT_REQUEST_PROOF"
            if name in secret_keys
            else "SERP_CONFIG_INPUT_DECLARED_NOT_REQUEST_PROOF"
        )
    result[API_KEY_ENV] = "PERPLEXITY_KEY_READINESS_NOT_REQUEST_CONSENT"
    result["RASAI_PERPLEXITY_ENABLED"] = (
        "PERPLEXITY_ACTIVATION_READINESS_NOT_PER_AUD_CONSENT"
    )
    for name in _FILTERS:
        result[name] = "PERPLEXITY_FILTER_READINESS_NOT_PROVIDER_USE_PROOF"
    return result


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
    parser, ini_status = _ini_with_status(file)

    specs = refresh_specs()
    apdex_affinities = _declared_apdex_consumer_surface()
    search_affinities = _declared_search_consumer_surface()
    consumer_affinities = {**search_affinities, **apdex_affinities}
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
            "declared_adapter_surface": consumer_affinities.get(
                key, "NOT_MAPPED_NO_CONSUMER_INFERENCE"
            ),
            "declared_adapter_surface_is_execution_proof": False,
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
    # The experience device mix is computed from console.device on both save
    # and load. Its absence in older INIs does not represent an operator input
    # lost on restore; never suggest copying an obsolete multi-device value.
    derived_state = frozenset({("synthetic_apdex_experience", "device_mix")})
    for section, options in console_settings._state_values(state).items():
        for option in options:
            present = bool(parser is not None and parser.has_option(section, option))
            derived = (section, option) in derived_state
            state_fields.append({
                "name": f"{section}.{option}",
                "scope": (
                    "DERIVED_FROM_CONSOLE_DEVICE" if derived
                    else "INI_EXECUTION_INPUT" if section == "search_intelligence"
                    else "INI_TYPED_STATE"
                ),
                "ini_section": section,
                "ini_present": present,
                "missing_ini_is_effective_config_loss": (
                    False if derived else None
                ),
            })
    missing = [
        field["name"] for field in state_fields
        if not field["ini_present"] and field["scope"] != "DERIVED_FROM_CONSOLE_DEVICE"
    ]
    derived_missing = [
        field["name"] for field in state_fields
        if not field["ini_present"] and field["scope"] == "DERIVED_FROM_CONSOLE_DEVICE"
    ]
    return {
        "contract": "RASAI-CONSOLE-CONFIG-INVENTORY-523-1",
        "registry_size": len(specs),
        "environment_variables": variables,
        "apdex_adapter_surface_coverage": {
            "mapped_registry_variables": sum(
                item["name"] in apdex_affinities for item in variables
            ),
            "unmapped_registry_variables": sum(
                item["name"] not in apdex_affinities for item in variables
            ),
            "execution_or_aud_snapshot_coverage_proven": False,
        },
        "search_adapter_surface_coverage": {
            "mapped_registry_variables": sum(
                item["name"] in search_affinities for item in variables
            ),
            "unmapped_registry_variables": sum(
                item["name"] not in search_affinities for item in variables
            ),
            "per_aud_provider_consent_proven": False,
            "real_provider_request_coverage_proven": False,
            "source": "SERP_RUNTIME_CONFIG_AND_PERPLEXITY_READINESS_DECLARATIONS",
        },
        "typed_state_fields": state_fields,
        "typed_ini_coverage": {
            "total": len(state_fields),
            "present": sum(1 for item in state_fields if item["ini_present"]),
            "missing_non_derived_names": missing if parser is not None else [],
            "missing_derived_names": derived_missing if parser is not None else [],
            "missing_non_derived_is_execution_failure_proven": False,
        },
        "execution_inputs": execution_inputs,
        "file_readable": parser is not None,
        "ini_source_status": ini_status,
        "ini_source_status_is_execution_proof": False,
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
    parser.add_argument(
        "--verify-apdex", action="store_true",
        help="offline M23/M25 adapter validation on an isolated INI copy; no audit or APIs",
    )
    args = parser.parse_args(argv)
    report = inventory(path=args.ini)
    if args.verify_apdex:
        from rasai.console_apdex_effective_validation_523 import inspect_apdex_consumers
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        report["apdex_offline_consumer_preflight"] = inspect_apdex_consumers(selected)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
