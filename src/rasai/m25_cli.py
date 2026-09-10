"""CLI/environment contract do M25 Synthetic User Experience Apdex."""
from __future__ import annotations

import argparse
import math
import os
from typing import Any, Mapping

from rasai.m25_apdex_experience import ExperienceApdexConfig
from rasai.m25_dynatrace import SUPPORTED_TIME_KPMS

UX_ENABLED_ENV = "RASAI_APDEX_EXPERIENCE"
UX_SAMPLES_ENV = "RASAI_APDEX_EXPERIENCE_SAMPLES"
UX_MAX_ATTEMPTS_ENV = "RASAI_APDEX_EXPERIENCE_MAX_ATTEMPTS"
UX_MAX_PAGES_ENV = "RASAI_APDEX_EXPERIENCE_MAX_PAGES"
UX_DEVICE_MIX_ENV = "RASAI_APDEX_EXPERIENCE_DEVICE_MIX"
UX_SESSION_MODE_ENV = "RASAI_APDEX_EXPERIENCE_SESSION_MODE"
UX_KPM_ENV = "RASAI_APDEX_EXPERIENCE_KPM"
UX_SATISFIED_ENV = "RASAI_APDEX_EXPERIENCE_SATISFIED_SECONDS"
UX_FRUSTRATED_ENV = "RASAI_APDEX_EXPERIENCE_FRUSTRATED_SECONDS"
UX_ERRORS_ENV = "RASAI_APDEX_EXPERIENCE_ERRORS_AFFECT"
UX_ERROR_SCOPE_ENV = "RASAI_APDEX_EXPERIENCE_ERROR_SCOPE"
UX_SETTLE_ENV = "RASAI_APDEX_EXPERIENCE_SETTLE_SECONDS"
UX_DELAY_ENV = "RASAI_APDEX_EXPERIENCE_DELAY_SECONDS"
UX_CONCURRENCY_ENV = "RASAI_APDEX_EXPERIENCE_CONCURRENCY"
DYNATRACE_IMPORT_ENV = "RASAI_APDEX_DYNATRACE_IMPORT"
DYNATRACE_BASE_URL_ENV = "RASAI_DYNATRACE_BASE_URL"
DYNATRACE_APPLICATION_ID_ENV = "RASAI_DYNATRACE_APPLICATION_ID"
DYNATRACE_CONFIG_JSON_ENV = "RASAI_DYNATRACE_CONFIG_JSON"

M25_ENV_NAMES = (
    UX_ENABLED_ENV, UX_SAMPLES_ENV, UX_MAX_ATTEMPTS_ENV, UX_MAX_PAGES_ENV,
    UX_DEVICE_MIX_ENV, UX_SESSION_MODE_ENV, UX_KPM_ENV, UX_SATISFIED_ENV,
    UX_FRUSTRATED_ENV, UX_ERRORS_ENV, UX_ERROR_SCOPE_ENV, UX_SETTLE_ENV,
    UX_DELAY_ENV, UX_CONCURRENCY_ENV, DYNATRACE_IMPORT_ENV,
    DYNATRACE_BASE_URL_ENV, DYNATRACE_APPLICATION_ID_ENV, DYNATRACE_CONFIG_JSON_ENV,
)

DEFAULT_UX_SAMPLES = 100
DEFAULT_UX_MAX_PAGES = 1
DEFAULT_UX_DEVICE_MIX = "mobile=60,desktop=35,tablet=5"
DEFAULT_UX_SESSION_MODE = "cold"
DEFAULT_UX_KPM = "USER_ACTION_DURATION"
DEFAULT_UX_ERROR_SCOPE = "first-party"
DEFAULT_UX_SETTLE_SECONDS = 5.0
DEFAULT_UX_DELAY_SECONDS = 1.0
DEFAULT_UX_CONCURRENCY = 1


def register_experience_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--apdex-experience", action=argparse.BooleanOptionalAction, default=None,
        help=f"enable calibrated Synthetic User Experience Apdex; default OFF or {UX_ENABLED_ENV}",
    )
    parser.add_argument("--apdex-experience-samples", type=int, default=None, help=f"total valid samples per page across the configured device population; default {DEFAULT_UX_SAMPLES} or {UX_SAMPLES_ENV}")
    parser.add_argument("--apdex-experience-max-attempts", type=int, default=None, help=f"total attempt budget per page; default ceil(1.25*samples) or {UX_MAX_ATTEMPTS_ENV}")
    parser.add_argument("--apdex-experience-max-pages", type=int, default=None, help=f"maximum pages; 0=all; default {DEFAULT_UX_MAX_PAGES} or {UX_MAX_PAGES_ENV}")
    parser.add_argument("--apdex-experience-device-mix", default=None, help=f"percentage distribution of synthetic user-action samples; must total 100; default {DEFAULT_UX_DEVICE_MIX} or {UX_DEVICE_MIX_ENV}")
    parser.add_argument("--apdex-experience-session-mode", choices=("cold", "warm"), default=None, help=f"cold=fresh context/cache; warm=reused context/cache/cookies; or {UX_SESSION_MODE_ENV}")
    parser.add_argument("--apdex-experience-kpm", choices=tuple(sorted(SUPPORTED_TIME_KPMS)), default=None, help=f"time KPM used for manual calibrated Apdex; or {UX_KPM_ENV}")
    parser.add_argument("--apdex-experience-satisfied-seconds", type=float, default=None, help=f"manual Satisfied/Tolerating threshold; or {UX_SATISFIED_ENV}")
    parser.add_argument("--apdex-experience-frustrated-seconds", type=float, default=None, help=f"manual Frustrated threshold; independent from 4T; or {UX_FRUSTRATED_ENV}")
    parser.add_argument("--apdex-experience-errors", action=argparse.BooleanOptionalAction, default=None, help=f"make qualifying errors Frustrated; default true when Synthetic User Experience Apdex is enabled; or {UX_ERRORS_ENV}")
    parser.add_argument("--apdex-experience-error-scope", choices=("navigation", "first-party", "all"), default=None, help=f"which request/JS errors can force Frustrated; or {UX_ERROR_SCOPE_ENV}")
    parser.add_argument("--apdex-experience-settle-seconds", type=float, default=None, help=f"bounded post-load observation window for late XHR/resources; default {DEFAULT_UX_SETTLE_SECONDS:g}s or {UX_SETTLE_ENV}")
    parser.add_argument("--apdex-experience-delay-seconds", type=float, default=None, help=f"minimum interval between sample starts; default {DEFAULT_UX_DELAY_SECONDS:g}s or {UX_DELAY_ENV}")
    parser.add_argument("--apdex-experience-concurrency", type=int, default=None, help=f"parallel workers 1-2; default {DEFAULT_UX_CONCURRENCY} or {UX_CONCURRENCY_ENV}")
    parser.add_argument("--apdex-dynatrace-import", action=argparse.BooleanOptionalAction, default=None, help=f"import load-action KPM/thresholds from Dynatrace configuration; or {DYNATRACE_IMPORT_ENV}")
    parser.add_argument("--dynatrace-base-url", default=None, help=f"Dynatrace environment URL, HTTPS only; or {DYNATRACE_BASE_URL_ENV}")
    parser.add_argument("--dynatrace-application-id", default=None, help=f"Dynatrace web application ID; or {DYNATRACE_APPLICATION_ID_ENV}")
    parser.add_argument("--apdex-dynatrace-config-json", default=None, help=f"offline exported Dynatrace application config JSON; preferred for reproducibility; or {DYNATRACE_CONFIG_JSON_ENV}")


def configured_experience(
    args: Any,
    env: Mapping[str, str] | None = None,
    *,
    standard_max_pages: int = 1,
    standard_delay_seconds: float = 1.0,
    standard_concurrency: int = 1,
) -> ExperienceApdexConfig:
    environment = env if env is not None else os.environ
    enabled = _bool(getattr(args, "apdex_experience", None), UX_ENABLED_ENV, False, environment)

    # Resolve the complete configuration even while the feature is disabled. The console
    # must be able to display, edit and persist coherent defaults/overrides before the
    # user enables the measurement. ExperienceApdexConfig.validate() intentionally
    # defers enablement-only requirements such as thresholds while enabled=False.
    samples = _positive_int(getattr(args, "apdex_experience_samples", None), UX_SAMPLES_ENV, DEFAULT_UX_SAMPLES, environment)
    max_attempts = _optional_positive_int(getattr(args, "apdex_experience_max_attempts", None), UX_MAX_ATTEMPTS_ENV, environment)
    if max_attempts is None:
        max_attempts = max(samples, int(math.ceil(samples * 1.25)))
    max_pages = _nonnegative_int(
        getattr(args, "apdex_experience_max_pages", None), UX_MAX_PAGES_ENV,
        standard_max_pages if standard_max_pages >= 0 else DEFAULT_UX_MAX_PAGES, environment,
    )
    mix_raw = _text(getattr(args, "apdex_experience_device_mix", None), UX_DEVICE_MIX_ENV, environment) or DEFAULT_UX_DEVICE_MIX
    mix = parse_device_mix(mix_raw)
    session = (_text(getattr(args, "apdex_experience_session_mode", None), UX_SESSION_MODE_ENV, environment) or DEFAULT_UX_SESSION_MODE).casefold()
    kpm = (_text(getattr(args, "apdex_experience_kpm", None), UX_KPM_ENV, environment) or DEFAULT_UX_KPM).upper()
    satisfied = _optional_positive_float(getattr(args, "apdex_experience_satisfied_seconds", None), UX_SATISFIED_ENV, environment)
    frustrated = _optional_positive_float(getattr(args, "apdex_experience_frustrated_seconds", None), UX_FRUSTRATED_ENV, environment)
    errors = _bool(getattr(args, "apdex_experience_errors", None), UX_ERRORS_ENV, True, environment)
    error_scope = (_text(getattr(args, "apdex_experience_error_scope", None), UX_ERROR_SCOPE_ENV, environment) or DEFAULT_UX_ERROR_SCOPE).casefold()
    settle = _positive_float(getattr(args, "apdex_experience_settle_seconds", None), UX_SETTLE_ENV, DEFAULT_UX_SETTLE_SECONDS, environment)
    delay = _nonnegative_float(getattr(args, "apdex_experience_delay_seconds", None), UX_DELAY_ENV, standard_delay_seconds, environment)
    concurrency = _positive_int(getattr(args, "apdex_experience_concurrency", None), UX_CONCURRENCY_ENV, standard_concurrency, environment)
    dynatrace_import = _bool(getattr(args, "apdex_dynatrace_import", None), DYNATRACE_IMPORT_ENV, False, environment)
    base_url = _text(getattr(args, "dynatrace_base_url", None), DYNATRACE_BASE_URL_ENV, environment)
    app_id = _text(getattr(args, "dynatrace_application_id", None), DYNATRACE_APPLICATION_ID_ENV, environment)
    config_json = _text(getattr(args, "apdex_dynatrace_config_json", None), DYNATRACE_CONFIG_JSON_ENV, environment)
    if config_json:
        dynatrace_import = True

    return ExperienceApdexConfig(
        enabled=enabled,
        target_samples_per_page=samples,
        max_attempts_per_page=max_attempts,
        max_pages=max_pages,
        device_mix=mix,
        session_mode=session,
        kpm=kpm,
        satisfied_threshold_seconds=satisfied,
        frustrated_threshold_seconds=frustrated,
        errors_affect_apdex=errors,
        error_scope=error_scope,
        settle_seconds=settle,
        delay_seconds=delay,
        concurrency=concurrency,
        dynatrace_import=dynatrace_import,
        dynatrace_base_url=base_url,
        dynatrace_application_id=app_id,
        dynatrace_config_json=config_json,
    ).validate()


def parse_device_mix(raw: str | None) -> tuple[tuple[str, float], ...]:
    if not raw or not raw.strip():
        return ()
    values: dict[str, float] = {}
    aliases = {"mobile": "MOBILE", "desktop": "DESKTOP", "tablet": "TABLET"}
    for part in raw.split(","):
        if "=" not in part:
            raise ValueError("device mix deve usar formato mobile=60,desktop=35,tablet=5")
        name_raw, value_raw = part.split("=", 1)
        key = name_raw.strip().casefold()
        if key not in aliases:
            raise ValueError(f"device mix contém device não suportado: {name_raw.strip()}")
        try:
            value = float(value_raw.strip())
        except ValueError as exc:
            raise ValueError(f"percentual inválido para {name_raw.strip()}") from exc
        if not math.isfinite(value) or value < 0:
            raise ValueError("percentuais do device mix devem ser finitos e >=0")
        values[aliases[key]] = value
    if abs(sum(values.values()) - 100.0) > 1e-6:
        raise ValueError("device mix deve somar exatamente 100")
    return tuple((name, values[name]) for name in ("MOBILE", "DESKTOP", "TABLET") if values.get(name, 0) > 0)


def validate_m25_env_value(name: str, raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("valor vazio")
    if name in {UX_ENABLED_ENV, UX_ERRORS_ENV, DYNATRACE_IMPORT_ENV}:
        _parse_bool(value, name)
    elif name in {UX_SAMPLES_ENV, UX_MAX_ATTEMPTS_ENV, UX_CONCURRENCY_ENV}:
        parsed = int(value)
        if parsed < 1 or (name == UX_CONCURRENCY_ENV and parsed > 2):
            raise ValueError("valor inteiro fora do domínio permitido")
    elif name == UX_MAX_PAGES_ENV:
        if int(value) < 0:
            raise ValueError("valor deve ser inteiro >=0")
    elif name == UX_DEVICE_MIX_ENV:
        parse_device_mix(value)
    elif name == UX_SESSION_MODE_ENV and value.casefold() not in {"cold", "warm"}:
        raise ValueError("session mode deve ser cold ou warm")
    elif name == UX_KPM_ENV and value.upper() not in SUPPORTED_TIME_KPMS:
        raise ValueError("KPM temporal não suportada pelo Synthetic User Experience Apdex")
    elif name == UX_ERROR_SCOPE_ENV and value.casefold() not in {"navigation", "first-party", "all"}:
        raise ValueError("error scope inválido")
    elif name in {UX_SATISFIED_ENV, UX_FRUSTRATED_ENV, UX_SETTLE_ENV}:
        if float(value) <= 0:
            raise ValueError("valor deve ser >0")
    elif name == UX_DELAY_ENV and float(value) < 0:
        raise ValueError("valor deve ser >=0")
    return value


def _text(cli: str | None, env_name: str, env: Mapping[str, str]) -> str | None:
    if cli is not None and str(cli).strip():
        return str(cli).strip()
    value = (env.get(env_name) or "").strip()
    return value or None


def _bool(cli: bool | None, env_name: str, default: bool, env: Mapping[str, str]) -> bool:
    if cli is not None:
        return bool(cli)
    raw = (env.get(env_name) or "").strip()
    return default if not raw else _parse_bool(raw, env_name)


def _parse_bool(raw: str, name: str) -> bool:
    value = raw.casefold()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} deve ser booleano")


def _optional_positive_int(cli: int | None, env_name: str, env: Mapping[str, str]) -> int | None:
    raw = cli if cli is not None else ((env.get(env_name) or "").strip() or None)
    if raw is None:
        return None
    value = int(raw)
    if value < 1:
        raise ValueError(f"{env_name} deve ser >=1")
    return value


def _positive_int(cli: int | None, env_name: str, default: int, env: Mapping[str, str]) -> int:
    value = _optional_positive_int(cli, env_name, env)
    return default if value is None else value


def _nonnegative_int(cli: int | None, env_name: str, default: int, env: Mapping[str, str]) -> int:
    raw = cli if cli is not None else ((env.get(env_name) or "").strip() or None)
    if raw is None:
        return default
    value = int(raw)
    if value < 0:
        raise ValueError(f"{env_name} deve ser >=0")
    return value


def _optional_positive_float(cli: float | None, env_name: str, env: Mapping[str, str]) -> float | None:
    raw = cli if cli is not None else ((env.get(env_name) or "").strip() or None)
    if raw is None:
        return None
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{env_name} deve ser número finito >0")
    return value


def _positive_float(cli: float | None, env_name: str, default: float, env: Mapping[str, str]) -> float:
    value = _optional_positive_float(cli, env_name, env)
    return default if value is None else value


def _nonnegative_float(cli: float | None, env_name: str, default: float, env: Mapping[str, str]) -> float:
    raw = cli if cli is not None else ((env.get(env_name) or "").strip() or None)
    if raw is None:
        return default
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{env_name} deve ser número finito >=0")
    return value
