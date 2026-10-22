"""Offline configuration-source inventory for RASAi operator audit (#523).

Use: python -m rasai.console_configuration_inventory
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
        # POSIX ctime detects a same-length in-place rewrite even when
        # mtime is restored. Windows creation time can differ between
        # stat(path) and fstat(descriptor), so it is not comparable there.
        if os.name != "nt":
            fields += ("st_ctime_ns",)
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
        # Windows-created UTF-8 INI may include a BOM; do not mistake it
        # for an invalid section or mutate the operator-owned source.
        parser.read_string(data.decode("utf-8-sig"))
    except (OSError, UnicodeError):
        return None, "SOURCE_UNREADABLE"
    except ConfigError:
        return None, "SOURCE_INVALID_INI"
    return parser, "SOURCE_PARSED_NO_RUNTIME_CONSUMER_PROOF"


def _safe_ini(path: Path) -> ConfigParser | None:
    """Compatibility inspection helper; do not expose source values."""
    parser, _ = _ini_with_status(path)
    return parser


def _explicit_environment_keys(parser: ConfigParser | None) -> frozenset[str]:
    """Only physical [environment] assignments, excluding [DEFAULT] inheritance."""
    if parser is None or not parser.has_section("environment"):
        return frozenset()
    # ConfigParser.has_option/items/get merge [DEFAULT], which would fabricate
    # persisted environment provenance and false positives for secret placement.
    return frozenset(parser._sections["environment"])


def _origin(key: str, parser: ConfigParser | None, environ: Mapping[str, str]) -> str:
    """Return only provenance, not the setting, for registered nonsecret vars."""
    from_ini = (
        parser.get("environment", key, fallback="").strip()
        if key in _explicit_environment_keys(parser) else ""
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
    from rasai.console_perplexity_readiness import _FILTERS

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


def _declared_gsc_consumer_surface() -> dict[str, str]:
    """Map source-declared GSC scope/OAuth/policy inputs without HTTP.

    References real constants in GSC scope, OAuth and Search Analytics policy.
    Presence of those keys does not prove OAuth access, property matching,
    data-finality or a GSC API call for the current AUD.
    """
    from rasai import gsc_scope, gsc_oauth, standards_gsc_policy

    gate = (gsc_scope.GSC_ENABLED_ENV, gsc_scope.GSC_SITE_URL_ENV)
    oauth = (
        gsc_oauth.ACCESS_TOKEN_ENV,
        gsc_oauth.CLIENT_ID_ENV,
        gsc_oauth.CLIENT_SECRET_ENV,
        gsc_oauth.REFRESH_TOKEN_ENV,
    )
    policy = (
        standards_gsc_policy.GSC_SEARCH_ANALYTICS_DAYS_ENV,
        standards_gsc_policy.GSC_SEARCH_MAX_ROWS_ENV,
        standards_gsc_policy.GSC_FINAL_DATA_LAG_DAYS_ENV,
    )
    result = {
        name: "GSC_SCOPE_DECLARED_NOT_PROPERTY_OR_API_PROOF"
        for name in gate
    }
    result.update({
        name: "GSC_OAUTH_INPUT_DECLARED_NOT_AUTHENTICATION_PROOF"
        for name in oauth
    })
    result.update({
        name: "GSC_ANALYTICS_POLICY_DECLARED_NOT_DATA_FINALITY_PROOF"
        for name in policy
    })
    return result



def _declared_console_core_surface() -> dict[str, str]:
    """Only settings read by the current console bootstrap/default parser.

    These constants and input keys occur in console_config.apply_environment_defaults,
    not in a measured M21, provider, AI-orchestrator or report execution.
    Classifying their origin closes a static inventory gap without asserting
    that a local INI was applied by a live engine or a paid request occurred.
    """
    from rasai import console_config as core

    declared: dict[str, str] = {
        "RASAI_DEVICE_CONTEXT": "CONSOLE_DEVICE_INPUT_NOT_EXECUTION_PROOF",
        core.AI_TIMEOUT_ENV: "CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF",
        core.AI_MAX_CYCLES_ENV: "CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF",
        core.AI_CYCLE_DELAY_ENV: "CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF",
        "RASAI_AI_CONTENT_REMEDIATION": "CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF",
        "RASAI_AI_TECHNICAL_REMEDIATION": "CONSOLE_AI_CONTROL_INPUT_NOT_PROVIDER_PROOF",
        "RASAI_WEB_PERFORMANCE": "CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF",
        "RASAI_WEB_PERFORMANCE_MAX_PAGES": "CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF",
        core.WEB_PERFORMANCE_TIMEOUT_ENV: "CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF",
        "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": "CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF",
        "RASAI_LIGHTHOUSE_CATEGORIES": "CONSOLE_WEB_PERFORMANCE_INPUT_NOT_M21_PROOF",
    }
    declared.update({
        name: "CONSOLE_CONTENT_CONTEXT_INPUT_NOT_AI_EXECUTION_PROOF"
        for name in core.CONTENT_CONTEXT_ENV_NAMES
    })
    return declared

def _declared_security_and_improvement_surface() -> dict[str, str]:
    """Declare real adapter inputs; do not imply security feed or AI execution."""
    from rasai import passive_security, improvement_intelligence as improvement

    security = (
        passive_security.ENABLED_ENV,
        passive_security.HEADERS_ENV,
        passive_security.COOKIES_ENV,
        passive_security.RESOURCES_ENV,
        passive_security.THIRD_PARTY_ENV,
        passive_security.RUNTIME_ENV,
        passive_security.OSV_ENV,
        passive_security.KEV_ENV,
        passive_security.EXTERNAL_TIMEOUT_ENV,
    )
    result = {
        name: "PASSIVE_SECURITY_INPUT_DECLARED_NOT_COLLECTION_PROOF"
        for name in security
    }
    improvement_inputs = (
        improvement.ENABLED_ENV,
        improvement.PROVIDER_ENV,
        improvement.MODEL_ENV,
        improvement.REASONING_ENV,
        improvement.DOMAINS_ENV,
        improvement.MAX_RECOMMENDATIONS_ENV,
        improvement.TIMEOUT_ENV,
    )
    result.update({
        name: "IMPROVEMENT_INPUT_DECLARED_NOT_PROVIDER_EXECUTION_PROOF"
        for name in improvement_inputs
    })
    result[improvement.AI_ANALYSIS_LANGUAGE_ENV] = (
        "IMPROVEMENT_LANGUAGE_INPUT_NOT_PROVIDER_EXECUTION_PROOF"
    )
    return result


def _declared_ai_catalog_surface() -> dict[str, str]:
    """Only canonical AI catalog selectors, never provider-use evidence."""
    from rasai import ai_model_catalog, ai_pricing_catalog, ai_task_profiles

    return {
        ai_model_catalog.MODEL_SOURCE_ENV: "MODEL_SOURCE_DECLARED_NOT_PROVIDER_USE",
        ai_model_catalog.MODEL_FILE_ENV: "MODEL_FILE_DECLARED_NOT_PROVIDER_USE",
        ai_pricing_catalog.PRICING_SOURCE_ENV: "PRICING_SOURCE_DECLARED_NOT_BILLING",
        ai_pricing_catalog.PRICING_FILE_ENV: "PRICING_FILE_DECLARED_NOT_BILLING",
        ai_task_profiles.PROFILE_SOURCE_ENV: "PROFILE_SOURCE_DECLARED_NOT_AI_USE",
        ai_task_profiles.PROFILE_FILE_ENV: "PROFILE_FILE_DECLARED_NOT_AI_USE",
    }


def _declared_presentation_surface() -> dict[str, str]:
    """The presentation timezone consumer cannot mutate persisted AUD clocks."""
    from rasai.time_contract import PRESENTATION_TIMEZONE_ENV

    return {
        PRESENTATION_TIMEZONE_ENV:
        "PRESENTATION_FORMAT_INPUT_NOT_PERSISTED_CLOCK_CHANGE"
    }


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
    gsc_affinities = _declared_gsc_consumer_surface()
    console_core_affinities = _declared_console_core_surface()
    security_improvement_affinities = _declared_security_and_improvement_surface()
    ai_catalog_affinities = _declared_ai_catalog_surface()
    presentation_affinities = _declared_presentation_surface()
    consumer_affinities = {
        **presentation_affinities,
        **ai_catalog_affinities,
        **security_improvement_affinities,
        **console_core_affinities, **gsc_affinities,
        **search_affinities, **apdex_affinities,
    }
    seen: set[str] = set()
    explicit_ini_keys = _explicit_environment_keys(parser)
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
            "secret_present_in_ini_violation": bool(
                sensitive and parser is not None
                and key in explicit_ini_keys
            ),
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
    # Secrets may exist in INI under keys omitted from the current registry.
    # Report a count only; never expose arbitrary (potentially sensitive) names.
    unregistered_secret_ini_keys = (
        sum(
            1 for key in explicit_ini_keys
            if key not in seen and is_secret(key)
        )
        if parser is not None and parser.has_section("environment") else 0
    )
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
        {
            "name": "perplexity_draft.queries",
            "scope": "REUSABLE_INI_DRAFT_NO_EXECUTION_INTENT",
            "new_audit_consent_inherited": False,
        },
        {
            "name": "perplexity_draft.search_type",
            "scope": "REUSABLE_INI_DRAFT_NO_EXECUTION_INTENT",
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
            present = bool(
                parser is not None
                and parser.has_section(section)
                and option in parser._sections[section]
            )
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
        "secret_ini_policy_violations": sum(
            1 for item in variables if item["secret_present_in_ini_violation"]
        ),
        "secret_ini_scan_complete": parser is not None,
        "unregistered_secret_ini_key_count": unregistered_secret_ini_keys,
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
        "ai_catalog_adapter_surface_coverage": {
            "mapped_registry_variables": sum(
                item["name"] in ai_catalog_affinities for item in variables
            ),
            "catalog_load_or_provider_use_proven": False,
            "pricing_or_bill_proven": False,
        },
        "security_improvement_adapter_surface_coverage": {
            "mapped_registry_variables": sum(
                item["name"] in security_improvement_affinities for item in variables
            ),
            "external_security_feeds_or_ai_provider_calls_proven": False,
            "security_snapshot_or_improvement_execution_proven": False,
            "source": "PASSIVE_SECURITY_AND_IMPROVEMENT_CONFIG_DECLARATIONS",
        },
        "console_core_adapter_surface_coverage": {
            "mapped_registry_variables": sum(
                item["name"] in console_core_affinities for item in variables
            ),
            "unmapped_registry_variables": sum(
                item["name"] not in console_core_affinities for item in variables
            ),
            "runtime_device_or_provider_execution_proven": False,
            "actual_web_performance_or_ai_usage_proven": False,
            "source": "CONSOLE_CONFIG_APPLY_ENVIRONMENT_DEFAULTS_DECLARATIONS",
        },
        "gsc_adapter_surface_coverage": {
            "mapped_registry_variables": sum(
                item["name"] in gsc_affinities for item in variables
            ),
            "unmapped_registry_variables": sum(
                item["name"] not in gsc_affinities for item in variables
            ),
            "authenticated_property_coverage_proven": False,
            "actual_gsc_api_read_coverage_proven": False,
            "source": "GSC_SCOPE_OAUTH_AND_ANALYTICS_POLICY_DECLARATIONS",
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
        "--acceptance-523", action="store_true",
        help="one offline acceptance gate: typed state, Perplexity draft, Apdex, core, SERP, GSC",
    )
    parser.add_argument(
        "--verify-apdex", action="store_true",
        help="offline M23/M25 adapter validation on an isolated INI copy; no audit or APIs",
    )
    parser.add_argument(
        "--verify-gsc", action="store_true",
        help="check Google Search Console scope/OAuth/policy from INI offline; never authenticate",
    )
    parser.add_argument(
        "--verify-core", action="store_true",
        help="verify core AI/Web console INI -> real audit CLI consumer offline",
    )
    parser.add_argument(
        "--verify-search", action="store_true",
        help="check SERP console INI -> governed AUD argv -> real CLI parser offline",
    )
    parser.add_argument(
        "--reconcile-typed", action="store_true",
        help="inspect declared typed INI adapters without loading it into the OS environment",
    )
    args = parser.parse_args(argv)
    report = inventory(path=args.ini)
    if args.verify_apdex:
        from rasai.console_apdex_effective_validation import inspect_apdex_consumers
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        report["apdex_offline_consumer_preflight"] = inspect_apdex_consumers(selected)
    if args.verify_gsc:
        from rasai.console_gsc_consumer_preflight import inspect_gsc_consumers
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        report["gsc_offline_consumer_preflight"] = inspect_gsc_consumers(selected)
    if args.verify_core:
        from rasai.console_core_consumer_preflight import inspect_core_consumers
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        report["core_offline_consumer_preflight"] = inspect_core_consumers(selected)
    if args.verify_search:
        from rasai.console_search_consumer_preflight import inspect_search_consumers
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        report["search_offline_consumer_preflight"] = inspect_search_consumers(selected)
    if args.reconcile_typed:
        from rasai.console_typed_reconciliation import inspect_typed_configuration
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        report["typed_adapter_reconciliation"] = inspect_typed_configuration(selected)
    if args.acceptance_523:
        from rasai.console_acceptance_contract import inspect_console_acceptance
        selected = args.ini if args.ini is not None else canonical_console_config_path()
        gate = inspect_console_acceptance(selected, prior=report)
        report["acceptance_523"] = gate
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if args.acceptance_523 and report["acceptance_523"]["status"] not in {
        "OFFLINE_CONTRACTS_VERIFIED", "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES",
    } else 0


if __name__ == "__main__":
    raise SystemExit(main())
