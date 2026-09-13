"""Configuration contract for read-only external observability integrations.

These settings control providers that enrich RASAi with observed outcomes or public
historical evidence. They never redefine SARI-001/SCORE-GEO-004 and never carry
secret values in durable audit/configuration payloads.
"""
from __future__ import annotations

from typing import Iterable

CRUX_HISTORY_ENABLED_ENV = "RASAI_CRUX_HISTORY_ENABLED"

CLARITY_ENABLED_ENV = "RASAI_CLARITY_ENABLED"
CLARITY_TOKEN_ENV = "RASAI_CLARITY_API_TOKEN"
CLARITY_DAYS_ENV = "RASAI_CLARITY_DAYS"
CLARITY_DIMENSIONS_ENV = "RASAI_CLARITY_DIMENSIONS"

COMMON_CRAWL_ENABLED_ENV = "RASAI_COMMON_CRAWL_ENABLED"
COMMON_CRAWL_MAX_URLS_ENV = "RASAI_COMMON_CRAWL_MAX_URLS"
COMMON_CRAWL_INDEX_COUNT_ENV = "RASAI_COMMON_CRAWL_INDEX_COUNT"

DEFAULT_CLARITY_DAYS = 1
DEFAULT_CLARITY_DIMENSIONS = ("URL", "Device")
DEFAULT_COMMON_CRAWL_MAX_URLS = 3
DEFAULT_COMMON_CRAWL_INDEX_COUNT = 2

_CLARITY_DIMENSIONS = {
    "Browser",
    "Device",
    "Country/Region",
    "OS",
    "Source",
    "Medium",
    "Campaign",
    "Channel",
    "URL",
}


def clarity_days(raw: str | None) -> int:
    if raw is None or not str(raw).strip():
        return DEFAULT_CLARITY_DAYS
    value = int(str(raw).strip())
    if value not in {1, 2, 3}:
        raise ValueError(f"{CLARITY_DAYS_ENV}: use 1, 2 ou 3")
    return value


def clarity_dimensions(raw: str | None) -> tuple[str, ...]:
    if raw is None or not str(raw).strip():
        return DEFAULT_CLARITY_DIMENSIONS
    values = tuple(item.strip() for item in str(raw).split(",") if item.strip())
    if not values:
        return DEFAULT_CLARITY_DIMENSIONS
    if len(values) > 3:
        raise ValueError(f"{CLARITY_DIMENSIONS_ENV}: no máximo 3 dimensões")
    normalized: list[str] = []
    by_fold = {item.casefold(): item for item in _CLARITY_DIMENSIONS}
    for value in values:
        canonical = by_fold.get(value.casefold())
        if canonical is None:
            raise ValueError(
                f"{CLARITY_DIMENSIONS_ENV}: dimensão inválida {value!r}; use "
                + ", ".join(sorted(_CLARITY_DIMENSIONS))
            )
        if canonical not in normalized:
            normalized.append(canonical)
    if "URL" not in normalized:
        raise ValueError(
            f"{CLARITY_DIMENSIONS_ENV}: inclua URL para que o RASAi possa restringir os dados ao domínio auditado"
        )
    return tuple(normalized)


def common_crawl_max_urls(raw: str | None) -> int:
    return _bounded_int(raw, DEFAULT_COMMON_CRAWL_MAX_URLS, minimum=0, maximum=25, name=COMMON_CRAWL_MAX_URLS_ENV)


def common_crawl_index_count(raw: str | None) -> int:
    return _bounded_int(raw, DEFAULT_COMMON_CRAWL_INDEX_COUNT, minimum=1, maximum=6, name=COMMON_CRAWL_INDEX_COUNT_ENV)


def dimensions_csv(values: Iterable[str]) -> str:
    return ",".join(str(value).strip() for value in values if str(value).strip())


def _bounded_int(raw: str | None, default: int, *, minimum: int, maximum: int, name: str) -> int:
    if raw is None or not str(raw).strip():
        return default
    value = int(str(raw).strip())
    if value < minimum or value > maximum:
        raise ValueError(f"{name}: use inteiro entre {minimum} e {maximum}")
    return value
