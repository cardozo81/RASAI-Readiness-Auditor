"""Transactional configuration edits for the catalog-driven console.

The public catalog editor writes environment overrides first and then asks the runtime to
rebuild the effective state.  Cross-field contracts (notably Synthetic Navigation Apdex)
can reject an intermediate combination.  This layer makes those edits atomic: dependent
values are reconciled before validation and failed edits restore both environment and
runtime state instead of being reported as successful.
"""
from __future__ import annotations

import math
import os
from types import ModuleType
from typing import Any

from rasai.m23_cli import (
    APDEX_MAX_ATTEMPTS_ENV,
    APDEX_SAMPLES_ENV,
    APDEX_THRESHOLD_ENV,
    APDEX_TIMEOUT_ENV,
)
from rasai.m25_cli import UX_MAX_ATTEMPTS_ENV, UX_SAMPLES_ENV


def _restore_environment(snapshot: dict[str, str | None]) -> None:
    for name, value in snapshot.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


_APDEX_SAMPLE_DEPENDENCIES = {
    APDEX_SAMPLES_ENV: APDEX_MAX_ATTEMPTS_ENV,
    UX_SAMPLES_ENV: UX_MAX_ATTEMPTS_ENV,
}


def _dependent_names(name: str) -> tuple[str, ...]:
    dependent: list[str] = []
    attempts_name = _APDEX_SAMPLE_DEPENDENCIES.get(name)
    if attempts_name is not None:
        dependent.append(attempts_name)
    if name == APDEX_THRESHOLD_ENV:
        dependent.append(APDEX_TIMEOUT_ENV)
    return tuple(dependent)


def _reconcile_apdex_dependencies(name: str, raw: str | None) -> None:
    """Keep Apdex attempt budgets valid when a sample target is increased.

    Both dedicated Apdex configurators derive an attempt budget of
    ``ceil(1.25 * samples)`` when the current budget is insufficient. The canonical
    variable editor must preserve the same contract for Navigation and User Experience
    instead of producing an invalid transient state that is rolled back after runtime
    validation.
    """
    if raw is None:
        return

    attempts_name = _APDEX_SAMPLE_DEPENDENCIES.get(name)
    if attempts_name is not None:
        samples = int(raw)
        attempts_raw = (os.environ.get(attempts_name) or "").strip()
        if attempts_raw:
            attempts = int(attempts_raw)
            if attempts < samples:
                os.environ[attempts_name] = str(max(samples, math.ceil(samples * 1.25)))

    if name == APDEX_THRESHOLD_ENV:
        threshold = float(raw)
        timeout_raw = (os.environ.get(APDEX_TIMEOUT_ENV) or "").strip()
        if timeout_raw:
            timeout = float(timeout_raw)
            if timeout <= 4.0 * threshold:
                recommended = max(45.0, 4.0 * threshold + 5.0)
                os.environ[APDEX_TIMEOUT_ENV] = f"{recommended:g}"


def install(ui_catalog: ModuleType) -> None:
    """Install an idempotent transactional replacement for ``console_ui_catalog._apply``."""
    original = ui_catalog._apply
    if bool(getattr(original, "_rasai_transactional_configuration", False)):
        return

    def apply(state: Any, spec: Any, raw: str | None) -> None:
        from rasai import console_provider_environment as env

        name = str(spec.name)
        watched = {name, *_dependent_names(name)}
        snapshot = {item: os.environ.get(item) for item in watched}
        sensitive = env.base_environment._is_sensitive_spec(spec)

        try:
            if raw is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = env._validate(name, raw)

            _reconcile_apdex_dependencies(name, raw)

            if sensitive:
                env.base_environment._sync_secret_state(state, name)
            env.base_environment._apply_change(state, name)

            issue = str(getattr(state, "error", "") or "").strip()
            if issue:
                raise ValueError(issue)

            env.refresh_specs()
        except (OSError, ValueError, OverflowError):
            _restore_environment(snapshot)
            if sensitive:
                env.base_environment._sync_secret_state(state, name)

            # Rebuild the state from the restored environment so a failed edit cannot
            # leave state and os.environ disagreeing. Preserve the original exception;
            # the editor will surface it instead of clearing state.error as success.
            env.base_environment._apply_change(state, name)
            env.refresh_specs()
            raise

    apply._rasai_transactional_configuration = True  # type: ignore[attr-defined]
    apply._rasai_original = original  # type: ignore[attr-defined]
    ui_catalog._apply = apply
