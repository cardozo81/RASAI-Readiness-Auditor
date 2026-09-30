"""Focused secret-safe render failure diagnostics across AUD and RPR."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from rasai.browser_render_failure import (
    render_failure_context,
    render_failure_public_detail,
)
from rasai.audit_fulfillment import list_work_items, start_reprocess_run
from rasai.catalog_report_governance import _rpr_render_diagnostics
from rasai.core_reprocessing import RENDER_CAPTURE, _attempt, synchronize_core_work_items
from rasai.rendering import BrowserRenderResult, RenderErrorKind
from tests.test_core_reprocessing import _workspace


AUDIT_ID = "AUD-CORE-RECOVERY"


def test_causal_diagnosis_never_persists_exception_message_or_urls() -> None:
    exception = RuntimeError("https://private.example/?token=top-secret")
    context = render_failure_context("DOCUMENT_SOURCE", exception)
    assert context == {
        "stage": "DOCUMENT_SOURCE",
        "exception_class": "RuntimeError",
    }
    assert "top-secret" not in json.dumps(context)
    assert "Origem do documento" not in render_failure_public_detail(context)
    assert "Aquisição da origem do documento" in render_failure_public_detail(context)
    assert render_failure_context("new-unknown-stage", exception)["stage"] == "UNCLASSIFIED"


def test_instrumented_browser_records_stage_and_safe_error_class(monkeypatch) -> None:
    from rasai import browser_identity_renderer, device_context_capture

    class FailureRenderer:
        def __init__(self):
            self._browser = SimpleNamespace(new_context=self._fail_context)
            self.navigation_timeout_ms = 2000
            self.settle_timeout_ms = 250

        def _fail_context(self, **_kwargs):
            raise ValueError("secret value https://private.example/?token=top-secret")

        def _navigation_failure(self, *, url, error_kind, **_kwargs):
            return BrowserRenderResult(
                requested_url=url,
                final_url=None,
                http_status=None,
                content_type=None,
                rendered_html=None,
                browser_metadata={"render_error": error_kind.value},
                error_kind=error_kind,
            )

    monkeypatch.setattr(browser_identity_renderer, "BrowserIdentityRenderer", FailureRenderer)
    device_context_capture._install_browser_capture()

    fake = FailureRenderer()
    result = fake._render_once(
        url="https://public.example/",
        profile=SimpleNamespace(),
        options={},
        identity={},
    )
    assert result.error_kind == RenderErrorKind.RENDERER_ERROR
    assert result.browser_metadata["render_failure_context"] == {
        "stage": "CONTEXT_CREATE",
        "exception_class": "ValueError",
    }
    assert "top-secret" not in json.dumps(result.browser_metadata)


def test_failed_rpr_render_attempt_persists_only_safe_causal_context(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path, render_succeeded=False, rendered_exists=False,
        rendered_ref_declared=False,
    )
    synchronize_core_work_items(workspace, AUDIT_ID)
    item = next(
        entry for entry in list_work_items(workspace, AUDIT_ID)
        if entry.component == RENDER_CAPTURE
    )
    reprocess_id = start_reprocess_run(workspace, AUDIT_ID)

    class Renderer:
        def render(self, url, device, **_kwargs):
            return BrowserRenderResult(
                requested_url=url,
                final_url=None,
                http_status=None,
                content_type=None,
                rendered_html=None,
                browser_metadata={
                    "render_error": "RENDERER_ERROR",
                    "render_failure_context": {
                        "stage": "DOCUMENT_SOURCE",
                        "exception_class": "ValueError",
                    },
                },
                error_kind=RenderErrorKind.RENDERER_ERROR,
            )

    success, affected = _attempt(
        workspace, AUDIT_ID, item, reprocess_id, renderer=Renderer()
    )
    assert success is False
    assert not affected

    with sqlite3.connect(workspace.database) as connection:
        row = connection.execute(
            """SELECT status,error_code,error_message,metadata,reprocess_id
               FROM audit_fulfillment_attempts
               WHERE audit_id=? AND reprocess_id=?""",
            (AUDIT_ID, reprocess_id),
        ).fetchone()
    assert row is not None
    status, code, detail, metadata, causal_rpr = row
    assert (status, code, causal_rpr) == (
        "FAILED_RETRYABLE", "RENDERER_ERROR", reprocess_id
    )
    assert "Aquisição da origem do documento" in detail
    assert json.loads(metadata)["render_failure_context"]["stage"] == "DOCUMENT_SOURCE"
    assert _rpr_render_diagnostics(workspace.database, AUDIT_ID) == {
        "SNP-CORE": {
            "stage": "DOCUMENT_SOURCE",
            "exception_class": "ValueError",
        }
    }
    assert "private.example" not in detail + metadata
