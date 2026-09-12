"""Bounded, non-secret policy for automatic Google Search Console collection."""
from __future__ import annotations

GSC_SEARCH_ANALYTICS_DAYS_ENV = "RASAI_GSC_SEARCH_ANALYTICS_DAYS"
GSC_SEARCH_MAX_ROWS_ENV = "RASAI_GSC_SEARCH_MAX_ROWS"
GSC_FINAL_DATA_LAG_DAYS_ENV = "RASAI_GSC_FINAL_DATA_LAG_DAYS"

DEFAULT_GSC_SEARCH_ANALYTICS_DAYS = 1
DEFAULT_GSC_SEARCH_MAX_ROWS = 10_000
DEFAULT_GSC_FINAL_DATA_LAG_DAYS = 3

MAX_GSC_SEARCH_ANALYTICS_DAYS = 31
MAX_GSC_SEARCH_MAX_ROWS = 50_000
MAX_GSC_FINAL_DATA_LAG_DAYS = 30


def bounded_int(value: object, *, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def search_analytics_days(value: object = None) -> int:
    return bounded_int(
        value,
        name="gsc_search_analytics_days",
        default=DEFAULT_GSC_SEARCH_ANALYTICS_DAYS,
        minimum=0,
        maximum=MAX_GSC_SEARCH_ANALYTICS_DAYS,
    )


def search_max_rows(value: object = None) -> int:
    return bounded_int(
        value,
        name="gsc_search_max_rows",
        default=DEFAULT_GSC_SEARCH_MAX_ROWS,
        minimum=1,
        maximum=MAX_GSC_SEARCH_MAX_ROWS,
    )


def final_data_lag_days(value: object = None) -> int:
    return bounded_int(
        value,
        name="gsc_final_data_lag_days",
        default=DEFAULT_GSC_FINAL_DATA_LAG_DAYS,
        minimum=0,
        maximum=MAX_GSC_FINAL_DATA_LAG_DAYS,
    )


def environment_names() -> tuple[str, ...]:
    return (
        GSC_SEARCH_ANALYTICS_DAYS_ENV,
        GSC_SEARCH_MAX_ROWS_ENV,
        GSC_FINAL_DATA_LAG_DAYS_ENV,
    )
