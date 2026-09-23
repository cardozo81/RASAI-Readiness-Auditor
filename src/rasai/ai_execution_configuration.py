"""Execution-boundary snapshot for operator-managed AI configuration.

The interactive console is long-lived, while each local audit runs in a fresh child
process. Before an audit starts, this module resolves and validates the current operator
model, pricing and task-profile catalogs, snapshots any file-backed catalogs, refreshes
the parent process used by pre-run cost/readiness UI, and exposes immutable AI catalog
settings to the audit subprocess without freezing unrelated execution-scoped variables.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
from typing import Any, Iterator, Mapping

from rasai.ai_model_catalog import (
    MODEL_FILE_ENV,
    MODEL_SOURCE_ENV,
    AiModelCatalog,
    load_model_catalog,
    model_runtime_settings,
)
from rasai.ai_pricing_catalog import (
    PRICING_FILE_ENV,
    PRICING_SOURCE_ENV,
    PricingCatalog,
    load_pricing_catalog,
    pricing_runtime_settings,
)
from rasai.ai_task_profiles import (
    PROFILE_FILE_ENV,
    PROFILE_SOURCE_ENV,
    AiTaskProfileCatalog,
    load_task_profile_catalog,
    task_profile_runtime_settings,
)

_CURRENT_CHILD_ENV: ContextVar[dict[str, str] | None] = ContextVar(
    "rasai_ai_execution_child_env", default=None
)

# Only these values belong to the immutable AI-catalog snapshot. The execution wrapper
# is installed outermost, before inner catalog/profile/configuration contexts bind their
# own temporary environment variables. Returning the entire environment captured here
# would therefore discard later execution-scoped values such as the canonical AUD
# configuration handoff and catalog feature suppressions.
_FROZEN_AI_ENV_KEYS = (
    MODEL_SOURCE_ENV,
    MODEL_FILE_ENV,
    PRICING_SOURCE_ENV,
    PRICING_FILE_ENV,
    PROFILE_SOURCE_ENV,
    PROFILE_FILE_ENV,
)


@dataclass(frozen=True, slots=True)
class AiExecutionConfiguration:
    environment: Mapping[str, str]
    models: AiModelCatalog
    pricing: PricingCatalog
    task_profiles: AiTaskProfileCatalog


def _snapshot_file(
    *,
    source: str,
    selected: Path,
    destination: Path,
    child_env: dict[str, str],
    source_env: str,
    file_env: str,
) -> None:
    """Freeze one file-backed catalog for the child process."""
    if source == "factory" or (source == "auto" and not selected.is_file()):
        child_env[source_env] = "factory"
        return
    if not selected.is_file():
        raise ValueError(f"{source_env}=file mas arquivo não existe: {selected}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(selected, destination)
    child_env[source_env] = "file"
    child_env[file_env] = str(destination.resolve())


def _refresh_parent_pricing(catalog: PricingCatalog) -> None:
    """Project the validated pricing snapshot into the long-lived console process."""
    from rasai import ai_cost_policy as policy

    flattened = policy._flatten_catalog(catalog)
    policy._EFFECTIVE_CATALOG = catalog
    policy.PRICING_VERSION = catalog.metadata.catalog_version
    policy.PRICING_VERIFIED_ON = catalog.metadata.verified_on
    policy.PRICING_REFERENCE_DATE = catalog.metadata.reference_date
    policy.PRICING_REVIEW_RECOMMENDED_ON = catalog.metadata.review_recommended_on
    policy.PRICING_CATALOG = flattened

    # A few already-imported facades bind these immutable constants by value. Refresh
    # only those public projections; pricing resolver functions already see policy globals.
    projections = {
        "rasai.console_cost": {"PRICING_VERSION": policy.PRICING_VERSION},
        "rasai.m18_ai": {
            "PRICING_VERSION": policy.PRICING_VERSION,
            "PRICING_CATALOG": flattened,
        },
        "rasai.m18_persistence": {"PRICING_CATALOG": flattened},
        "rasai.dynamic_ai_routing": {
            "PRICING_VERSION": policy.PRICING_VERSION,
            "PRICING_REVIEW_RECOMMENDED_ON": policy.PRICING_REVIEW_RECOMMENDED_ON,
        },
        "rasai.consolidation.specialist": {"PRICING_VERSION": policy.PRICING_VERSION},
    }
    for module_name, values in projections.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for name, value in values.items():
            setattr(module, name, value)


def _refresh_parent_models(catalog: AiModelCatalog) -> None:
    from rasai.ai_model_runtime import apply_model_catalog

    apply_model_catalog(catalog)


def _prepare_snapshot(directory: Path, *, cwd: Path) -> AiExecutionConfiguration:
    child_env = dict(os.environ)

    model_source, model_file = model_runtime_settings(env=child_env, cwd=cwd)
    pricing_source, pricing_file = pricing_runtime_settings(env=child_env, cwd=cwd)
    profile_source, profile_file = task_profile_runtime_settings(env=child_env, cwd=cwd)

    _snapshot_file(
        source=model_source,
        selected=model_file,
        destination=directory / "ai-models.toml",
        child_env=child_env,
        source_env=MODEL_SOURCE_ENV,
        file_env=MODEL_FILE_ENV,
    )
    _snapshot_file(
        source=pricing_source,
        selected=pricing_file,
        destination=directory / "ai-pricing.toml",
        child_env=child_env,
        source_env=PRICING_SOURCE_ENV,
        file_env=PRICING_FILE_ENV,
    )
    _snapshot_file(
        source=profile_source,
        selected=profile_file,
        destination=directory / "ai-task-profiles.toml",
        child_env=child_env,
        source_env=PROFILE_SOURCE_ENV,
        file_env=PROFILE_FILE_ENV,
    )

    # Validate every effective catalog before mutating any parent runtime state.
    models = load_model_catalog(env=child_env, cwd=cwd)
    pricing = load_pricing_catalog(env=child_env, cwd=cwd)
    task_profiles = load_task_profile_catalog(env=child_env, cwd=cwd)

    _refresh_parent_models(models)
    _refresh_parent_pricing(pricing)
    return AiExecutionConfiguration(child_env, models, pricing, task_profiles)


@contextmanager
def execution_ai_configuration(*, cwd: Path | None = None) -> Iterator[AiExecutionConfiguration]:
    """Freeze current AI catalogs for one console execution.

    Human edits made under ``config/`` after this context starts cannot change the current
    audit. A later execution creates a new snapshot and therefore sees newly saved edits.
    Execution-scoped environment changes made by inner wrappers remain visible to the
    child; only model/pricing/task-profile source and snapshot paths stay frozen here.
    """
    base = (cwd or Path.cwd()).resolve()
    with tempfile.TemporaryDirectory(prefix="rasai-ai-config-") as raw:
        prepared = _prepare_snapshot(Path(raw), cwd=base)
        token = _CURRENT_CHILD_ENV.set(dict(prepared.environment))
        try:
            yield prepared
        finally:
            _CURRENT_CHILD_ENV.reset(token)


def current_execution_environment() -> dict[str, str] | None:
    """Return the current execution environment plus immutable AI-catalog settings.

    The AI snapshot is created by the outermost console wrapper. Inner execution layers
    subsequently bind catalog suppressions, profile overlays and the secret-free AUD
    configuration handoff. Those values are execution contract data and must not be
    replaced by the older process-wide environment captured when the AI catalogs were
    frozen. Merge the six AI catalog keys onto the live environment instead.
    """
    frozen = _CURRENT_CHILD_ENV.get()
    if frozen is None:
        return None
    environment = dict(os.environ)
    for name in _FROZEN_AI_ENV_KEYS:
        if name in frozen:
            environment[name] = frozen[name]
        else:
            environment.pop(name, None)
    return environment


def install(console_module: ModuleType) -> None:
    """Install as the outermost local execution wrapper."""
    if getattr(console_module, "_rasai_ai_execution_configuration", False):
        return

    from rasai.execution_adherence_refinement import finalize_after_console_run

    original = console_module.run_audit_from_console

    def run(state: Any) -> int:
        try:
            with execution_ai_configuration():
                code = int(original(state) or 0)
                # This wrapper is installed last and is therefore the outermost execution
                # boundary. Rebuild report-catalog only now, after cost/fulfillment and
                # every other inner persistence owner have returned.
                return finalize_after_console_run(state, code)
        except (OSError, UnicodeError, ValueError) as exc:
            state.status = "PRECHECK_FAILED"
            state.operation = "LOCAL:AI_CONFIGURATION"
            state.error = f"Configuração de IA inválida: {exc}"
            return 2

    console_module.run_audit_from_console = run
    console_module._rasai_ai_execution_configuration = True