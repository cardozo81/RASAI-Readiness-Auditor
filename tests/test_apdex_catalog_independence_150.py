"""Focused regressions for #150: effective Apdex plan and independent CAT-07."""
from __future__ import annotations

from types import SimpleNamespace

from rasai import audit_catalog
from rasai import cli_extensions
from rasai import console_apdex_configuration
from rasai import console_profile_capability_architecture
from rasai import console_ui_catalog
from rasai import console_catalog_plan as plan
from rasai.audit_execution_contract import normalize_audit_job_payload
from rasai.audit_fulfillment import (
    REPLAY_SAFE,
    SUCCESS,
    list_work_items,
    register_work_item,
)
from rasai.console_m23 import State, synthetic_load_summary
from rasai.console_search_intelligence import SearchConsoleState
from rasai.domain import Audit
from rasai.fulfillment_execution_contract import _reconcile_requested_apdex
from rasai.m23_apdex import SyntheticApdexConfig
from rasai.m23_cli import configured_apdex
from rasai.m25_apdex_experience import ExperienceApdexConfig
from rasai.m25_runtime import peek_pending_config, set_pending_config
from rasai.persistence import AuditPersistence, AuditWorkspace


AUDIT_ID = "AUD-APDEX-INDEPENDENCE-150"


def _workspace(tmp_path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="issue-150"))
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component="CORE_AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=False,
        configuration={"test": True},
    )
    return workspace


def test_effective_catalog_plan_masks_stale_apdex_environment_for_fulfillment(
    tmp_path, monkeypatch,
) -> None:
    """Real regression: UI had CAT-06/07 off but stale env recreated both work-items."""
    workspace = _workspace(tmp_path)
    state = SearchConsoleState()
    state.synthetic_apdex = True
    state.apdex_experience = True
    plan.set_selected_catalog_ids(state, ["CAT-08", "CAT-10"])

    monkeypatch.setenv("RASAI_SYNTHETIC_APDEX", "true")
    monkeypatch.setenv("RASAI_APDEX_EXPERIENCE", "true")

    with plan.project_plan(state):
        assert plan.selected_catalog_ids(state) == ("CAT-08", "CAT-10")
        assert state.synthetic_apdex is False
        assert state.apdex_experience is False
        assert __import__("os").environ["RASAI_SYNTHETIC_APDEX"] == "false"
        assert __import__("os").environ["RASAI_APDEX_EXPERIENCE"] == "false"
        _reconcile_requested_apdex(workspace, AUDIT_ID)

    components = {item.component for item in list_work_items(workspace, AUDIT_ID)}
    assert "SYNTHETIC_APDEX" not in components
    assert "EXPERIENCE_APDEX" not in components
    # Operator configuration survives outside the one-execution projection.
    assert state.synthetic_apdex is True
    assert state.apdex_experience is True
    assert __import__("os").environ["RASAI_SYNTHETIC_APDEX"] == "true"
    assert __import__("os").environ["RASAI_APDEX_EXPERIENCE"] == "true"


def test_cat07_selection_and_removal_are_independent_from_cat06() -> None:
    state = SearchConsoleState()
    plan.set_selected_catalog_ids(state, ["CAT-07"])
    assert plan.selected_catalog_ids(state) == ("CAT-07",)

    plan.select_catalog(state, audit_catalog.CATALOG_BY_ID["CAT-06"])
    assert plan.selected_catalog_ids(state) == ("CAT-06", "CAT-07")

    assert plan.deselect_catalog(state, audit_catalog.CATALOG_BY_ID["CAT-06"]) is True
    assert plan.selected_catalog_ids(state) == ("CAT-07",)


def test_cli_resolves_pending_experience_when_navigation_is_disabled() -> None:
    args = SimpleNamespace(synthetic_apdex=False, apdex_experience=True)
    try:
        nav = configured_apdex(args, {})
        ux = peek_pending_config()
        assert nav.enabled is False
        assert ux.enabled is True
    finally:
        set_pending_config(ExperienceApdexConfig(enabled=False))


def test_standalone_experience_dispatch_does_not_execute_disabled_navigation(
    monkeypatch,
) -> None:
    calls: list[tuple[str, object]] = []

    def fake_execute_pending_m25(*, audit_id, workspace):
        calls.append((audit_id, workspace))
        return None

    monkeypatch.setattr(cli_extensions, "execute_pending_m25", fake_execute_pending_m25)
    workspace = object()
    ran = cli_extensions._execute_standalone_experience(
        m23_config=SyntheticApdexConfig(enabled=False),
        experience_config=SimpleNamespace(enabled=True),
        audit_id=AUDIT_ID,
        workspace=workspace,
        assessment=None,
    )
    assert ran is True
    assert calls == [(AUDIT_ID, workspace)]


def test_synthetic_load_summary_counts_cat07_without_cat06() -> None:
    state = State(
        synthetic_apdex=False,
        apdex_experience=True,
        max_pages=10,
        apdex_experience_max_pages=1,
        apdex_experience_max_attempts=25,
    )
    attempts, detail = synthetic_load_summary(state)
    assert attempts == 25
    assert "Navigation Apdex não solicitado" in detail
    assert "25 ação(ões) Synthetic User Experience Apdex" in detail


def test_saas_audit_contract_accepts_experience_without_navigation() -> None:
    normalized = normalize_audit_job_payload(
        {"synthetic_apdex": False, "apdex_experience": True}
    )
    assert normalized["synthetic_apdex"] is False
    assert normalized["apdex_experience"] is True


def test_navigation_configuration_off_does_not_disable_experience(monkeypatch) -> None:
    state = State(synthetic_apdex=True, apdex_experience=True)
    monkeypatch.setattr(console_apdex_configuration, "_yes_no", lambda *args, **kwargs: False)

    console_apdex_configuration._configure_navigation(state)

    assert state.synthetic_apdex is False
    assert state.apdex_experience is True


def test_experience_capability_is_ready_without_navigation() -> None:
    state = State(
        synthetic_apdex=False,
        apdex_experience=True,
        apdex_experience_device_mix="mobile=60,desktop=35,tablet=5",
    )
    capability = next(
        item for item in console_ui_catalog.CAPABILITIES
        if item.key == "apdex-experience"
    )
    status, detail = console_ui_catalog.capability_status(state, capability)
    assert status == "APTO"
    assert "60" in detail


def test_experience_execution_profile_contains_only_its_own_apdex_capability() -> None:
    assert console_profile_capability_architecture.CAPS["apdex-experience"] == (
        "apdex-experience",
    )
