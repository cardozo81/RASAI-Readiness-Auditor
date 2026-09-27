from __future__ import annotations

from pathlib import Path

import pytest

from rasai.audit_fulfillment import (
    FAILED_RETRYABLE,
    LIVE_RECOLLECTION,
    PENDING,
    REPLAY_SAFE,
    list_work_items,
    register_work_item,
)
from rasai.domain import Audit
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.reprocess_policy import (
    expand_selected_items,
    item_key,
    item_selected,
    reprocess_policy,
)


AUDIT_ID = "AUD-RPR-CLOSURE"


def _workspace(tmp_path: Path) -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, AUDIT_ID)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=AUDIT_ID, project_name="dependency closure"))
    return workspace


def _register(
    workspace: AuditWorkspace,
    component: str,
    scope_key: str = "AUDIT",
    *,
    status: str = FAILED_RETRYABLE,
    temporal_mode: str = REPLAY_SAFE,
) -> None:
    register_work_item(
        workspace,
        audit_id=AUDIT_ID,
        component=component,
        scope_key=scope_key,
        required=True,
        temporal_mode=temporal_mode,
        status=status,
        retryable=True,
        configuration={"test": True},
    )


@pytest.mark.parametrize("component", ["WEB_PERFORMANCE", "SYNTHETIC_APDEX"])
def test_snapshot_based_measurement_selection_closes_core_dependency_scope(
    tmp_path: Path,
    component: str,
) -> None:
    workspace = _workspace(tmp_path)
    _register(workspace, "DISCOVERY_ACQUISITION", temporal_mode=LIVE_RECOLLECTION)
    _register(workspace, "HTTP_ACQUISITION", "PGE-1", temporal_mode=LIVE_RECOLLECTION)
    _register(
        workspace,
        "RENDER_CAPTURE",
        "PLANNED:PGE-1:MOBILE",
        status=PENDING,
        temporal_mode=LIVE_RECOLLECTION,
    )
    _register(workspace, component, temporal_mode=LIVE_RECOLLECTION)

    expanded = expand_selected_items(
        workspace,
        AUDIT_ID,
        [item_key(component, "AUDIT")],
        use_ai=False,
    )

    assert expanded is not None
    assert item_key(component, "AUDIT") in expanded
    assert "DISCOVERY_ACQUISITION" in expanded
    assert "HTTP_ACQUISITION" in expanded
    assert "RENDER_CAPTURE" in expanded

    render = next(
        item
        for item in list_work_items(workspace, AUDIT_ID)
        if item.component == "RENDER_CAPTURE"
    )
    with reprocess_policy(
        selected_items=[item_key(component, "AUDIT")],
        use_ai=False,
        workspace=workspace,
        audit_id=AUDIT_ID,
    ):
        assert item_selected(render) is True


def test_direct_render_selection_adds_matching_http_prerequisite(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _register(workspace, "HTTP_ACQUISITION", "PGE-1", temporal_mode=LIVE_RECOLLECTION)
    _register(
        workspace,
        "RENDER_CAPTURE",
        "PLANNED:PGE-1:MOBILE",
        status=PENDING,
        temporal_mode=LIVE_RECOLLECTION,
    )

    expanded = expand_selected_items(
        workspace,
        AUDIT_ID,
        [item_key("RENDER_CAPTURE", "PLANNED:PGE-1:MOBILE")],
        use_ai=False,
    )

    assert expanded is not None
    assert item_key("HTTP_ACQUISITION", "PGE-1") in expanded


def test_improvement_dependency_closure_respects_ai_authorization(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _register(workspace, "DISCOVERY_ACQUISITION", temporal_mode=LIVE_RECOLLECTION)
    _register(workspace, "HTTP_ACQUISITION", "PGE-1", temporal_mode=LIVE_RECOLLECTION)
    _register(workspace, "RENDER_CAPTURE", "PLANNED:PGE-1:MOBILE", status=PENDING, temporal_mode=LIVE_RECOLLECTION)
    _register(workspace, "CONTENT_EXTRACTION", "SNP-1")
    _register(workspace, "IMPROVEMENT_INTELLIGENCE")

    disabled = expand_selected_items(
        workspace,
        AUDIT_ID,
        [item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")],
        use_ai=False,
    )
    assert disabled == frozenset({item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")})

    enabled = expand_selected_items(
        workspace,
        AUDIT_ID,
        [item_key("IMPROVEMENT_INTELLIGENCE", "AUDIT")],
        use_ai=True,
    )
    assert enabled is not None
    for dependency in (
        "DISCOVERY_ACQUISITION",
        "HTTP_ACQUISITION",
        "RENDER_CAPTURE",
        "CONTENT_EXTRACTION",
    ):
        assert dependency in enabled


def test_experience_apdex_is_not_artificially_bound_to_render_capture(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    _register(workspace, "RENDER_CAPTURE", "PLANNED:PGE-1:MOBILE", status=PENDING, temporal_mode=LIVE_RECOLLECTION)
    _register(workspace, "EXPERIENCE_APDEX", temporal_mode=LIVE_RECOLLECTION)

    selected = item_key("EXPERIENCE_APDEX", "AUDIT")
    expanded = expand_selected_items(
        workspace,
        AUDIT_ID,
        [selected],
        use_ai=False,
    )

    assert expanded == frozenset({selected})
