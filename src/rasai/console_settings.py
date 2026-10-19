"""Persistent non-secret settings for the interactive console.

All user/operator configuration variables exposed by the console are preserved across
Save -> close -> reopen, except secrets. API keys, bearer tokens, passwords, session
secrets and credential-bearing DSNs are intentionally environment/session-only.
"""
from __future__ import annotations

from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass
from hashlib import sha256
import io
import math
import os
import stat
from tempfile import mkstemp
from pathlib import Path
from typing import Any, Mapping

from rasai.ai_canonical_orchestration import AI_CYCLE_DELAY_ENV, AI_MAX_CYCLES_ENV
from rasai.apdex_concurrency_policy import EXPERIENCE_MAX_CONCURRENCY, NAVIGATION_MAX_CONCURRENCY
from rasai.device_context import canonical_single_device_mix
from rasai.m25_cli import (
    DEFAULT_UX_CONSOLE_ERROR_CAPTURE,
    DEFAULT_UX_CONSOLE_ERRORS_AFFECT,
    DEFAULT_UX_DEVICE_MIX,
    DEFAULT_UX_FETCH_CAPTURE,
    DEFAULT_UX_JAVASCRIPT_ERROR_CAPTURE,
    DEFAULT_UX_JAVASCRIPT_ERRORS_AFFECT,
    DEFAULT_UX_MAX_ERROR_DETAILS,
    DEFAULT_UX_REQUEST_ERRORS_AFFECT,
    DEFAULT_UX_XHR_CAPTURE,
    DYNATRACE_APPLICATION_ID_ENV,
    DYNATRACE_BASE_URL_ENV,
    DYNATRACE_CONFIG_JSON_ENV,
    DYNATRACE_IMPORT_ENV,
    UX_CONCURRENCY_ENV,
    UX_DELAY_ENV,
    UX_DEVICE_MIX_ENV,
    UX_ENABLED_ENV,
    UX_ERRORS_ENV,
    UX_JAVASCRIPT_ERRORS_ENV,
    UX_REQUEST_ERRORS_ENV,
    UX_CONSOLE_ERRORS_ENV,
    UX_JAVASCRIPT_CAPTURE_ENV,
    UX_XHR_CAPTURE_ENV,
    UX_FETCH_CAPTURE_ENV,
    UX_CONSOLE_CAPTURE_ENV,
    UX_MAX_ERROR_DETAILS_ENV,
    UX_ERROR_SCOPE_ENV,
    UX_FRUSTRATED_ENV,
    UX_KPM_ENV,
    UX_ARCHITECTURE_ENV,
    UX_PROFILE_MODE_ENV,
    UX_MAX_ATTEMPTS_ENV,
    UX_MAX_PAGES_ENV,
    UX_SAMPLES_ENV,
    UX_SATISFIED_ENV,
    UX_SESSION_MODE_ENV,
    UX_SETTLE_ENV,
    parse_device_mix,
)
from rasai.provider_registry import get_provider_registration
from rasai.provider_runtime_policy import (
    AI_TIMEOUT_ENV,
    WEB_PERFORMANCE_TIMEOUT_ENV,
    provider_reasoning_env,
)
from rasai.time_contract import (
    DEFAULT_PRESENTATION_TIMEZONE,
    PRESENTATION_TIMEZONE_ENV,
    configured_presentation_timezone,
    validate_presentation_timezone,
)

CONSOLE_INI_ENV = "RASAI_CONSOLE_INI"
DEFAULT_CONSOLE_INI = "rasai-console.ini"
CONFIG_VERSION = "4"


@dataclass(frozen=True, slots=True)
class ConfigLoadResult:
    path: Path
    created: bool
    warnings: tuple[str, ...] = ()


def resolve_config_path(
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    environment = env if env is not None else os.environ
    configured = (environment.get(CONSOLE_INI_ENV) or "").strip()
    base = cwd if cwd is not None else Path.cwd()
    path = Path(configured).expanduser() if configured else base / DEFAULT_CONSOLE_INI
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _optional(value: Any) -> str:
    return "" if value is None else str(value)


def _gsc_nonsecret_names() -> frozenset[str]:
    """Bounded GSC non-secret keys subject to the consumer's real validators."""
    from rasai import gsc_scope, standards_gsc_policy
    return frozenset({
        gsc_scope.GSC_ENABLED_ENV,
        gsc_scope.GSC_SITE_URL_ENV,
        *standards_gsc_policy.environment_names(),
    })


def _canonical_gsc_value(name: str, raw: str) -> str:
    from rasai.console_provider_environment import _validate

    return _validate(name, raw)


def _known_nonsecret_environment_names() -> tuple[str, ...]:
    # Lazy import avoids a module-import cycle while making the console catalog the
    # single persistence allowlist. EnvironmentSpec.sensitive also protects DSNs and
    # other credentials whose names do not contain API_KEY/TOKEN/PASSWORD.
    from rasai.console_config import is_secret
    from rasai import console_provider_environment as facade

    specs = facade.refresh_specs()
    return tuple(
        spec.name
        for spec in specs
        if not spec.sensitive and not is_secret(spec.name)
    )


def _runtime_environment_projection(state: Any) -> dict[str, str]:
    values = {
        "RASAI_DEVICE_CONTEXT": str(state.device),
        AI_TIMEOUT_ENV: f"{float(state.ai_timeout):g}",
        AI_MAX_CYCLES_ENV: str(int(state.ai_max_cycles)),
        AI_CYCLE_DELAY_ENV: f"{float(state.ai_cycle_delay):g}",
        "RASAI_AI_CONTENT_REMEDIATION": _bool_text(bool(state.content_remediation)),
        "RASAI_AI_TECHNICAL_REMEDIATION": _bool_text(bool(getattr(state, "technical_remediation", False))),
        "RASAI_WEB_PERFORMANCE": _bool_text(bool(state.web_performance)),
        "RASAI_WEB_PERFORMANCE_MAX_PAGES": str(int(state.web_max_pages)),
        WEB_PERFORMANCE_TIMEOUT_ENV: f"{float(state.web_timeout):g}",
        "RASAI_WEB_PERFORMANCE_FIELD_SOURCE": str(state.field_source),
        "RASAI_LIGHTHOUSE_CATEGORIES": str(state.lighthouse_categories),
        PRESENTATION_TIMEZONE_ENV: configured_presentation_timezone(),
    }
    if hasattr(state, "synthetic_apdex"):
        values.update({
            "RASAI_SYNTHETIC_APDEX": _bool_text(bool(state.synthetic_apdex)),
            "RASAI_APDEX_SAMPLES_PER_CONTEXT": str(int(state.apdex_samples)),
            "RASAI_APDEX_MAX_ATTEMPTS_PER_CONTEXT": str(int(state.apdex_max_attempts)),
            "RASAI_APDEX_MAX_PAGES": str(int(state.apdex_max_pages)),
            "RASAI_APDEX_TIMEOUT_SECONDS": f"{float(state.apdex_timeout):g}",
            "RASAI_APDEX_DELAY_SECONDS": f"{float(state.apdex_delay):g}",
            "RASAI_APDEX_CONCURRENCY": str(int(state.apdex_concurrency)),
            UX_ENABLED_ENV: _bool_text(bool(getattr(state, "apdex_experience", False))),
            UX_SAMPLES_ENV: str(int(getattr(state, "apdex_experience_samples", 100))),
            UX_MAX_ATTEMPTS_ENV: str(int(getattr(state, "apdex_experience_max_attempts", 125))),
            UX_MAX_PAGES_ENV: str(int(getattr(state, "apdex_experience_max_pages", 1))),
            UX_DEVICE_MIX_ENV: canonical_single_device_mix(str(getattr(state, "device", "mobile"))),
            UX_SESSION_MODE_ENV: str(getattr(state, "apdex_experience_session_mode", "cold")),
            UX_KPM_ENV: str(getattr(state, "apdex_experience_kpm", "USER_ACTION_DURATION")),
            UX_ARCHITECTURE_ENV: str(getattr(state, "apdex_experience_architecture", "AUTO")),
            UX_PROFILE_MODE_ENV: str(getattr(state, "apdex_experience_profile_mode", "CUSTOM")),
            UX_ERRORS_ENV: _bool_text(bool(getattr(state, "apdex_experience_errors", True))),
            UX_JAVASCRIPT_ERRORS_ENV: _bool_text(bool(getattr(state, "apdex_experience_javascript_errors", DEFAULT_UX_JAVASCRIPT_ERRORS_AFFECT))),
            UX_REQUEST_ERRORS_ENV: _bool_text(bool(getattr(state, "apdex_experience_request_errors", DEFAULT_UX_REQUEST_ERRORS_AFFECT))),
            UX_CONSOLE_ERRORS_ENV: _bool_text(bool(getattr(state, "apdex_experience_console_errors", DEFAULT_UX_CONSOLE_ERRORS_AFFECT))),
            UX_JAVASCRIPT_CAPTURE_ENV: _bool_text(bool(getattr(state, "apdex_experience_javascript_capture", DEFAULT_UX_JAVASCRIPT_ERROR_CAPTURE))),
            UX_XHR_CAPTURE_ENV: _bool_text(bool(getattr(state, "apdex_experience_xhr_capture", DEFAULT_UX_XHR_CAPTURE))),
            UX_FETCH_CAPTURE_ENV: _bool_text(bool(getattr(state, "apdex_experience_fetch_capture", DEFAULT_UX_FETCH_CAPTURE))),
            UX_CONSOLE_CAPTURE_ENV: _bool_text(bool(getattr(state, "apdex_experience_console_capture", DEFAULT_UX_CONSOLE_ERROR_CAPTURE))),
            UX_MAX_ERROR_DETAILS_ENV: str(int(getattr(state, "apdex_experience_max_error_details", DEFAULT_UX_MAX_ERROR_DETAILS))),
            UX_ERROR_SCOPE_ENV: str(getattr(state, "apdex_experience_error_scope", "all")),
            UX_SETTLE_ENV: f"{float(getattr(state, 'apdex_experience_settle', 5.0)):g}",
            UX_DELAY_ENV: f"{float(getattr(state, 'apdex_experience_delay', 1.0)):g}",
            UX_CONCURRENCY_ENV: str(int(getattr(state, "apdex_experience_concurrency", 1))),
            DYNATRACE_IMPORT_ENV: _bool_text(bool(getattr(state, "apdex_dynatrace_import", False))),
        })
        # An explicitly cleared typed option must evict its former session
        # override; otherwise M23/M25 may consume stale values after the
        # operator disabled or cleared the corresponding setting.
        threshold = getattr(state, "apdex_threshold", None)
        satisfied = getattr(state, "apdex_experience_satisfied", None)
        frustrated = getattr(state, "apdex_experience_frustrated", None)
        values["RASAI_APDEX_THRESHOLD_SECONDS"] = (
            "" if threshold is None else f"{float(threshold):g}"
        )
        values[UX_SATISFIED_ENV] = (
            "" if satisfied is None else f"{float(satisfied):g}"
        )
        values[UX_FRUSTRATED_ENV] = (
            "" if frustrated is None else f"{float(frustrated):g}"
        )
        for name, raw in (
            (DYNATRACE_BASE_URL_ENV, getattr(state, "dynatrace_base_url", "")),
            (DYNATRACE_APPLICATION_ID_ENV, getattr(state, "dynatrace_application_id", "")),
            (DYNATRACE_CONFIG_JSON_ENV, getattr(state, "apdex_dynatrace_config_json", "")),
        ):
            values[name] = str(raw or "").strip()
    registration = get_provider_registration(str(state.ai_provider))
    if registration is not None:
        # Only the selected provider is owned by the current typed choice.
        # Preserve other providers and secrets during a provider change.
        values[registration.model_env] = str(
            getattr(state, "ai_model", None) or ""
        ).strip()
        variable = provider_reasoning_env(registration.provider_name)
        if variable:
            values[variable] = str(
                getattr(state, "ai_reasoning", None) or ""
            ).strip().upper()
    return values


def _persisted_environment_values(state: Any) -> dict[str, str]:
    allowed = set(_known_nonsecret_environment_names())
    projected = _runtime_environment_projection(state)
    result: dict[str, str] = {}
    for name in allowed:
        value = (os.environ.get(name) or projected.get(name) or "").strip()
        if value:
            result[name] = value
    return dict(sorted(result.items()))


def _state_values(state: Any) -> dict[str, dict[str, str]]:
    """Return only persistable, non-secret settings."""
    return {
        "console": {
            "config_version": CONFIG_VERSION,
            "input_mode": "url",
            "target": str(state.target),
            "project": str(state.project),
            "language": str(state.language),
            "market": str(state.market),
            "max_pages": str(int(state.max_pages)),
            "audits_root": str(state.audits_root),
            "device": str(state.device),
        },
        "presentation": {
            "timezone": configured_presentation_timezone(),
        },
        "ai": {
            "provider": str(state.ai_provider),
            "model": _optional(state.ai_model),
            "reasoning_effort": _optional(getattr(state, "ai_reasoning", None)),
            "timeout_seconds": f"{float(state.ai_timeout):g}",
            "max_cycles": str(int(state.ai_max_cycles)),
            "cycle_delay_seconds": f"{float(state.ai_cycle_delay):g}",
            "content_remediation": _bool_text(bool(state.content_remediation)),
            "technical_remediation": _bool_text(bool(getattr(state, "technical_remediation", False))),
        },
        "web_performance": {
            "enabled": _bool_text(bool(state.web_performance)),
            "max_pages": str(int(state.web_max_pages)),
            "timeout_seconds": f"{float(state.web_timeout):g}",
            "field_source": str(state.field_source),
            "lighthouse_categories": str(state.lighthouse_categories),
        },
        "synthetic_apdex": {
            "enabled": _bool_text(bool(state.synthetic_apdex)),
            "threshold_seconds": _optional(state.apdex_threshold),
            "samples_per_context": str(int(state.apdex_samples)),
            "max_attempts_per_context": str(int(state.apdex_max_attempts)),
            "max_pages": str(int(state.apdex_max_pages)),
            "timeout_seconds": f"{float(state.apdex_timeout):g}",
            "delay_seconds": f"{float(state.apdex_delay):g}",
            "concurrency": str(int(state.apdex_concurrency)),
        },
        "synthetic_apdex_experience": {
            "enabled": _bool_text(bool(getattr(state, "apdex_experience", False))),
            "samples_per_page": str(int(getattr(state, "apdex_experience_samples", 100))),
            "max_attempts_per_page": str(int(getattr(state, "apdex_experience_max_attempts", 125))),
            "max_pages": str(int(getattr(state, "apdex_experience_max_pages", 1))),
            "device_mix": canonical_single_device_mix(str(getattr(state, "device", "mobile"))),
            "session_mode": str(getattr(state, "apdex_experience_session_mode", "cold")),
            "kpm": str(getattr(state, "apdex_experience_kpm", "USER_ACTION_DURATION")),
            "architecture": str(getattr(state, "apdex_experience_architecture", "AUTO")),
            "profile_mode": str(getattr(state, "apdex_experience_profile_mode", "CUSTOM")),
            "satisfied_seconds": _optional(getattr(state, "apdex_experience_satisfied", None)),
            "frustrated_seconds": _optional(getattr(state, "apdex_experience_frustrated", None)),
            "errors_affect_apdex": _bool_text(bool(getattr(state, "apdex_experience_errors", True))),
            "javascript_errors_affect_apdex": _bool_text(bool(getattr(state, "apdex_experience_javascript_errors", DEFAULT_UX_JAVASCRIPT_ERRORS_AFFECT))),
            "request_errors_affect_apdex": _bool_text(bool(getattr(state, "apdex_experience_request_errors", DEFAULT_UX_REQUEST_ERRORS_AFFECT))),
            "console_errors_affect_apdex": _bool_text(bool(getattr(state, "apdex_experience_console_errors", DEFAULT_UX_CONSOLE_ERRORS_AFFECT))),
            "javascript_error_capture": _bool_text(bool(getattr(state, "apdex_experience_javascript_capture", DEFAULT_UX_JAVASCRIPT_ERROR_CAPTURE))),
            "xhr_capture": _bool_text(bool(getattr(state, "apdex_experience_xhr_capture", DEFAULT_UX_XHR_CAPTURE))),
            "fetch_capture": _bool_text(bool(getattr(state, "apdex_experience_fetch_capture", DEFAULT_UX_FETCH_CAPTURE))),
            "console_error_capture": _bool_text(bool(getattr(state, "apdex_experience_console_capture", DEFAULT_UX_CONSOLE_ERROR_CAPTURE))),
            "max_error_details": str(int(getattr(state, "apdex_experience_max_error_details", DEFAULT_UX_MAX_ERROR_DETAILS))),
            "error_scope": str(getattr(state, "apdex_experience_error_scope", "all")),
            "settle_seconds": f"{float(getattr(state, 'apdex_experience_settle', 5.0)):g}",
            "delay_seconds": f"{float(getattr(state, 'apdex_experience_delay', 1.0)):g}",
            "concurrency": str(int(getattr(state, "apdex_experience_concurrency", 1))),
            "dynatrace_import": _bool_text(bool(getattr(state, "apdex_dynatrace_import", False))),
            "dynatrace_base_url": str(getattr(state, "dynatrace_base_url", "")),
            "dynatrace_application_id": str(getattr(state, "dynatrace_application_id", "")),
            "dynatrace_config_json": str(getattr(state, "apdex_dynatrace_config_json", "")),
        },
    }


def configuration_fingerprint(state: Any) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    values = _state_values(state)
    sections = [(section, tuple(sorted(items.items()))) for section, items in sorted(values.items())]
    sections.append(("environment", tuple(sorted(_persisted_environment_values(state).items()))))
    return tuple(sections)


def _parser_for_state(state: Any) -> ConfigParser:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    for section, values in _state_values(state).items():
        parser[section] = values
    parser["environment"] = _persisted_environment_values(state)
    return parser


def _existing_ini_snapshot(destination: Path) -> tuple[tuple[int, ...], bytes] | None:
    """Read a bounded physical INI and fingerprint its identity without logging data."""
    try:
        info = destination.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("INI existente nao pode ser inspecionado com seguranca") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > 2_000_000:
        raise ValueError("INI existente nao pode ser substituido com seguranca")
    try:
        data = destination.read_bytes()
        after = destination.lstat()
    except OSError as exc:
        raise ValueError("INI existente nao pode ser lido com seguranca") from exc
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    before_identity = tuple(getattr(info, field) for field in fields)
    after_identity = tuple(getattr(after, field) for field in fields)
    if (
        not stat.S_ISREG(after.st_mode)
        or len(data) > 2_000_000
        or len(data) != info.st_size
        or before_identity != after_identity
    ):
        raise ValueError("INI existente mudou durante a leitura; preserve a origem")
    return (*after_identity, sha256(data).digest()), data


def _guard_existing_ini_before_save(
    destination: Path, state: Any
) -> tuple[object, ...] | None:
    """Reject lossy replacement of an operator INI, including unknown typed data.

    Only declared schema keys may be reserialized. Existing values are not
    copied to logs; other integrations must reconcile their schema explicitly.
    Return a physical+content fingerprint for an optimistic compare on commit.
    """
    snapshot = _existing_ini_snapshot(destination)
    if snapshot is None:
        return None
    identity, payload = snapshot
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_file(io.StringIO(payload.decode("utf-8-sig")))
    except (UnicodeError, ConfigError) as exc:
        raise ValueError("INI existente invalido; preserve a origem") from exc
    expected = _parser_for_state(state)
    if parser.defaults():
        raise ValueError("INI contem configuracoes DEFAULT nao persistiveis")
    for section, values in parser._sections.items():
        allowed = expected._sections.get(section)
        unexpected = set(values) - set(allowed or ())
        # First-run INIs may include this historical derived transport field.
        # An explicit device edit removes it from the current schema. Validate
        # the compatibility value before safely migrating the known key; all
        # other unrecognized keys and sections remain fail-closed.
        if section == "synthetic_apdex_experience" and "device_mix" in unexpected:
            try:
                compatibility_mix = values["device_mix"].strip()
                if compatibility_mix:
                    parse_device_mix(compatibility_mix)
            except ValueError as exc:
                raise ValueError(
                    "INI contem device_mix invalido; preserve a origem"
                ) from exc
            unexpected.remove("device_mix")
        if allowed is None or unexpected:
            raise ValueError(
                "INI contem configuracoes desconhecidas ou nao persistiveis; "
                "preserve uma copia e reconcilie antes de salvar"
            )
    return identity


def _reject_secret_bearing_dynatrace_json(value: Any) -> None:
    """Never serialize credential fields embedded in an otherwise public JSON."""
    import json

    raw = str(value or "").strip()
    if not raw:
        return
    # This operator-controlled field is persisted and projected repeatedly.
    # Bound JSON size/depth so a malicious value cannot exhaust console memory
    # or recursion during the credential walk.
    if len(raw) > 65536:
        raise ValueError("Dynatrace JSON excede limite de configuracao")
    try:
        parsed = json.loads(raw)
    except RecursionError as exc:
        raise ValueError("Dynatrace JSON excede profundidade segura") from exc
    except (ValueError, TypeError):
        # Preserve opaque values; the consumer performs structural validation.
        return
    secret_keys = frozenset({
        "token", "api_token", "access_token", "refresh_token", "bearer_token",
        "api_key", "apikey", "password", "passwd", "client_secret",
        "authorization", "credentials", "secret",
    })
    def has_secret(value: Any) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                canonical = "".join(char for char in str(key).casefold() if char.isalnum())
                if canonical in {"".join(char for char in candidate if char.isalnum()) for candidate in secret_keys} or has_secret(child):
                    return True
        elif isinstance(value, list):
            return any(has_secret(child) for child in value)
        return False
    try:
        contains_secret = has_secret(parsed)
    except RecursionError as exc:
        raise ValueError("Dynatrace JSON excede profundidade segura") from exc
    if contains_secret:
        raise ValueError("Dynatrace JSON contem campos de credencial nao persistiveis")


def save_console_config(state: Any, path: Path | None = None) -> Path:
    destination = path or resolve_config_path()
    _reject_secret_bearing_dynatrace_json(getattr(state, "apdex_dynatrace_config_json", ""))
    _reject_secret_bearing_dynatrace_json(os.environ.get(DYNATRACE_CONFIG_JSON_ENV))
    # Do not persist syntactically recognized GSC values that the real
    # consumer will refuse (or that hide credentials in a property URL).
    # This applies to direct save as well as edits through the guided menu.
    for name in _gsc_nonsecret_names():
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            continue
        try:
            _canonical_gsc_value(name, raw)
        except ValueError:
            raise ValueError(
                f"environment.{name}: valor GSC inválido; preservado INI original"
            ) from None
    initial_identity = _guard_existing_ini_before_save(destination, state)
    # Save is a logical transaction for both the INI and the in-process
    # projection. Persisting may fail due to disk/permissions/races; a failed
    # save must not advertise unsaved runtime values as successfully applied.
    projection = _runtime_environment_projection(state)
    previous_environment = {name: os.environ.get(name) for name in projection}
    try:
        sync_nonsecret_runtime_environment(state)
        destination.parent.mkdir(parents=True, exist_ok=True)
        parser = _parser_for_state(state)
        stream = io.StringIO()
        stream.write("; RASAi interactive console settings\n")
        stream.write("; All explicit non-secret overrides exposed by the console are persisted.\n")
        stream.write("; API keys, bearer tokens, passwords, session secrets and credential-bearing DSNs are NOT persisted.\n")
        stream.write("; Use environment variables, OS persistence or the SaaS secret mechanism for credentials.\n\n")
        parser.write(stream)
        descriptor, temporary = mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                output.write(stream.getvalue())
            current = _existing_ini_snapshot(destination)
            current_identity = current[0] if current is not None else None
            if current_identity != initial_identity:
                raise ValueError("INI de origem mudou durante o save; preserve a origem")
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    except Exception:
        for name, previous in previous_environment.items():
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        raise
    if hasattr(state, "config_path"):
        state.config_path = str(destination)
    if hasattr(state, "config_dirty"):
        state.config_dirty = False
    return destination


def _parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}: return True
    if normalized in {"0", "false", "no", "off"}: return False
    raise ValueError("use true/false")


def _positive_float(raw: str, *, label: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value <= 0: raise ValueError(f"{label}: use número finito > 0")
    return value


def _assign(state: Any, section: str, option: str, raw: str) -> None:
    key = (section, option)
    if key == ("console", "input_mode"):
        value = raw.strip().casefold()
        if value != "url":
            raise ValueError("novas AUDs aceitam somente input_mode=url")
        state.input_mode = "url"
    elif key == ("console", "target"): state.target = raw.strip()
    elif key == ("console", "project"): state.project = raw.strip()
    elif key == ("console", "language"): state.language = raw.strip() or state.language
    elif key == ("console", "market"): state.market = raw.strip() or state.market
    elif key == ("console", "max_pages"):
        value = int(raw)
        if value <= 0: raise ValueError("use inteiro > 0")
        state.max_pages = value
    elif key == ("console", "audits_root"): state.audits_root = raw.strip() or state.audits_root
    elif key == ("console", "device"):
        value = raw.strip().casefold()
        if value not in {"mobile", "desktop"}: raise ValueError("use mobile ou desktop")
        state.device, state.current_device = value, value.upper()
        if hasattr(state, "apdex_experience_device_mix"):
            from rasai.device_context import canonical_single_device_mix
            state.apdex_experience_device_mix = canonical_single_device_mix(value)
    elif key == ("presentation", "timezone"):
        os.environ[PRESENTATION_TIMEZONE_ENV] = validate_presentation_timezone(raw)
    elif key == ("ai", "provider"): state.ai_provider = raw.strip().casefold() or "none"
    elif key == ("ai", "model"): state.ai_model = raw.strip() or None
    elif key == ("ai", "reasoning_effort"): state.ai_reasoning = raw.strip().upper() or None
    elif key == ("ai", "timeout_seconds"): state.ai_timeout = _positive_float(raw, label="ai.timeout_seconds")
    elif key == ("ai", "max_cycles"):
        value = int(raw)
        if not 1 <= value <= 10: raise ValueError("ai.max_cycles: use inteiro entre 1 e 10")
        state.ai_max_cycles = value
    elif key == ("ai", "cycle_delay_seconds"):
        value = float(raw)
        if not math.isfinite(value) or not 0 <= value <= 300: raise ValueError("ai.cycle_delay_seconds: use número finito entre 0 e 300")
        state.ai_cycle_delay = value
    elif key == ("ai", "content_remediation"): state.content_remediation = _parse_bool(raw)
    elif key == ("ai", "technical_remediation"): state.technical_remediation = _parse_bool(raw)
    elif key == ("web_performance", "enabled"): state.web_performance = _parse_bool(raw)
    elif key == ("web_performance", "max_pages"):
        value = int(raw)
        if value < 0: raise ValueError("use inteiro >= 0")
        state.web_max_pages = value
    elif key == ("web_performance", "timeout_seconds"): state.web_timeout = _positive_float(raw, label="web_performance.timeout_seconds")
    elif key == ("web_performance", "field_source"):
        value = raw.strip().casefold()
        if value not in {"auto", "pagespeed", "crux", "none"}: raise ValueError("use auto, pagespeed, crux ou none")
        state.field_source = value
    elif key == ("web_performance", "lighthouse_categories"): state.lighthouse_categories = raw.strip() or state.lighthouse_categories
    elif key == ("synthetic_apdex", "enabled"): state.synthetic_apdex = _parse_bool(raw)
    elif key == ("synthetic_apdex", "threshold_seconds"): state.apdex_threshold = None if not raw.strip() else _positive_float(raw, label="synthetic_apdex.threshold_seconds")
    elif key == ("synthetic_apdex", "samples_per_context"):
        value = int(raw)
        if value < 1: raise ValueError("use inteiro >= 1")
        state.apdex_samples = value
    elif key == ("synthetic_apdex", "max_attempts_per_context"):
        value = int(raw)
        if value < 1: raise ValueError("use inteiro >= 1")
        state.apdex_max_attempts = value
    elif key == ("synthetic_apdex", "max_pages"):
        value = int(raw)
        if value < 0: raise ValueError("use inteiro >= 0")
        state.apdex_max_pages = value
    elif key == ("synthetic_apdex", "timeout_seconds"): state.apdex_timeout = _positive_float(raw, label="synthetic_apdex.timeout_seconds")
    elif key == ("synthetic_apdex", "delay_seconds"):
        value = float(raw)
        if not math.isfinite(value) or value < 0: raise ValueError("use número finito >= 0")
        state.apdex_delay = value
    elif key == ("synthetic_apdex", "concurrency"):
        value = int(raw)
        if value < 1 or value > NAVIGATION_MAX_CONCURRENCY:
            raise ValueError(f"use inteiro entre 1 e {NAVIGATION_MAX_CONCURRENCY}")
        state.apdex_concurrency = value
    elif key == ("synthetic_apdex_experience", "enabled"): state.apdex_experience = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "samples_per_page"):
        value = int(raw)
        if value < 1: raise ValueError("use inteiro >= 1")
        state.apdex_experience_samples = value
    elif key == ("synthetic_apdex_experience", "max_attempts_per_page"):
        value = int(raw)
        if value < 1: raise ValueError("use inteiro >= 1")
        state.apdex_experience_max_attempts = value
    elif key == ("synthetic_apdex_experience", "max_pages"):
        value = int(raw)
        if value < 0: raise ValueError("use inteiro >= 0")
        state.apdex_experience_max_pages = value
    elif key == ("synthetic_apdex_experience", "device_mix"):
        # Read old INI files without reactivating device_mix as an operator setting.
        if raw.strip():
            parse_device_mix(raw.strip())
        from rasai.device_context import canonical_single_device_mix
        state.apdex_experience_device_mix = canonical_single_device_mix(
            str(getattr(state, "device", "mobile"))
        )
    elif key == ("synthetic_apdex_experience", "session_mode"):
        value = raw.strip().casefold()
        if value not in {"cold", "warm"}: raise ValueError("use cold ou warm")
        state.apdex_experience_session_mode = value
    elif key == ("synthetic_apdex_experience", "architecture"):
        value = raw.strip().upper()
        if value not in {"AUTO", "STATIC_OR_SSR", "HYDRATED", "CSR_SPA", "MIXED", "UNKNOWN"}:
            raise ValueError("arquitetura Experience inválida")
        state.apdex_experience_architecture = value
    elif key == ("synthetic_apdex_experience", "profile_mode"):
        value = raw.strip().upper()
        if value not in {"CUSTOM", "DYNATRACE_GUIDED", "DYNATRACE_IMPORTED"}:
            raise ValueError("perfil Experience inválido")
        state.apdex_experience_profile_mode = value
    elif key == ("synthetic_apdex_experience", "kpm"):
        value = raw.strip().upper()
        if not value: raise ValueError("KPM não pode ser vazia")
        state.apdex_experience_kpm = value
    elif key == ("synthetic_apdex_experience", "satisfied_seconds"): state.apdex_experience_satisfied = None if not raw.strip() else _positive_float(raw, label="M25 satisfied_seconds")
    elif key == ("synthetic_apdex_experience", "frustrated_seconds"): state.apdex_experience_frustrated = None if not raw.strip() else _positive_float(raw, label="M25 frustrated_seconds")
    elif key == ("synthetic_apdex_experience", "errors_affect_apdex"): state.apdex_experience_errors = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "javascript_errors_affect_apdex"): state.apdex_experience_javascript_errors = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "request_errors_affect_apdex"): state.apdex_experience_request_errors = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "console_errors_affect_apdex"): state.apdex_experience_console_errors = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "javascript_error_capture"): state.apdex_experience_javascript_capture = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "xhr_capture"): state.apdex_experience_xhr_capture = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "fetch_capture"): state.apdex_experience_fetch_capture = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "console_error_capture"): state.apdex_experience_console_capture = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "max_error_details"):
        value = int(raw)
        if value < 0 or value > 50: raise ValueError("use inteiro entre 0 e 50")
        state.apdex_experience_max_error_details = value
    elif key == ("synthetic_apdex_experience", "error_scope"):
        value = raw.strip().casefold()
        if value not in {"navigation", "first-party", "all"}: raise ValueError("use navigation, first-party ou all")
        state.apdex_experience_error_scope = value
    elif key == ("synthetic_apdex_experience", "settle_seconds"): state.apdex_experience_settle = _positive_float(raw, label="M25 settle_seconds")
    elif key == ("synthetic_apdex_experience", "delay_seconds"):
        value = float(raw)
        if not math.isfinite(value) or value < 0: raise ValueError("use número finito >= 0")
        state.apdex_experience_delay = value
    elif key == ("synthetic_apdex_experience", "concurrency"):
        value = int(raw)
        if value < 1 or value > EXPERIENCE_MAX_CONCURRENCY:
            raise ValueError(f"use inteiro entre 1 e {EXPERIENCE_MAX_CONCURRENCY}")
        state.apdex_experience_concurrency = value
    elif key == ("synthetic_apdex_experience", "dynatrace_import"): state.apdex_dynatrace_import = _parse_bool(raw)
    elif key == ("synthetic_apdex_experience", "dynatrace_base_url"): state.dynatrace_base_url = raw.strip()
    elif key == ("synthetic_apdex_experience", "dynatrace_application_id"): state.dynatrace_application_id = raw.strip()
    elif key == ("synthetic_apdex_experience", "dynatrace_config_json"):
        _reject_secret_bearing_dynatrace_json(raw)
        state.apdex_dynatrace_config_json = raw.strip()


def load_console_config(state: Any, path: Path | None = None) -> ConfigLoadResult:
    source = Path(path) if path is not None else resolve_config_path()
    # A dangling symlink does not satisfy exists(); never interpret it as a
    # missing file that should be created. Console boot must fail closed.
    if source.is_symlink():
        return ConfigLoadResult(source, False, ("INI simbólico não autorizado",))
    warnings: list[str] = []
    external_timezone = (os.environ.get(PRESENTATION_TIMEZONE_ENV) or "").strip()
    if external_timezone:
        try:
            validate_presentation_timezone(external_timezone)
        except ValueError as exc:
            warnings.append(f"{PRESENTATION_TIMEZONE_ENV}: {exc}; usando INI/default")
            os.environ.pop(PRESENTATION_TIMEZONE_ENV, None)
            external_timezone = ""
    if not source.exists():
        save_console_config(state, source)
        return ConfigLoadResult(source, True, tuple(warnings))
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        # Verify source identity and bounded bytes before applying any settings.
        # This is the same non-writing guard used by the save path: never follow
        # operator INI symlinks or trust an oversized/concurrently changed file.
        snapshot = _existing_ini_snapshot(source)
        if snapshot is None:
            return ConfigLoadResult(source, False, ("INI ausente durante a leitura",))
        # Decode the verified bytes (not a second open of a potentially changed
        # path). Windows UTF-8 BOM remains supported and source bytes untouched.
        parser.read_string(snapshot[1].decode("utf-8-sig"))
    except (ValueError, OSError, UnicodeError, ConfigError) as exc:
        # An operator INI can be truncated or contain duplicate entries.
        # Keep state and environment unchanged rather than abort console startup
        # or partially applying an invalid document. Do not echo source values.
        return ConfigLoadResult(source, False, (f"não foi possível ler {source}: {type(exc).__name__}",))
    if parser.has_section("environment"):
        allowed = set(_known_nonsecret_environment_names())
        # ConfigParser.items() silently merges [DEFAULT]. Only physical keys
        # placed in [environment] are operator environment assignments.
        for name, raw in parser._sections["environment"].items():
            if name not in allowed:
                warnings.append(f"environment.{name}: variável não reconhecida ou não persistível")
                continue
            if name == DYNATRACE_CONFIG_JSON_ENV:
                try:
                    _reject_secret_bearing_dynatrace_json(raw)
                except ValueError:
                    warnings.append("Dynatrace JSON nao persistivel")
                    continue
            # A deliberately empty session override is still an override.
            # Do not revive an older INI value on console startup.
            if name not in os.environ and raw.strip():
                if name in _gsc_nonsecret_names():
                    try:
                        canonical = _canonical_gsc_value(name, raw)
                    except ValueError:
                        warnings.append(
                            f"environment.{name}: valor GSC inválido; conteúdo omitido"
                        )
                        continue
                    os.environ[name] = canonical
                else:
                    os.environ[name] = raw.strip()
    # Optional console adapters may own additional legitimate sections that
    # are loaded after this base adapter. Do not warn about every such section:
    # that incorrectly marks valid fresh-process round trips as broken.
    # Warn only if an unowned section has an explicitly secret-like key.
    from rasai.console_config import is_secret
    owned_sections = set(_state_values(state)) | {"environment"}
    for section in parser.sections():
        if section not in owned_sections and any(
            is_secret(option) for option in parser._sections[section]
        ):
            warnings.append(f"{section}: campo sensível em seção não reconhecida")
    for section, values in _state_values(state).items():
        if not parser.has_section(section):
            continue
        # Unknown options in owned typed sections are not consumed and must
        # not be reported as successfully restored or silently dropped.
        for option in parser._sections[section]:
            if option not in values:
                warnings.append(f"{section}.{option}: opção não reconhecida ou não persistível")
        for option in values:
            # has_option() inherits [DEFAULT], which must not overwrite
            # typed state without an explicit assignment in this section.
            if option == "config_version" or option not in parser._sections[section]: continue
            if section == "presentation" and option == "timezone" and external_timezone:
                continue
            raw = parser.get(section, option, raw=True)
            try:
                _assign(state, section, option, raw)
            except (ValueError, TypeError, OverflowError):
                # The exception text of int/float parsers can contain the
                # operator's literal INI value. Keep only schema coordinates.
                warnings.append(f"{section}.{option}: valor inválido; conteúdo omitido")
    if not (os.environ.get(PRESENTATION_TIMEZONE_ENV) or "").strip():
        os.environ[PRESENTATION_TIMEZONE_ENV] = DEFAULT_PRESENTATION_TIMEZONE
    if hasattr(state, "config_path"):
        state.config_path = str(source)
    # The loaded session cannot be represented as "saved" after an invalid
    # typed value: an operator must explicitly inspect and save corrections.
    if hasattr(state, "config_dirty"):
        # Any rejected persisted input requires operator reconciliation before
        # the UI can truthfully claim the current settings are fully restored.
        # Do not treat benign explanatory notices as a failed restore.
        typed_prefixes = tuple(f"{section}." for section in _state_values(state))
        state.config_dirty = any(
            note.startswith(typed_prefixes)
            or note.startswith("environment.")
            or note.endswith(": campo sensível em seção não reconhecida")
            or note == "Dynatrace JSON nao persistivel"
            for note in warnings
        )
    return ConfigLoadResult(source, False, tuple(warnings))


def sync_nonsecret_runtime_environment(state: Any) -> None:
    """Project all effective non-secret console settings into adapter environment."""
    projection = _runtime_environment_projection(state)
    # The runtime projection is as sensitive as INI save/load: never export
    # nested credential fields from an operator-supplied JSON snapshot.
    _reject_secret_bearing_dynatrace_json(projection.get(DYNATRACE_CONFIG_JSON_ENV))
    for name, value in projection.items():
        if value: os.environ[name] = value
        else: os.environ.pop(name, None)
