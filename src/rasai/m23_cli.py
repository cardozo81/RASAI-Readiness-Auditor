"""CLI/environment configuration contract for Synthetic Navigation Apdex."""
from __future__ import annotations

import argparse
import math
import os
from typing import Any

from rasai.m23_apdex import SyntheticApdexConfig
from rasai.m23_apdex_profiles import profile_from_presets
from rasai.m25_apdex_experience import ExperienceApdexConfig
from rasai.m25_cli import UX_ENABLED_ENV, configured_experience, register_experience_arguments
from rasai.m25_runtime import set_pending_config
from rasai.synthetic_runtime_profiles import (
    PROFILE_ENV_NAMES,
    configured_preset,
    default_preset,
    env_name,
    preset_ids,
)

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


def _profile_dest(device: str, kind: str) -> str:
    return f"apdex_{device.casefold()}_{kind}_profile"


def _register_profile_arguments(parser: argparse.ArgumentParser) -> None:
    for device in ("MOBILE", "DESKTOP", "TABLET"):
        for kind in ("client", "hardware", "network"):
            parser.add_argument(
                f"--apdex-{device.casefold()}-{kind}-profile",
                dest=_profile_dest(device, kind),
                choices=preset_ids(kind, device),
                default=None,
                help=(
                    f"{device.title()} {kind} preset; default {default_preset(kind, device)} "
                    f"or {env_name(kind, device)}"
                ),
            )


def register_apdex_arguments(audit_parser: argparse.ArgumentParser) -> None:
    audit_parser.add_argument(
        "--synthetic-apdex",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=f"enable Synthetic Navigation Apdex; default OFF or {APDEX_ENABLED_ENV}; requires explicit T",
    )
    audit_parser.add_argument(
        "--apdex-threshold-seconds", type=float, default=None,
        help=f"Apdex target threshold T in seconds; required when enabled; or {APDEX_THRESHOLD_ENV}",
    )
    audit_parser.add_argument(
        "--apdex-samples-per-context", type=int, default=None,
        help=f"target VALID samples per page/device; default {DEFAULT_APDEX_SAMPLES_PER_CONTEXT} or {APDEX_SAMPLES_ENV}",
    )
    audit_parser.add_argument(
        "--apdex-max-attempts-per-context", type=int, default=None,
        help=f"attempt budget; default ceil(1.25 * target samples), or {APDEX_MAX_ATTEMPTS_ENV}",
    )
    audit_parser.add_argument(
        "--apdex-max-pages", type=int, default=None,
        help=f"maximum audited pages; 0 means all; default {DEFAULT_APDEX_MAX_PAGES} or {APDEX_MAX_PAGES_ENV}",
    )
    audit_parser.add_argument(
        "--apdex-timeout-seconds", type=float, default=None,
        help=f"navigation timeout; must be > 4*T; default max(45s,4*T+5s), or {APDEX_TIMEOUT_ENV}",
    )
    audit_parser.add_argument(
        "--apdex-delay-seconds", type=float, default=None,
        help=f"minimum interval between sample starts; default {DEFAULT_APDEX_DELAY_SECONDS:g}s or {APDEX_DELAY_ENV}",
    )
    audit_parser.add_argument(
        "--apdex-concurrency", type=int, default=None,
        help=f"parallel synthetic workers 1-2; default {DEFAULT_APDEX_CONCURRENCY} or {APDEX_CONCURRENCY_ENV}",
    )
    _register_profile_arguments(audit_parser)
    register_experience_arguments(audit_parser)


def _resolved_profile(args: Any, environment: dict[str, str] | os._Environ[str], device: str):
    values = {
        kind: configured_preset(kind, device, environment, getattr(args, _profile_dest(device, kind), None))
        for kind in ("client", "hardware", "network")
    }
    return profile_from_presets(
        device=device,
        client_profile_id=values["client"],
        hardware_profile_id=values["hardware"],
        network_profile_id=values["network"],
    )


def configured_apdex(args: Any, env: dict[str, str] | os._Environ[str] | None = None) -> SyntheticApdexConfig:
    """Resolve config with CLI > environment > current controlled defaults."""
    environment = env if env is not None else os.environ
    set_pending_config(ExperienceApdexConfig(enabled=False))
    enabled = _configured_bool(getattr(args, "synthetic_apdex", None), APDEX_ENABLED_ENV, False, environment)
    ux_requested = _configured_bool(getattr(args, "apdex_experience", None), UX_ENABLED_ENV, False, environment)

    mobile_profile = _resolved_profile(args, environment, "MOBILE")
    desktop_profile = _resolved_profile(args, environment, "DESKTOP")

    if not enabled:
        if ux_requested:
            raise ValueError("Synthetic User Experience Apdex exige Synthetic Navigation Apdex habilitado (--synthetic-apdex)")
        return SyntheticApdexConfig(
            enabled=False,
            mobile_profile=mobile_profile,
            desktop_profile=desktop_profile,
        ).validate()

    threshold = _optional_positive_float(getattr(args, "apdex_threshold_seconds", None), APDEX_THRESHOLD_ENV, environment)
    if threshold is None:
        raise ValueError(f"Synthetic Apdex requires explicit T: use --apdex-threshold-seconds or {APDEX_THRESHOLD_ENV}")
    samples = _positive_int(getattr(args, "apdex_samples_per_context", None), APDEX_SAMPLES_ENV, DEFAULT_APDEX_SAMPLES_PER_CONTEXT, environment)
    max_attempts = _optional_positive_int(getattr(args, "apdex_max_attempts_per_context", None), APDEX_MAX_ATTEMPTS_ENV, environment)
    if max_attempts is None:
        max_attempts = max(samples, int(math.ceil(samples * 1.25)))
    max_pages = _nonnegative_int(getattr(args, "apdex_max_pages", None), APDEX_MAX_PAGES_ENV, DEFAULT_APDEX_MAX_PAGES, environment)
    timeout = _optional_positive_float(getattr(args, "apdex_timeout_seconds", None), APDEX_TIMEOUT_ENV, environment)
    if timeout is None:
        timeout = max(DEFAULT_APDEX_TIMEOUT_SECONDS, 4.0 * threshold + 5.0)
    delay = _nonnegative_float(getattr(args, "apdex_delay_seconds", None), APDEX_DELAY_ENV, DEFAULT_APDEX_DELAY_SECONDS, environment)
    concurrency = _positive_int(getattr(args, "apdex_concurrency", None), APDEX_CONCURRENCY_ENV, DEFAULT_APDEX_CONCURRENCY, environment)
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
        mobile_profile=mobile_profile,
        desktop_profile=desktop_profile,
    ).validate()


def profile_environment_names() -> tuple[str, ...]:
    return PROFILE_ENV_NAMES


def _configured_bool(cli_value: bool | None, env_name_value: str, default: bool, env: dict[str, str] | os._Environ[str]) -> bool:
    if cli_value is not None:
        return bool(cli_value)
    raw = (env.get(env_name_value) or "").strip()
    if not raw:
        return default
    value = raw.casefold()
    if value in {"1", "true", "yes", "on"}: return True
    if value in {"0", "false", "no", "off"}: return False
    raise ValueError(f"{env_name_value} must be one of: true/false, 1/0, yes/no, on/off")


def _optional_positive_float(cli_value: float | None, env_name_value: str, env: dict[str, str] | os._Environ[str]) -> float | None:
    if cli_value is not None:
        value = float(cli_value)
    else:
        raw = (env.get(env_name_value) or "").strip()
        if not raw: return None
        try: value = float(raw)
        except ValueError as exc: raise ValueError(f"{env_name_value} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{env_name_value} / CLI value must be a positive finite number")
    return value


def _nonnegative_float(cli_value: float | None, env_name_value: str, default: float, env: dict[str, str] | os._Environ[str]) -> float:
    if cli_value is not None:
        value = float(cli_value)
    else:
        raw = (env.get(env_name_value) or "").strip()
        if not raw: return default
        try: value = float(raw)
        except ValueError as exc: raise ValueError(f"{env_name_value} must be a finite number >= 0") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{env_name_value} / CLI value must be a finite number >= 0")
    return value


def _optional_positive_int(cli_value: int | None, env_name_value: str, env: dict[str, str] | os._Environ[str]) -> int | None:
    if cli_value is not None:
        value = int(cli_value)
    else:
        raw = (env.get(env_name_value) or "").strip()
        if not raw: return None
        try: value = int(raw)
        except ValueError as exc: raise ValueError(f"{env_name_value} must be an integer >= 1") from exc
    if value < 1:
        raise ValueError(f"{env_name_value} / CLI value must be >= 1")
    return value


def _positive_int(cli_value: int | None, env_name_value: str, default: int, env: dict[str, str] | os._Environ[str]) -> int:
    value = _optional_positive_int(cli_value, env_name_value, env)
    return default if value is None else value


def _nonnegative_int(cli_value: int | None, env_name_value: str, default: int, env: dict[str, str] | os._Environ[str]) -> int:
    if cli_value is not None:
        value = int(cli_value)
    else:
        raw = (env.get(env_name_value) or "").strip()
        if not raw: return default
        try: value = int(raw)
        except ValueError as exc: raise ValueError(f"{env_name_value} must be an integer >= 0") from exc
    if value < 0:
        raise ValueError(f"{env_name_value} / CLI value must be >= 0")
    return value
