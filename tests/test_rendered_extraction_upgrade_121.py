"""Targeted regression: a later rendered DOM supersedes earlier RAW-only M4 evidence."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from rasai.audit_fulfillment import (
    REPLAY_SAFE, SUCCESS, FAILED_RETRYABLE, list_work_items,
    register_work_item, set_work_item_status, start_reprocess_run,
)
from rasai.core_reprocessing import (
    CONTENT_EXTRACTION, RENDER_CAPTURE, _extraction_recovery_candidates,
    _recover_extraction, _recover_render, synchronize_core_work_items,
)
from rasai.domain import DeviceContext
from rasai.m3 import M3ExecutionResult
from rasai.m4 import execute_m4
from rasai.persistence import AuditPersistence
from rasai.rendering import BrowserRenderResult
from rasai.reprocess_policy import reprocess_policy
from tests.test_core_reprocessing import _workspace

AUDIT_ID = "AUD-CORE-RECOVERY"
SNAPSHOT_ID = "SNP-CORE"
PAGE_ID = "PGE-CORE"
RAW_HTML = (
    "<!doctype html><html><head><title>Raw-only baseline</title></head>"
    "<body><main><h1>Raw source</h1><p>Evidence originally derived "
    "from the HTTP document before browser rendering was available. "
    "This paragraph supplies actual main content for extraction.</p>"
    "</main></body></html>"
)
RENDER_HTML = (
    "<!doctype html><html><head><title>Rendered recovery</title></head>"
    "<body><main><h1>Rendered source</h1><p>Updated main content that "
    "was only available after the rendering recovery succeeded. "
    "Persist this text separately to preserve historical artifact bytes.</p>"
    "</main></body></html>"
)


def _item(workspace, component):
    return next(
        item for item in list_work_items(workspace, AUDIT_ID)
        if item.component == component
    )


def _source_counts(workspace):
    with sqlite3.connect(workspace.database) as connection:
        return dict(connection.execute(
            """SELECT source,COUNT(*) FROM evidence
               WHERE audit_id=? AND snapshot_id=?
                 AND source IN ('RAW_HTML_FALLBACK','RENDERED_DOM')
               GROUP BY source""",
            (AUDIT_ID, SNAPSHOT_ID),
        ))


def _raw_only_workspace(tmp_path):
    workspace = _workspace(
        tmp_path, render_succeeded=False,
        rendered_exists=False, rendered_ref_declared=False,
    )
    path = workspace.root / "artifacts" / "raw" / "source.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(RAW_HTML, encoding="utf-8")
    with sqlite3.connect(workspace.database) as connection:
        connection.execute(
            "UPDATE page_snapshots SET raw_artifact_ref=? WHERE snapshot_id=?",
            ("artifacts/raw/source.html", SNAPSHOT_ID),
        )
    with AuditPersistence(workspace) as persistence:
        original = execute_m4(
            M3ExecutionResult(
                snapshot_ids={PAGE_ID: {DeviceContext.MOBILE: SNAPSHOT_ID}},
                failures=(),
            ),
            persistence,
            workspace,
        )
    assert not original.failures
    synchronize_core_work_items(workspace, AUDIT_ID)
    assert _item(workspace, CONTENT_EXTRACTION).status == SUCCESS
    assert _source_counts(workspace).get("RAW_HTML_FALLBACK", 0) >= 1
    return workspace


class _RecoveredRenderer:
    def render(self, url, device, **_kwargs):
        return BrowserRenderResult(
            requested_url=url,
            final_url=url,
            http_status=200,
            content_type="text/html",
            rendered_html=RENDER_HTML,
            browser_metadata={"render_succeeded": True},
        )


def test_render_recovery_reopens_raw_extraction_without_recollecting_success(tmp_path):
    workspace = _raw_only_workspace(tmp_path)
    register_work_item(
        workspace,
        audit_id=AUDIT_ID, component="WEB_PERFORMANCE",
        required=True, temporal_mode=REPLAY_SAFE, status=SUCCESS,
        retryable=False,
    )
    set_work_item_status(
        workspace, audit_id=AUDIT_ID,
        component="WEB_PERFORMANCE", status=SUCCESS,
        result_ref="web-performance:preserved", retryable=False,
    )

    with sqlite3.connect(workspace.database) as connection:
        before = connection.execute(
            "SELECT main_content_ref FROM page_snapshots WHERE snapshot_id=?",
            (SNAPSHOT_ID,),
        ).fetchone()[0]
    original_evidence = _source_counts(workspace)["RAW_HTML_FALLBACK"]
    reprocess_id = start_reprocess_run(workspace, AUDIT_ID)
    ok, code, affected = _recover_render(
        workspace, AUDIT_ID, _item(workspace, RENDER_CAPTURE),
        reprocess_id, _RecoveredRenderer(),
    )
    assert (ok, code, affected) == (
        True, "RENDER_CAPTURE_RECOVERED", {SNAPSHOT_ID},
    )
    synchronize_core_work_items(workspace, AUDIT_ID)
    extraction = _item(workspace, CONTENT_EXTRACTION)
    assert extraction.status == FAILED_RETRYABLE
    assert extraction.last_error_code == "RENDERED_SOURCE_UPGRADE_REQUIRED"
    assert _source_counts(workspace)["RAW_HTML_FALLBACK"] == original_evidence

    # The user chose only the failed render, but its affected M4 is mandatory.
    with reprocess_policy(selected_items=("RENDER_CAPTURE",), use_ai=False):
        assert _extraction_recovery_candidates(
            workspace, AUDIT_ID, {SNAPSHOT_ID}
        ) == (extraction,)
        assert _extraction_recovery_candidates(workspace, AUDIT_ID, set()) == ()

    ok, code, affected = _recover_extraction(
        workspace, AUDIT_ID, extraction, reprocess_id,
    )
    assert (ok, code, affected) == (
        True, "EXTRACTION_RECOVERED", {SNAPSHOT_ID},
    )
    synchronize_core_work_items(workspace, AUDIT_ID)
    assert _item(workspace, CONTENT_EXTRACTION).status == SUCCESS
    assert _item(workspace, "WEB_PERFORMANCE").status == SUCCESS
    assert _source_counts(workspace).get("RAW_HTML_FALLBACK", 0) == 0
    assert _source_counts(workspace).get("RENDERED_DOM", 0) >= 1

    with sqlite3.connect(workspace.database) as connection:
        after = connection.execute(
            "SELECT main_content_ref FROM page_snapshots WHERE snapshot_id=?",
            (SNAPSHOT_ID,),
        ).fetchone()[0]
        archive = connection.execute(
            """SELECT COUNT(*) FROM audit_reprocess_derived_archive
               WHERE audit_id=? AND reprocess_id=?
                 AND entity_type='superseded_raw_extraction_evidence'""",
            (AUDIT_ID, reprocess_id),
        ).fetchone()[0]
    assert archive == original_evidence
    assert after is not None
    assert f"artifacts/reprocess/{reprocess_id}/extraction/" in after
    assert (workspace.root / after).is_file()
    assert "Updated main content" in (workspace.root / after).read_text()
    if before:
        assert before != after
        assert (workspace.root / before).is_file()
        assert "originally derived" in (workspace.root / before).read_text()


def test_no_rendered_artifact_does_not_invalidate_valid_raw_extraction(tmp_path):
    workspace = _raw_only_workspace(tmp_path)
    assert _item(workspace, CONTENT_EXTRACTION).status == SUCCESS
    assert _extraction_recovery_candidates(workspace, AUDIT_ID, set()) == ()


def test_failed_rendered_reextraction_never_retires_raw_source(tmp_path, monkeypatch):
    workspace = _raw_only_workspace(tmp_path)
    reprocess_id = start_reprocess_run(workspace, AUDIT_ID)
    ok, _, _ = _recover_render(
        workspace, AUDIT_ID, _item(workspace, RENDER_CAPTURE),
        reprocess_id, _RecoveredRenderer(),
    )
    assert ok
    synchronize_core_work_items(workspace, AUDIT_ID)
    # Force a deterministic extractor failure without touching the historical data.
    from rasai import m4

    class FailingExtractor:
        def extract(self, _html):
            raise ValueError("controlled M4 extraction failure")

    original = m4.ContentExtractor
    monkeypatch.setattr(m4, "ContentExtractor", lambda: FailingExtractor())
    try:
        ok, code, changed = _recover_extraction(
            workspace, AUDIT_ID, _item(workspace, CONTENT_EXTRACTION),
            reprocess_id,
        )
    finally:
        monkeypatch.setattr(m4, "ContentExtractor", original)
    assert ok is False and code == "EXTRACTION_ERROR" and not changed
    assert _source_counts(workspace).get("RAW_HTML_FALLBACK", 0) >= 1
    synchronize_core_work_items(workspace, AUDIT_ID)
    assert _item(workspace, CONTENT_EXTRACTION).status == FAILED_RETRYABLE
