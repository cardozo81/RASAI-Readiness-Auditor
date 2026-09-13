from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from rasai.audit_fulfillment import BLOCKED, FAILED_RETRYABLE, SUCCESS, WAITING_FOR_DATA, list_work_items, start_reprocess_run
from rasai.core_reprocessing import (
    CONTENT_EXTRACTION,
    HTTP_ACQUISITION,
    RENDER_CAPTURE,
    _core_unresolved,
    _recover_extraction,
    _recover_render,
    _retryable_core,
    synchronize_core_work_items,
)
from rasai.domain import Audit, AuditTarget, DeviceContext, Page, PageSnapshot, RuleExecution, RuleResult, TargetType, new_id, utc_now
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.rendering import BrowserRenderResult

_HTML = "<!doctype html><html><head><title>Recovered</title></head><body><main><h1>Recovered</h1><p>Enough persisted content for deterministic extraction.</p></main></body></html>"


def _workspace(root: Path, *, render_succeeded: bool, rendered_exists: bool, rendered_ref_declared: bool = True) -> AuditWorkspace:
    audit = Audit(audit_id="AUD-CORE-RECOVERY",project_name="core recovery")
    workspace = AuditWorkspace.create(root,audit.audit_id)
    page = Page(
        page_id="PGE-CORE",audit_id=audit.audit_id,
        normalized_url="https://example.test/core",discovered_url="https://example.test/core",
    )
    target = AuditTarget(
        target_id="TGT-CORE",audit_id=audit.audit_id,input_url=page.normalized_url,
        normalized_origin="https://example.test",target_type=TargetType.URL,
    )
    rendered_ref = "artifacts/rendered/core.html" if rendered_ref_declared else None
    if rendered_exists and rendered_ref:
        path = workspace.root / rendered_ref
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(_HTML,encoding="utf-8")
    snapshot = PageSnapshot(
        snapshot_id="SNP-CORE",page_id=page.page_id,device=DeviceContext.MOBILE,
        requested_url=page.normalized_url,final_url=page.normalized_url,
        captured_at=datetime(2026,9,13,12,0,tzinfo=timezone.utc),http_status=200,
        content_type="text/html",rendered_artifact_ref=rendered_ref,
        browser_metadata={"render_succeeded":render_succeeded},
    )
    http_rule = RuleExecution(
        rule_execution_id=new_id("REX"),audit_id=audit.audit_id,rule_id="BR-GEO-005",rule_version="1",
        page_id=page.page_id,snapshot_id=None,device=None,result=RuleResult.PASS,
        observed_value={"status":200,"network_error":None},
        expected_condition="retrievable",evidence_ids=(),executed_at=utc_now(),
    )
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(audit)
        persistence.targets.add(target)
        persistence.pages.add(page)
        persistence.snapshots.add(snapshot)
        persistence.rule_executions.add(http_rule)
    return workspace


def _by_component(workspace: AuditWorkspace) -> dict[str, object]:
    return {item.component:item for item in list_work_items(workspace,"AUD-CORE-RECOVERY")}


def test_core_projection_separates_successful_capture_from_pending_extraction() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory),render_succeeded=True,rendered_exists=True)
        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        items = _by_component(workspace)
        assert items[HTTP_ACQUISITION].status == SUCCESS
        assert items[RENDER_CAPTURE].status == SUCCESS
        assert items[CONTENT_EXTRACTION].status == FAILED_RETRYABLE
        assert _core_unresolved(workspace,"AUD-CORE-RECOVERY") is True


def test_replay_safe_extraction_completes_without_network_recollection() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory),render_succeeded=True,rendered_exists=True)
        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        item = next(value for value in list_work_items(workspace,"AUD-CORE-RECOVERY") if value.component == CONTENT_EXTRACTION)
        reprocess_id = start_reprocess_run(workspace,"AUD-CORE-RECOVERY")
        success,code,affected = _recover_extraction(
            workspace,"AUD-CORE-RECOVERY",item,reprocess_id,
        )
        assert success is True
        assert code == "EXTRACTION_RECOVERED"
        assert affected == {"SNP-CORE"}
        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        extraction = next(value for value in list_work_items(workspace,"AUD-CORE-RECOVERY") if value.component == CONTENT_EXTRACTION)
        assert extraction.status == SUCCESS
        with AuditPersistence(workspace) as persistence:
            snapshot = persistence.snapshots.get("SNP-CORE")
            assert snapshot is not None and snapshot.main_content_ref
            assert (workspace.root / snapshot.main_content_ref).is_file()


def test_missing_artifact_after_recorded_success_is_blocked_not_refetched() -> None:
    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory),render_succeeded=True,rendered_exists=False,rendered_ref_declared=True)
        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        items = _by_component(workspace)
        assert items[RENDER_CAPTURE].status == BLOCKED
        assert items[RENDER_CAPTURE].retryable is False
        assert items[CONTENT_EXTRACTION].status == BLOCKED
        assert items[CONTENT_EXTRACTION].retryable is False
        assert _core_unresolved(workspace,"AUD-CORE-RECOVERY") is True
        assert all(value.component not in {RENDER_CAPTURE,CONTENT_EXTRACTION} for value in _retryable_core(workspace,"AUD-CORE-RECOVERY"))


def test_failed_original_render_can_be_recovered_inside_same_aud() -> None:
    class Renderer:
        def render(self, url, device, **kwargs):
            return BrowserRenderResult(
                requested_url=url,final_url=url,http_status=200,content_type="text/html",
                rendered_html=_HTML,browser_metadata={"render_succeeded":True},error_kind=None,
            )

    with TemporaryDirectory() as directory:
        workspace = _workspace(Path(directory),render_succeeded=False,rendered_exists=False,rendered_ref_declared=False)
        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        items = _by_component(workspace)
        assert items[RENDER_CAPTURE].status == FAILED_RETRYABLE
        assert items[CONTENT_EXTRACTION].status == WAITING_FOR_DATA

        reprocess_id = start_reprocess_run(workspace,"AUD-CORE-RECOVERY")
        render = next(value for value in list_work_items(workspace,"AUD-CORE-RECOVERY") if value.component == RENDER_CAPTURE)
        success,code,affected = _recover_render(
            workspace,"AUD-CORE-RECOVERY",render,reprocess_id,Renderer(),
        )
        assert success is True
        assert code == "RENDER_CAPTURE_RECOVERED"
        assert affected == {"SNP-CORE"}

        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        extraction = next(value for value in list_work_items(workspace,"AUD-CORE-RECOVERY") if value.component == CONTENT_EXTRACTION)
        assert extraction.status == FAILED_RETRYABLE
        success,code,_ = _recover_extraction(workspace,"AUD-CORE-RECOVERY",extraction,reprocess_id)
        assert success is True
        assert code == "EXTRACTION_RECOVERED"
        synchronize_core_work_items(workspace,"AUD-CORE-RECOVERY")
        items = _by_component(workspace)
        assert items[RENDER_CAPTURE].status == SUCCESS
        assert items[CONTENT_EXTRACTION].status == SUCCESS
