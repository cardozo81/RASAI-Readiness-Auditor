"""Read-only projection guarantees for final report materialization."""
from __future__ import annotations

from rasai.audit_fulfillment import (
    REPLAY_SAFE,
    SUCCESS,
    initialize_contract,
    recalculate,
    register_work_item,
    set_work_item_status,
)
from rasai.domain import Audit
from rasai.governed_analysis_runtime import _logical_db_fingerprint
from rasai.governed_report_projection_runtime import project_persisted_fulfillment
from rasai.persistence import AuditPersistence, AuditWorkspace


def _workspace(tmp_path, audit_id: str = "AUD-PROJECTION") -> AuditWorkspace:
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="projection invariant"))
    initialize_contract(workspace, audit_id, {"source": "projection-test"})
    register_work_item(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        required=True,
        temporal_mode=REPLAY_SAFE,
        status=SUCCESS,
        retryable=False,
    )
    set_work_item_status(
        workspace,
        audit_id=audit_id,
        component="CORE_AUDIT",
        status=SUCCESS,
        result_ref=f"audit:{audit_id}",
        retryable=False,
    )
    summary = recalculate(workspace, audit_id)
    assert summary.is_final
    return workspace


def test_persisted_fulfillment_projection_does_not_mutate_audit_db(tmp_path) -> None:
    workspace = _workspace(tmp_path)
    report_dir = workspace.root / "report"
    report_dir.mkdir()
    html = report_dir / "index.html"
    html.write_text("<!doctype html><html><body><main>report</main></body></html>", encoding="utf-8")

    before = _logical_db_fingerprint(workspace.database)
    summary = project_persisted_fulfillment(
        workspace=workspace,
        audit_id="AUD-PROJECTION",
    )
    after = _logical_db_fingerprint(workspace.database)

    assert summary is not None and summary.is_final
    assert before == after
    assert (report_dir / "processing-status.json").is_file()
    rendered = html.read_text(encoding="utf-8")
    assert "rasai-fulfillment-banner" in rendered
    assert "relatório final" in rendered


def test_projection_is_idempotent_for_html_banner_and_database(tmp_path) -> None:
    workspace = _workspace(tmp_path, "AUD-PROJECTION-IDEMPOTENT")
    report_dir = workspace.root / "report"
    report_dir.mkdir()
    html = report_dir / "readiness.html"
    html.write_text("<html><body>content</body></html>", encoding="utf-8")

    baseline = _logical_db_fingerprint(workspace.database)
    project_persisted_fulfillment(
        workspace=workspace,
        audit_id="AUD-PROJECTION-IDEMPOTENT",
    )
    first = html.read_text(encoding="utf-8")
    project_persisted_fulfillment(
        workspace=workspace,
        audit_id="AUD-PROJECTION-IDEMPOTENT",
    )
    second = html.read_text(encoding="utf-8")

    assert first == second
    assert second.count("rasai-fulfillment-banner") == 1
    assert _logical_db_fingerprint(workspace.database) == baseline
