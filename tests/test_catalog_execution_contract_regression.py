from __future__ import annotations

import os
from types import SimpleNamespace

from rasai import console_catalog_plan as plan


def _state(**overrides):
    values = {
        "target": "https://example.test/",
        "web_performance": True,
        "search_queries": (),
        "synthetic_apdex": True,
        "apdex_experience": True,
        "improvement_enabled": True,
        "content_remediation": False,
        "technical_remediation": False,
        "ai_provider": "auto",
        "ai_model": None,
        "ai_reasoning": None,
        "runtime_blocks": {},
        "error": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_unselected_cat08_masks_state_and_runtime_environment(monkeypatch) -> None:
    state = _state()
    plan.set_selected_catalog_ids(
        state,
        ["CAT-01", "CAT-02", "CAT-03", "CAT-04", "CAT-06", "CAT-07"],
    )
    plan.set_ai_execution_enabled(state, True)
    monkeypatch.setenv("RASAI_IMPROVEMENT_INTELLIGENCE", "true")

    with plan.project_plan(state):
        assert state.improvement_enabled is False
        assert os.environ["RASAI_IMPROVEMENT_INTELLIGENCE"] == "false"
        # Optional IA remains available because CAT-03 requested it.
        assert state.ai_provider == "auto"

    assert state.improvement_enabled is True
    assert os.environ["RASAI_IMPROVEMENT_INTELLIGENCE"] == "true"


def test_catalog_snapshot_exposes_persisted_id_and_per_catalog_ai_flag() -> None:
    state = _state()
    plan.set_selected_catalog_ids(state, ["CAT-01", "CAT-03"])
    plan.set_ai_execution_enabled(state, True)

    rows = {row["catalog_id"]: row for row in plan.catalog_snapshot(state)}
    assert rows["CAT-01"]["id"] == "CAT-01"
    assert rows["CAT-03"]["id"] == "CAT-03"
    assert rows["CAT-03"]["ai_execution_enabled"] is True
    assert rows["CAT-08"]["selected"] is False
    assert rows["CAT-08"]["ai_execution_enabled"] is False
