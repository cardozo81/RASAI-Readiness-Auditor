"""#319: no paid requests, never persist CAT-05 query or region text."""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from rasai.console_search_duration_scope_319 import (
    comparable_search_ai_duration_scope, search_ai_duration_scope,
)


def _active():
    return SimpleNamespace(
        search_ai_competitive=True,
        search_queries=("private life-insurance query", "price by neighborhood"),
        search_depth=20,
        search_device="mobile",
        market="BR",
        language="pt-BR",
        search_region="PRIVATE CITY AND POSTCODE DO NOT PERSIST",
        search_competitive=True,
        search_compare_content=True,
        search_max_content_pages=3,
        search_content_timeout_seconds=10.0,
        search_content_max_bytes=2_000_000,
        search_content_max_redirects=5,
        search_ymyl_mode="AUTO",
    )


def test_exact_declared_search_workload_is_metadata_only():
    state = _active()
    frozen = search_ai_duration_scope(state)
    assert frozen["search_ai_competitive_workload"]["query_count"] == 2
    assert frozen["search_ai_competitive_workload"]["region_configured"] is True
    assert frozen["search_ai_competitive_workload"]["depth"] == 20
    assert comparable_search_ai_duration_scope(state, frozen)
    assert "private life-insurance" not in str(frozen)
    assert "price by neighborhood" not in str(frozen)
    assert "PRIVATE CITY AND POSTCODE" not in str(frozen)
    state.search_ai_competitive = False
    assert search_ai_duration_scope(state) == {}


@pytest.mark.parametrize(("name", "changed"), [
    ("search_depth", 30),
    ("search_device", "desktop"),
    ("market", "US"),
    ("language", "en-US"),
    ("search_region", ""),
    ("search_compare_content", False),
    ("search_max_content_pages", 6),
    ("search_content_timeout_seconds", 15.0),
    ("search_content_max_bytes", 4_000_000),
    ("search_content_max_redirects", 9),
    ("search_ymyl_mode", "YMYL"),
    ("search_queries", ("another query",)),
])
def test_relevant_changed_search_workload_refuses_prior_forecast(name, changed):
    current = _active()
    old = search_ai_duration_scope(current)
    setattr(current, name, changed)
    assert not comparable_search_ai_duration_scope(current, old)


@pytest.mark.parametrize(("name", "invalid"), [
    ("search_queries", ()),
    ("search_queries", ("",)),
    ("search_depth", "20"),
    ("search_depth", True),
    ("search_content_timeout_seconds", float("nan")),
    ("search_content_max_bytes", -1),
    ("search_compare_content", "true"),
    ("search_competitive", False),
    ("search_ymyl_mode", None),
])
def test_no_fingerprint_when_execution_workload_cannot_be_proven(name, invalid):
    state = _active()
    setattr(state, name, invalid)
    assert search_ai_duration_scope(state) == {}
    assert not comparable_search_ai_duration_scope(state, {})


@pytest.mark.parametrize(("altered", "value"), [
    ("query_count", "2"),
    ("depth", True),
    ("region_configured", 1),
    ("content_timeout_seconds", float("inf")),
])
def test_forged_historical_workload_types_are_not_normalized(altered, value):
    state = _active()
    historical = deepcopy(search_ai_duration_scope(state))
    historical["search_ai_competitive_workload"][altered] = value
    assert not comparable_search_ai_duration_scope(state, historical)


def test_old_active_history_without_bounded_shape_is_not_comparable():
    state = _active()
    assert not comparable_search_ai_duration_scope(
        state, {"search_ai_competitive": True},
    )
    historical = search_ai_duration_scope(state)
    historical["search_ai_competitive_workload"]["unexpected"] = "unsealed"
    assert not comparable_search_ai_duration_scope(state, historical)
