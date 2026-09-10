"""Canonical timestamp and report-presentation timezone contract for RASAi.

Internal timestamps are normalized to timezone-aware UTC. User-facing HTML reports
use an explicit IANA timezone, defaulting to ``America/Sao_Paulo``. Presentation
conversion never mutates persisted source evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
