"""CLI/environment configuration contract for M23 Synthetic Navigation Apdex."""
from __future__ import annotations

import argparse
import math
import os
from typing import Any

from rasai.m23_apdex import SyntheticApdexConfig
from rasai.m25_apdex_experience import ExperienceApdexConfig
from rasai.m25_cli import UX_ENABLED_ENV, configured_experience, register_experience_arguments
from rasai.m25_runtime import set_pending_config

APDEX_ENABLED_ENV = "RASAI_SYNTHETIC_APDEX"
APDEX_THRESHOLD_ENV = "RASAI_APDEX_THRESHOLD_SECONDS"
APDEX_SAMPLES_ENV = "RASAI_APDEX_SAMPLES_PER_CONTEXT"
APDEX_MAX_ATTEMPTS_ENV = "RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT"
APDEX_MAX_PAGES_ENV = "RASAI_APDEX_MAX_PAGES"
APDEX_TIMEOUT_ENV = "RASAI_APDEX_TIMEOUT_SECONDS"
APDEX_DELAY_ENV = "RASAI_APDEX_DELAY_SECONDS"
APDEX_CONCURRENCY_ENV = "RASAI_APDEX_CONCURRENCY"

DEFAULT_APDEX_SAMPLES_PER_CONTEXT = 100
DEFAULT_APDEX_MAX_PAGES = 1
DEFAULT_APDEX_TIMEOUT_SECONDS = 45.0
DEFAULT_APDEX_DELAY_SECONDS = 1.0
DEFAULT_APDEX_CONCURRENCY = 1
MAX_APDEX_CONCURRENCY = 2


def register_apdex_arguments(audit_parser: argparse.ArgumentParser) -> None:
    """Add M23 options plus the additive M25 calibrated UX options."""
    audit_parser.add_argument(
        "--synthetic-apdex",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "enable Synthetic Navigation Apdex; default OFF or "
            f"{APDEX_ENABLED_ENV}; requires an explicit T"
        ),
    )
    audit_parser.add_argument(
        "--apdex-threshold-seconds",
        type=float,
        default=None,
        help=(
            "Apdex target threshold T in seconds; mandatory when Synthetic Navigation Apdex is enabled; "
            f"or {APDEX_THRESHOLD_ENV}"
        ),
    )
    audit_parser.add_argument(
        "--apdex-samples-per-context",
        type=int,
        default=None,
        help=(
            "target number of VALID cold-context samples per page/device; "
            f"default {DEFAULT_APDEX_SAMPLES_PER_CONTEXT} or {APDEX_SAMPLES_ENV}. "
            "Groups below 100 valid samples are marked small-group (*) and are not a normal final Apdex group"
        ),
    )
    audit_parser.add_argument(
        "--apdex-max-attempts-per-context",
        type=int,
        default=None,
        help=(
            "hard attempt budget used to replace invalid tool/profile samples; "
            "default ceil(1.25 * target samples), or "
            f"{APDEX_MAX_ATTEMPTS_ENV}"
        ),
    )
    audit_parser.add_argument(
        "--apdex-max-pages",
        type=int,
        default=None,
        help=(
            "maximum audited pages measured by Synthetic Apdex; 0 means all; "
            f"default {DEFAULT_APDEX_MAX_PAGES} or {APDEX_MAX_PAGES_ENV}"
        ),
    )
    audit_parser.add_argument(
        "--apdex-timeout-seconds",
        type=float,
        default=None,
        help=(
            "navigation timeout for each synthetic sample; must be > 4*T. "
            "When omitted it is max(45s, 4*T+5s), or use "
            f"{APDEX_TIMEOUT_ENV}"
        ),
    )
    audit_parser.add_argument(
        "--apdex-delay-seconds",
        type=float,
        default=None,
        help=(
            "minimum delay between STARTS of synthetic navigation samples for the audited origin; "
            f"default {DEFAULT_APDEX_DELAY_SECONDS:g}s or {APDEX_DELAY_ENV}. "
            "No random jitter is added so runs remain reproducible"
        ),
    )
    audit_parser.add_argument(
        "--apdex-concurrency",
        type=int,
        default=None,
        help=(
            "parallel synthetic workers; default 1, maximum 2. Each worker uses its own Chromium gateway "
            "and every sample uses a fresh browser context with cache disabled. Or "
            f"{APDEX_CONCURRENCY_ENV}"
        ),
    )
    register_experience_arguments(audit_parser)


def configured_apdex(args: Any, env: dict[str, str] | os._Environ[str] | None = None) -> SyntheticApdexConfig:
    """Resolve M23 config with CLI > environment > safe defaults.

    M25 is an additive child capability. It is parsed here and handed off as a
    one-shot process-local config to the M23 execution stage; it cannot be
    enabled while M23 itself is OFF.
    """
    environment = env if env is not None else os.environ
    set_pending_config(ExperienceApdexConfig(enabled=False))
    enabled = _configured_bool(getattr(args, "synthetic_apdex", None), APDEX_ENABLED_ENV, False, environment)
    ux_requested = _configured_bool(getattr(args, "apdex_experience", None), UX_ENABLED_ENV, False, environment)
    if not enabled:
        if ux_requested:
            raise ValueError("Synthetic User Experience Apdex exige Synthetic Navigation Apdex habilitado (--synthetic-apdex)")
        return SyntheticApdexConfig(enabled=False).validate()

    threshold = _optional_positive_float(
        getattr(args, "apdex_threshold_seconds", None),
        APDEX_THRESHOLD_ENV,
        environment,
    )
    if threshold is None:
        raise ValueError(
            "Synthetic Apdex requires explicit T: use --apdex-threshold-seconds "
            f"or {APDEX_THRESHOLD_ENV}"
        )
    samples = _positive_int(
        getattr(args, "apdex_samples_per_context", None),
        APDEX_SAMPLES_ENV,
        DEFAULT_APDEX_SAMPLES_PER_CONTEXT,
        environment,
    )
    max_attempts = _optional_positive_int(
        getattr(args, "apdex_max_attempts_per_context", None),
        APDEX_MAX_ATTEMPTS_ENV,
        environment,
    )
    if max_attempts is None:
        max_attempts = max(samples, int(math.ceil(samples * 1.25)))
    max_pages = _nonnegative_int(
        getattr(args, "apdex_max_pages", None),
        APDEX_MAX_PAGES_ENV,
        DEFAULT_APDEX_MAX_PAGES,
        environment,
    )
    timeout = _optional_positive_float(
        getattr(args, "apdex_timeout_seconds", None),
        APDEX_TIMEOUT_ENV,
        environment,
    )
    if timeout is None:
        timeout = max(DEFAULT_APDEX_TIMEOUT_SECONDS, 4.0 * threshold + 5.0)
    delay = _nonnegative_float(
        getattr(args, "apdex_delay_seconds", None),
        APDEX_DELAY_ENV,
        DEFAULT_APDEX_DELAY_SECONDS,
        environment,
    )
    concurrency = _positive_int(
        getattr(args, "apdex_concurrency", None),
        APDEX_CONCURRENCY_ENV,
        DEFAULT_APDEX_CONCURRENCY,
        environment,
    )
    if concurrency > MAX_APDEX_CONCURRENCY:
        raise ValueError(f"Synthetic Apdex concurrency must be <= {MAX_APDEX_CONCURRENCY} to bound origin load")

    experience = configured_experience(
        args,
        environment,
        standard_max_pages=max_pages,
        standard_delay_seconds=delay,
        standard_concurrency=concurrency,
    )
    set_pending_config(experience)

    return SyntheticApdexConfig(
        enabled=True,
        threshold_seconds=threshold,
        target_valid_samples=samples,
        max_attempts_per_context=max_attempts,
        max_pages=max_pages,
        timeout_seconds=timeout,
        delay_seconds=delay,
        concurrency=concurrency,
    ).validate()


def _configured_bool(
    cli_value: bool | None,
    env_name: str,
    default: bool,
    env: dict[str, str] | os._Environ[str],
) -> bool:
    if cli_value is not None:
        return bool(cli_value)
    raw = (env.get(env_name) or "").strip()
    if not raw:
        return default
    value = raw.casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{env_name} must be one of: true/false, 1/0, yes/no, on/off")


def _optional_positive_float(
    cli_value: float | None,
    env_name: str,
    env: dict[str, str] | os._Environ[str],
) -> float | None:
    if cli_value is not None:
        value = float(cli_value)
    else:
        raw = (env.get(env_name) or "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{env_name} / CLI value must be a positive finite number")
    return value


def _nonnegative_float(
    cli_value: float | None,
    env_name: str,
    default: float,
    env: dict[str, str] | os._Environ[str],
) -> float:
    if cli_value is not None:
        value = float(cli_value)
    else:
        raw = (env.get(env_name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be a finite number >= 0") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{env_name} / CLI value must be a finite number >= 0")
    return value


def _optional_positive_int(
    cli_value: int | None,
    env_name: str,
    env: dict[str, str] | os._Environ[str],
) -> int | None:
    if cli_value is not None:
        value = int(cli_value)
    else:
        raw = (env.get(env_name) or "").strip()
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be an integer >= 1") from exc
    if value < 1:
        raise ValueError(f"{env_name} / CLI value must be >= 1")
    return value


def _positive_int(
    cli_value: int | None,
    env_name: str,
    default: int,
    env: dict[str, str] | os._Environ[str],
) -> int:
    value = _optional_positive_int(cli_value, env_name, env)
    return default if value is None else value


def _nonnegative_int(
    cli_value: int | None,
    env_name: str,
    default: int,
    env: dict[str, str] | os._Environ[str],
) -> int:
    if cli_value is not None:
        value = int(cli_value)
    else:
        raw = (env.get(env_name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f"{env_name} must be an integer >= 0") from exc
    if value < 0:
        raise ValueError(f"{env_name} / CLI value must be >= 0")
    return value
