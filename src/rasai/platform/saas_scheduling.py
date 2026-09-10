"""SaaS scheduling recurrence and URL-scope contracts.

This module is intentionally independent from FastAPI and from the audit engine. It
normalizes user-friendly schedule configuration into a deterministic calendar model,
resolves occurrences in an explicit IANA timezone and validates that scheduled URLs
remain inside one RASAi Property.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MIN_INTERVAL_MINUTES = 60
MAX_NEXT_OCCURRENCES = 100
MAX_SCHEDULE_URLS = 5000
_ALLOWED_OVERLAP = {"SKIP", "QUEUE"}


def normalize_timezone(value: str) -> str:
    name = str(value or "").strip()
    if not name:
        raise ValueError("schedule timezone is required")
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown IANA timezone: {name}") from exc
    return name


def normalize_overlap_policy(value: str | None) -> str:
    policy = str(value or "SKIP").strip().upper()
    if policy not in _ALLOWED_OVERLAP:
        raise ValueError("overlap_policy must be SKIP or QUEUE")
    return policy


def _hhmm(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    try:
        parsed = time.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} must use HH:MM") from exc
    if parsed.second or parsed.microsecond:
        raise ValueError(f"{field} must use minute precision HH:MM")
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def normalize_recurrence(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize the flexible recurrence contract used by Web/API scheduling.

    ``times`` represents fixed local clock times. ``every_minutes`` represents a
    repeated cadence inside the optional local ``window_start``/``window_end``.
    Weekday and month-day filters are intersections when both are provided. The
    special ``last_day`` flag adds the last calendar day as an allowed month day.
    """
    if not isinstance(value, dict):
        raise ValueError("recurrence must be an object")
    times = sorted(set(_hhmm(item, field="recurrence.times") for item in value.get("times", []) or []))
    raw_interval = value.get("every_minutes")
    every_minutes: int | None = None
    if raw_interval is not None:
        if isinstance(raw_interval, bool) or not isinstance(raw_interval, int):
            raise ValueError("recurrence.every_minutes must be an integer")
        if raw_interval < MIN_INTERVAL_MINUTES or raw_interval > 31 * 24 * 60:
            raise ValueError(f"recurrence.every_minutes must be between {MIN_INTERVAL_MINUTES} and 44640")
        every_minutes = raw_interval
    window_start = _hhmm(value.get("window_start", "00:00"), field="recurrence.window_start")
    window_end = _hhmm(value.get("window_end", "23:59"), field="recurrence.window_end")
    if window_end < window_start:
        raise ValueError("recurrence window cannot cross midnight; use explicit times on both days")

    weekdays = sorted(set(int(item) for item in (value.get("weekdays") or [])))
    if any(item < 1 or item > 7 for item in weekdays):
        raise ValueError("recurrence.weekdays must use ISO weekday numbers 1..7")
    month_days = sorted(set(int(item) for item in (value.get("month_days") or [])))
    if any(item < 1 or item > 31 for item in month_days):
        raise ValueError("recurrence.month_days must contain values 1..31")
    last_day = bool(value.get("last_day", False))

    if not times and every_minutes is None:
        raise ValueError("recurrence requires fixed times or every_minutes")
    unknown = sorted(
        set(value)
        - {"times", "every_minutes", "window_start", "window_end", "weekdays", "month_days", "last_day"}
    )
    if unknown:
        raise ValueError("unsupported recurrence field(s): " + ", ".join(unknown))
    return {
        "version": "CALENDAR_V1",
        "times": times,
        "every_minutes": every_minutes,
        "window_start": window_start,
        "window_end": window_end,
        "weekdays": weekdays,
        "month_days": month_days,
        "last_day": last_day,
    }


def _date_allowed(day: date, recurrence: dict[str, Any]) -> bool:
    weekdays = recurrence.get("weekdays") or []
    if weekdays and day.isoweekday() not in weekdays:
        return False
    month_days = recurrence.get("month_days") or []
    last_day = bool(recurrence.get("last_day"))
    if month_days or last_day:
        allowed = day.day in month_days
        if last_day and day.day == monthrange(day.year, day.month)[1]:
            allowed = True
        if not allowed:
            return False
    return True


def _clock_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":", 1))
    return hour * 60 + minute


def _daily_times(recurrence: dict[str, Any]) -> tuple[str, ...]:
    values = set(str(item) for item in recurrence.get("times") or [])
    interval = recurrence.get("every_minutes")
    if interval is not None:
        start = _clock_minutes(str(recurrence["window_start"]))
        end = _clock_minutes(str(recurrence["window_end"]))
        cursor = start
        while cursor <= end:
            values.add(f"{cursor // 60:02d}:{cursor % 60:02d}")
            cursor += int(interval)
    return tuple(sorted(values))


def _local_candidate(day: date, hhmm: str, zone: ZoneInfo) -> datetime | None:
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone, fold=0)
    # A UTC round-trip rejects nonexistent DST wall times. Ambiguous times use
    # fold=0 deterministically, preventing a duplicate occurrence during fallback.
    roundtrip = local.astimezone(UTC).astimezone(zone)
    if (roundtrip.date(), roundtrip.hour, roundtrip.minute) != (day, hour, minute):
        return None
    return local


def next_occurrences(
    recurrence: dict[str, Any],
    timezone: str,
    *,
    after: str | datetime | None = None,
    count: int = 1,
) -> tuple[str, ...]:
    normalized = normalize_recurrence({key: value for key, value in recurrence.items() if key != "version"})
    zone_name = normalize_timezone(timezone)
    if count < 1 or count > MAX_NEXT_OCCURRENCES:
        raise ValueError(f"count must be between 1 and {MAX_NEXT_OCCURRENCES}")
    zone = ZoneInfo(zone_name)
    if after is None:
        cursor_utc = datetime.now(UTC)
    elif isinstance(after, datetime):
        cursor_utc = after if after.tzinfo is not None else after.replace(tzinfo=UTC)
        cursor_utc = cursor_utc.astimezone(UTC)
    else:
        parsed = datetime.fromisoformat(str(after).replace("Z", "+00:00"))
        cursor_utc = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        cursor_utc = cursor_utc.astimezone(UTC)

    local_start = cursor_utc.astimezone(zone).date()
    clocks = _daily_times(normalized)
    found: list[str] = []
    for offset in range(0, 370 * 3):
        day = local_start + timedelta(days=offset)
        if not _date_allowed(day, normalized):
            continue
        for hhmm in clocks:
            candidate = _local_candidate(day, hhmm, zone)
            if candidate is None:
                continue
            candidate_utc = candidate.astimezone(UTC)
            if candidate_utc <= cursor_utc:
                continue
            found.append(candidate_utc.isoformat())
            if len(found) >= count:
                return tuple(found)
    raise ValueError("recurrence produced no occurrence within the supported three-year horizon")


def normalize_scheduled_urls(
    urls: Iterable[str],
    *,
    property_hostname: str,
    environment_origin: str,
) -> tuple[str, ...]:
    hostname = property_hostname.strip().lower().rstrip(".")
    env = urlsplit(environment_origin)
    if not hostname or not env.hostname:
        raise ValueError("invalid Property/Environment URL scope")
    normalized: list[str] = []
    for raw in urls:
        text = str(raw or "").strip()
        if not text:
            continue
        if "://" not in text:
            text = environment_origin.rstrip("/") + "/" + text.lstrip("/")
        parts = urlsplit(text)
        candidate_host = (parts.hostname or "").lower().rstrip(".")
        if parts.scheme.lower() not in {"http", "https"} or not candidate_host:
            raise ValueError(f"scheduled URL must be absolute HTTP(S): {raw}")
        if candidate_host != hostname:
            raise ValueError(f"scheduled URL is outside Property hostname {hostname}: {raw}")
        port = parts.port
        netloc = candidate_host
        if port and not ((parts.scheme.lower() == "http" and port == 80) or (parts.scheme.lower() == "https" and port == 443)):
            netloc = f"{candidate_host}:{port}"
        path = parts.path or "/"
        normalized.append(urlunsplit((parts.scheme.lower(), netloc, path, parts.query, "")))
    deduped = tuple(dict.fromkeys(normalized))
    if not deduped:
        deduped = (environment_origin.rstrip("/") + "/",)
    if len(deduped) > MAX_SCHEDULE_URLS:
        raise ValueError(f"a schedule can contain at most {MAX_SCHEDULE_URLS} URLs")
    return deduped
