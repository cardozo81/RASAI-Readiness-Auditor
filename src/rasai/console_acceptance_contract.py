"""#523 single offline gate for the existing independent configuration consumers.

This is an acceptance *preflight*, never an operator paid-execution consent.
One optional command produces a bounded status for all adapters; only source
metadata, counts and code-level states are reported. Caller INI, audit,
credentials and process environment are never modified intentionally.
"""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from typing import Any, Mapping

from rasai.console_apdex_effective_validation import _verified_source

_CONTRACT = "RASAI-CONSOLE-ACCEPTANCE-523-001"
_PASSED = {
    "typed": frozenset({"TYPED_ADAPTERS_INSPECTED"}),
    "apdex": frozenset({"ADAPTERS_VALIDATED_OFFLINE"}),
    "core": frozenset({"CORE_CLI_PARITY_VERIFIED"}),
    "search": frozenset({"CLI_ADAPTERS_VALIDATED_OFFLINE"}),
    "gsc": frozenset({"LOCAL_SCOPE_AND_OAUTH_CONFIG_VERIFIED"}),
    "perplexity": frozenset({"DRAFT_RESTORED_NO_EXECUTION_INTENT"}),
}
_INTENTIONALLY_ABSENT = {
    "search": frozenset({"NO_SEARCH_QUERY_INPUT"}),
    "gsc": frozenset({
        "GSC_DISABLED_BY_CONFIGURATION",
        "AUTO_OAUTH_NOT_CONFIGURED",
        "AUTO_PROPERTY_NOT_CONFIGURED",
    }),
    "perplexity": frozenset({"NO_DRAFT_NO_EXECUTION_INTENT"}),
}
# No target in a saved PREPARAR state is NOT an external prerequisite for
# auditing configuration serialization. It prevents an actual per-URL GSC
# scope check, but not the INI-to-CLI/default/consumer checks. Do not invent a
# URL or mark provider access proven merely to make this gate return 0.
_TARGET_NOT_PREPARED = {
    "core": frozenset({"CLI_PARITY_TARGET_NOT_SET"}),
    "gsc": frozenset({"TARGET_NOT_PREPARED"}),
}
_OUTSIDE_CONFIGURATION = {
    "core": frozenset({"EXTERNAL_WEB_PREREQUISITE_UNVERIFIED"}),
    "gsc": frozenset({
        "REQUIRED_OAUTH_NOT_CONFIGURED",
        "REQUIRED_PROPERTY_NOT_CONFIGURED",
    }),
}


def _perplexity_draft(path: Path) -> dict[str, Any]:
    """Verify actual fresh-state load and zero billable request intent."""
    base = {
        "status": "NOT_VERIFIABLE", "draft_count": None,
        "active_request_count": None, "paid_request_inherited": False,
        "values_exposed": False, "requests": 0, "audit_writes": 0,
    }
    data, identity, status = _verified_source(path)
    if status != "READY":
        return {**base, "status": status}
    assert data is not None and identity is not None
    original_digest = sha256(data).digest()
    initial_environment = dict(os.environ)
    scratch = gettempdir()
    try:
        from rasai.console_search_intelligence import SearchConsoleState
        from rasai.console_ui_refactor import _install_search_persistence
        from rasai.console_complete_persistence import install
        from rasai import console_settings

        _install_search_persistence()
        install()
        # Do not inherit a commercial request from the inspecting process.
        os.environ.clear()
        with TemporaryDirectory(prefix="rasai-perplexity-draft-523-", dir=scratch) as tmp:
            duplicate = Path(tmp) / "config.ini"
            duplicate.write_bytes(data)
            state = SearchConsoleState()
            loaded = console_settings.load_console_config(state, duplicate)
            if loaded.created or loaded.warnings:
                return {**base, "status": "INI_LOAD_WARNINGS"}
            draft = tuple(state.perplexity_draft_queries or ())
            active = tuple(state.perplexity_queries or ())
            valid = (
                len(draft) <= 5
                and all(isinstance(item, str) and item.strip() for item in draft)
                and state.perplexity_draft_search_type in {"web", "fast"}
            )
            if not valid or active or state.perplexity_last_status != "NOT_REQUESTED":
                return {**base, "status": "PERPLEXITY_CONSENT_OR_DRAFT_INVALID"}
            count = len(draft)
        latest, latest_identity, latest_status = _verified_source(path)
        if (
            latest_status != "READY" or latest_identity != identity
            or latest is None or sha256(latest).digest() != original_digest
        ):
            return {**base, "status": "SOURCE_CHANGED"}
        return {
            **base,
            "status": (
                "DRAFT_RESTORED_NO_EXECUTION_INTENT"
                if count else "NO_DRAFT_NO_EXECUTION_INTENT"
            ),
            "draft_count": count,
            "active_request_count": 0,
        }
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError):
        return {**base, "status": "DRAFT_ADAPTER_UNVERIFIABLE"}
    finally:
        os.environ.clear()
        os.environ.update(initial_environment)


def classify_console_acceptance(
    statuses: Mapping[str, str], *,
    invalid_typed_fields: int = 0,
    unknown_typed_fields: int = 0,
) -> dict[str, Any]:
    """Classify truthful acceptance states independently of provider consent.

    A missing GSC credential is not a failed unit test; a mismatched parser
    or a silently lost field is. Both prevent issue closure for distinct reasons.
    """
    failed: list[str] = []
    missing_external: list[str] = []
    intentional: list[str] = []
    unprepared_target: list[str] = []
    if invalid_typed_fields or unknown_typed_fields:
        failed.append("typed")
    for name in ("typed", "apdex", "core", "search", "gsc", "perplexity"):
        observed = statuses.get(name, "NOT_VERIFIABLE")
        if observed in _PASSED.get(name, ()):
            continue
        if observed in _TARGET_NOT_PREPARED.get(name, ()):
            # Independent from missing OAuth / provider access, which are
            # meaningful only for a URL that is actually prepared.
            unprepared_target.append(name)
        elif observed in _INTENTIONALLY_ABSENT.get(name, ()):
            intentional.append(name)
        elif observed in _OUTSIDE_CONFIGURATION.get(name, ()):
            missing_external.append(name)
        elif name not in failed:
            failed.append(name)
    if failed:
        overall = "CONFIGURATION_CONTRACT_FAILURE"
    elif missing_external:
        overall = "EXTERNAL_PREREQUISITE_OR_TARGET_MISSING"
    elif intentional or unprepared_target:
        overall = "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES"
    else:
        overall = "OFFLINE_CONTRACTS_VERIFIED"
    return {
        "status": overall,
        "failed_consumer_names": sorted(failed),
        "external_prerequisite_consumer_names": sorted(missing_external),
        "intentionally_not_requested_consumer_names": sorted(intentional),
        "target_not_prepared_consumer_names": sorted(unprepared_target),
        "target_scope_execution_verified": False,
        "issue_523_final_acceptance_proven": False,
        "real_windows_reopen_verified_by_this_run": False,
        "runner_execution_verified_by_this_run": False,
        "paid_external_use_authorized": False,
    }


def inspect_console_acceptance(
    path: Path, *, prior: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate all adapters on ONE verifiable physical INI generation.

    Every individual consumer checks its own short read; without an outer
    lease a file replaced between two checks could produce a passing report
    that never described any single operator configuration. Source paths,
    values and digests are deliberately absent from public output.
    """
    from rasai.console_typed_reconciliation import inspect_typed_configuration
    from rasai.console_apdex_effective_validation import inspect_apdex_consumers
    from rasai.console_core_consumer_preflight import inspect_core_consumers
    from rasai.console_search_consumer_preflight import inspect_search_consumers
    from rasai.console_gsc_consumer_preflight import inspect_gsc_consumers

    path = Path(path)
    initial_bytes, initial_identity, initial_status = _verified_source(path)
    if initial_status != "READY" or initial_bytes is None or initial_identity is None:
        return {
            "contract": _CONTRACT,
            "status": "INI_SOURCE_UNVERIFIABLE",
            "source_status": initial_status,
            "consumer_status": {},
            "source_generation_consistent": False,
            "issue_523_final_acceptance_proven": False,
            "real_windows_reopen_verified_by_this_run": False,
            "runner_execution_verified_by_this_run": False,
            "paid_external_use_authorized": False,
            "values_exposed": False, "provider_requests": 0,
            "audit_writes": 0, "source_ini_writes": 0,
        }
    generation_digest = sha256(initial_bytes).digest()
    previous = prior if isinstance(prior, Mapping) else {}
    runners = {
        "typed": ("typed_adapter_reconciliation", inspect_typed_configuration),
        "apdex": ("apdex_offline_consumer_preflight", inspect_apdex_consumers),
        "core": ("core_offline_consumer_preflight", inspect_core_consumers),
        "search": ("search_offline_consumer_preflight", inspect_search_consumers),
        "gsc": ("gsc_offline_consumer_preflight", inspect_gsc_consumers),
    }
    results: dict[str, Mapping[str, Any]] = {}
    for name, (key, runner) in runners.items():
        cached = previous.get(key)
        results[name] = cached if isinstance(cached, Mapping) else runner(path)
    results["perplexity"] = _perplexity_draft(path)
    statuses = {key: str(result.get("status") or "NOT_VERIFIABLE")
                for key, result in results.items()}
    counts = results["typed"].get("counts") or {}
    classified = classify_console_acceptance(
        statuses,
        invalid_typed_fields=int(results["typed"].get("invalid_typed_fields") or 0),
        unknown_typed_fields=int(counts.get("UNRECOGNIZED_INPUT_COUNT") or 0),
    )
    # Inspect physical coverage AND forbidden secret entries *before*
    # checking the final generation identity: the inventory itself reads
    # the source and is part of the same atomic validation window.
    source_meta = previous
    if (
        not isinstance(source_meta.get("typed_ini_coverage"), Mapping)
        or "secret_ini_policy_violations" not in source_meta
        or "unregistered_secret_ini_key_count" not in source_meta
        or "file_readable" not in source_meta
    ):
        from rasai.console_configuration_inventory import inventory
        try:
            source_meta = inventory(path=path)
        except (ValueError, OSError, TypeError):
            source_meta = {}
    coverage = source_meta.get("typed_ini_coverage", {})
    secret_policy_violations = (
        int(source_meta.get("secret_ini_policy_violations") or 0)
        + int(source_meta.get("unregistered_secret_ini_key_count") or 0)
    )
    if secret_policy_violations or source_meta.get("file_readable") is not True:
        classified = {
            **classified,
            "status": "CONFIGURATION_CONTRACT_FAILURE",
            "failed_consumer_names": sorted(set(
                classified["failed_consumer_names"]
            ) | {"ini_secret_or_unreadable_source"}),
        }
    latest_bytes, latest_identity, latest_status = _verified_source(path)
    consistent = (
        latest_status == "READY"
        and latest_identity == initial_identity
        and latest_bytes is not None
        and sha256(latest_bytes).digest() == generation_digest
    )
    if not consistent:
        classified = {
            **classified,
            "status": "INI_SOURCE_CHANGED_DURING_GATE",
            "issue_523_final_acceptance_proven": False,
        }
    partial = (
        isinstance(coverage, Mapping)
        and isinstance(coverage.get("missing_non_derived_names"), list)
        and bool(coverage["missing_non_derived_names"])
    )
    if consistent and partial and classified["status"] in {
        "OFFLINE_CONTRACTS_VERIFIED",
        "OFFLINE_CONTRACTS_WITH_INTENTIONAL_ABSENCES",
    }:
        classified = {
            **classified,
            "status": "OFFLINE_TYPED_COVERAGE_PARTIAL",
        }
    return {
        "contract": _CONTRACT,
        **classified,
        "source_generation_consistent": consistent,
        "source_status": latest_status,
        "secret_ini_policy_violations_detected": secret_policy_violations > 0,
        "typed_fields_unavailable": (
            len(coverage["missing_non_derived_names"])
            if isinstance(coverage, Mapping)
            and isinstance(coverage.get("missing_non_derived_names"), list)
            else None
        ),
        "typed_coverage_complete": not partial,
        "consumer_status": statuses,
        "typed_invalid_field_count": int(results["typed"].get("invalid_typed_fields") or 0),
        "typed_unrecognized_field_groups": int(counts.get("UNRECOGNIZED_INPUT_COUNT") or 0),
        "perplexity_draft": results["perplexity"],
        "provider_requests": 0,
        "audit_writes": 0,
        "source_ini_writes": 0,
        "values_exposed": False,
    }


__all__ = ["inspect_console_acceptance", "classify_console_acceptance"]
