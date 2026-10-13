"""#319: non-secret CAT-05 competitive AI workload shape for duration cohorts.

Counts and request budgets are only intent, not executed provider work.
Search terms and region text are never persisted. This helper does not run
SERP, Perplexity, collectors or any paid AI.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


_FIELDS = (
    "query_count", "depth", "device", "market", "language",
    "region_configured", "compare_content", "competitive_enabled",
    "max_content_pages", "content_timeout_seconds", "content_max_bytes",
    "content_max_redirects", "ymyl_mode",
)


def _shape(state: Any) -> dict[str, object] | None:
    """Only a bounded, fully typed *declared* workload is comparable."""
    queries = getattr(state, "search_queries", None)
    if not isinstance(queries, (tuple, list)) or not 1 <= len(queries) <= 10:
        return None
    if any(
        not isinstance(query, str)
        or not query.strip() or len(query) > 300
        for query in queries
    ):
        return None
    count = len(queries)
    integers = {
        "depth": (getattr(state, "search_depth", None), 1, 1000),
        "max_content_pages": (getattr(state, "search_max_content_pages", None), 0, 100),
        "content_max_bytes": (getattr(state, "search_content_max_bytes", None), 1, 100_000_000),
        "content_max_redirects": (getattr(state, "search_content_max_redirects", None), 0, 100),
    }
    for value, low, high in integers.values():
        if type(value) is not int or not low <= value <= high:
            return None
    timeout = getattr(state, "search_content_timeout_seconds", None)
    if (
        type(timeout) not in (int, float)
        or not math.isfinite(timeout)
        or not 0 < timeout <= 300
    ):
        return None
    comp = getattr(state, "search_competitive", None)
    compare = getattr(state, "search_compare_content", None)
    if type(comp) is not bool or type(compare) is not bool or not comp or not compare:
        return None
    device = getattr(state, "search_device", None)
    market = getattr(state, "market", None)
    language = getattr(state, "language", None)
    region = getattr(state, "search_region", None)
    ymyl = getattr(state, "search_ymyl_mode", None)
    if (
        not isinstance(device, str) or device not in {"mobile", "desktop"}
        or not isinstance(market, str) or not 1 <= len(market) <= 32
        or not isinstance(language, str) or not 1 <= len(language) <= 32
        or not isinstance(region, str) or len(region) > 200
        or not isinstance(ymyl, str) or not 1 <= len(ymyl) <= 40
    ):
        return None
    return {
        "query_count": count,
        "depth": integers["depth"][0],
        "device": device,
        "market": market,
        "language": language,
        "region_configured": bool(region.strip()),
        "compare_content": compare,
        "competitive_enabled": comp,
        "max_content_pages": integers["max_content_pages"][0],
        "content_timeout_seconds": float(timeout),
        "content_max_bytes": integers["content_max_bytes"][0],
        "content_max_redirects": integers["content_max_redirects"][0],
        "ymyl_mode": ymyl,
    }


def search_ai_duration_scope(state: Any) -> dict[str, object]:
    """Persist only a bounded shape for explicitly enabled CAT-05 AI."""
    if getattr(state, "search_ai_competitive", False) is not True:
        return {}
    shape = _shape(state)
    return {"search_ai_competitive_workload": shape} if shape is not None else {}


def comparable_search_ai_duration_scope(
    current: Any, historical: Mapping[str, object],
) -> bool:
    """Reject enabled competitive AI without matching typed workload bounds."""
    if getattr(current, "search_ai_competitive", False) is not True:
        return True
    expected = _shape(current)
    recorded = historical.get("search_ai_competitive_workload")
    if (
        expected is None or not isinstance(recorded, dict)
        or set(recorded) != set(_FIELDS)
    ):
        return False
    return all(
        type(recorded[key]) is type(value) and recorded[key] == value
        for key, value in expected.items()
    )
