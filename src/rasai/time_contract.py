"""Canonical timestamp and report-presentation timezone contract for RASAi.

Internal timestamps are normalized to timezone-aware UTC. User-facing HTML reports
use an explicit IANA timezone, defaulting to ``America/Sao_Paulo``. Presentation
conversion never mutates persisted source evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from math import isfinite
import os
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
DEFAULT_PRESENTATION_TIMEZONE = "America/Sao_Paulo"
PRESENTATION_TIMEZONE_ENV = "RASAI_PRESENTATION_TIMEZONE"

_AWARE_ISO_TIMESTAMP_PATTERN = (
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
)
_AWARE_ISO_TIMESTAMP_RE = re.compile(
    rf"(?<!\d)(?P<value>{_AWARE_ISO_TIMESTAMP_PATTERN})(?!\d)"
)
_FULL_AWARE_ISO_TIMESTAMP_RE = re.compile(rf"^{_AWARE_ISO_TIMESTAMP_PATTERN}$")
_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)", flags=re.DOTALL)


def utc_now() -> datetime:
    """Return the current instant as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Return the current instant in canonical ISO-8601 UTC form."""
    return utc_now().isoformat()


def to_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC; legacy naive values are interpreted as UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and normalize it to UTC.

    ``Z`` and explicit offsets are supported. Naive timestamps are accepted only
    as a legacy compatibility path and are interpreted as UTC, never as host-local
    time.
    """
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return to_utc(parsed)


def canonical_utc_timestamp(value: str | datetime) -> str:
    """Return one timestamp as an explicit ``+00:00`` ISO-8601 value."""
    instant = parse_timestamp(value) if isinstance(value, str) else to_utc(value)
    return instant.isoformat()


def normalize_timestamp_values(value: Any) -> Any:
    """Recursively normalize aware ISO timestamp strings to UTC.

    This is intended for derivative manifests/config payloads. It deliberately
    leaves date-only values, free text and naive datetime strings unchanged.
    """
    if isinstance(value, dict):
        return {key: normalize_timestamp_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_timestamp_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_timestamp_values(item) for item in value)
    if isinstance(value, str) and _FULL_AWARE_ISO_TIMESTAMP_RE.fullmatch(value.strip()):
        return canonical_utc_timestamp(value)
    return value


def validate_presentation_timezone(value: str) -> str:
    """Validate and normalize one IANA timezone identifier."""
    candidate = str(value).strip()
    if not candidate:
        raise ValueError("timezone vazio; use um identificador IANA como America/Sao_Paulo")
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(
            f"timezone IANA inválido: {candidate}; exemplo válido: America/Sao_Paulo"
        ) from exc
    return candidate


def configured_presentation_timezone(env: Mapping[str, str] | None = None) -> str:
    """Return the effective presentation timezone from environment or product default."""
    environment = env if env is not None else os.environ
    raw = (environment.get(PRESENTATION_TIMEZONE_ENV) or "").strip()
    return validate_presentation_timezone(raw or DEFAULT_PRESENTATION_TIMEZONE)



def presentation_timezone_for_audit(configuration: Mapping[str, Any] | None) -> tuple[str, str]:
    """Use only the audit's persisted configuration, never the current host/env.

    Explicit product default is a documented fallback, *not* evidence that the
    historic operator selected this zone. The second value is provenance.
    """
    settings = configuration.get("settings", {}) if isinstance(configuration, Mapping) else {}
    settings = settings if isinstance(settings, Mapping) else {}
    presentation = settings.get("presentation", {})
    presentation = presentation if isinstance(presentation, Mapping) else {}
    environment = settings.get("environment", {})
    environment = environment if isinstance(environment, Mapping) else {}
    direct = presentation.get("timezone")
    env = environment.get(PRESENTATION_TIMEZONE_ENV)
    raw = direct if direct is not None else env
    if not isinstance(raw, str) or not raw.strip():
        return DEFAULT_PRESENTATION_TIMEZONE, "HISTORICAL_TIMEZONE_NOT_PERSISTED_ND_DEFAULT_USED"
    try:
        zone = validate_presentation_timezone(raw)
    except ValueError:
        return DEFAULT_PRESENTATION_TIMEZONE, "INVALID_PERSISTED_TIMEZONE_ND_DEFAULT_USED"
    if isinstance(direct, str) and isinstance(env, str) and direct.strip() != env.strip():
        return zone, "PERSISTED_TIMEZONE_CONFLICT_PREFERRED_PRESENTATION"
    return zone, ("settings.presentation.timezone" if direct is not None
                  else "settings.environment." + PRESENTATION_TIMEZONE_ENV)


def timezone_offset_label(
    timezone_name: str,
    *,
    instant: datetime | None = None,
) -> str:
    """Return the current UTC offset label for an IANA timezone, e.g. ``UTC-03:00``."""
    zone_name = validate_presentation_timezone(timezone_name)
    reference = to_utc(instant or utc_now()).astimezone(ZoneInfo(zone_name))
    offset = reference.utcoffset()
    total_minutes = int((offset.total_seconds() if offset else 0) // 60)
    sign = "+" if total_minutes >= 0 else "-"
    absolute = abs(total_minutes)
    hours, minutes = divmod(absolute, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _resolve_presentation_timezone(timezone_name: str | None) -> str:
    return (
        configured_presentation_timezone()
        if timezone_name is None
        else validate_presentation_timezone(timezone_name)
    )


def format_presentation_timestamp(
    value: str | datetime,
    *,
    timezone_name: str | None = None,
) -> str:
    """Render a timestamp in the selected user-facing IANA timezone."""
    instant = parse_timestamp(value) if isinstance(value, str) else to_utc(value)
    resolved = _resolve_presentation_timezone(timezone_name)
    local = instant.astimezone(ZoneInfo(resolved))
    return f"{local.strftime('%d/%m/%Y %H:%M:%S')} ({resolved})"


def localize_visible_timestamps(
    text: str,
    *,
    timezone_name: str | None = None,
) -> str:
    """Convert aware ISO timestamps embedded in visible report text.

    Date-only values are deliberately not changed because a calendar date has no
    timezone semantics without an associated instant.
    """
    resolved = _resolve_presentation_timezone(timezone_name)

    def replace(match: re.Match[str]) -> str:
        return format_presentation_timestamp(match.group("value"), timezone_name=resolved)

    return _AWARE_ISO_TIMESTAMP_RE.sub(replace, text)


def localize_html_timestamps(
    html: str,
    *,
    timezone_name: str | None = None,
) -> str:
    """Localize visible HTML timestamps without changing tags or technical blocks."""
    resolved = _resolve_presentation_timezone(timezone_name)
    parts = _TAG_SPLIT_RE.split(html)
    blocked_depth = 0
    output: list[str] = []
    for part in parts:
        if part.startswith("<"):
            lowered = part.lower()
            if re.match(r"<(script|style|pre|code)\b", lowered):
                blocked_depth += 1
            elif re.match(r"</(script|style|pre|code)\b", lowered):
                blocked_depth = max(0, blocked_depth - 1)
            output.append(part)
            continue
        if blocked_depth:
            output.append(part)
            continue
        output.append(localize_visible_timestamps(part, timezone_name=resolved))
    return "".join(output)


def format_presentation_http_date(value: str, *, timezone_name: str | None = None) -> str:
    """Format a typed RFC 7231 HTTP Date; preserve the raw header in its caller."""
    if not isinstance(value, str) or not 10 <= len(value) <= 80:
        raise ValueError("HTTP-date ausente ou fora da política")
    try:
        instant = parsedate_to_datetime(value)
    except (ValueError, TypeError, IndexError) as exc:
        raise ValueError("HTTP-date inválido") from exc
    if instant.tzinfo is None or instant.utcoffset() != UTC.utcoffset(None):
        raise ValueError("HTTP-date sem prova UTC/GMT")
    return format_presentation_timestamp(instant, timezone_name=timezone_name)


def format_presentation_unix_epoch(
    value: int | float, *, unit: str, timezone_name: str | None = None
) -> str:
    """Render a typed Unix timestamp with mandatory seconds/milliseconds unit."""
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError("epoch inválido")
    if unit not in {"seconds", "milliseconds"}:
        raise ValueError("unidade epoch deve ser seconds ou milliseconds")
    try:
        instant = datetime.fromtimestamp(value if unit == "seconds" else value / 1000, tz=UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("epoch fora do intervalo") from exc
    return format_presentation_timestamp(instant, timezone_name=timezone_name)
