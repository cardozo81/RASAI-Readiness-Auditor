"""Linux-authoritative SaaS/control-plane regressions for AUD configuration reuse."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from rasai.audit_configuration_reuse import KIND_AUDIT_PAYLOAD, persist_audit_configuration
from rasai.audit_configuration_reuse_saas import build_reused_payload
from rasai.audit_execution_contract import normalize_audit_job_payload
from rasai.audit_fulfillment import REPLAY_SAFE, SUCCESS, initialize_contract, recalculate, register_work_item, set_work_item_status
from rasai.domain import Audit, CompletionStatus
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.web.app import ExecutionJobCreate


def _complete_workspace(root: Path, audit_id: str) -> AuditWorkspace:
    workspace = AuditWorkspace.create(root, audit_id)
    with AuditPersistence(workspace) as persistence:
        persistence.audits.add(Audit(audit_id=audit_id, project_name="saas configuration reuse"))
        persistence.audits.complete(audit_id, completion_status=CompletionStatus.COMPLETE)
    initialize_contract(workspace, audit_id)
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
    assert recalculate(workspace, audit_id).consolidation_eligible is True
    return workspace


def test_saas_reuse_inherits_payload_series_and_records_override_delta() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = _complete_workspace(root, "AUD-SAAS")
        payload = normalize_audit_job_payload({
            "urls": ["https://example.com/"],
            "max_pages": 10,
            "device_context": "mobile",
        })
        snapshot = persist_audit_configuration(
            source.root,
            audit_id="AUD-SAAS",
            kind=KIND_AUDIT_PAYLOAD,
            configuration=payload,
            scope={"project_id": "P1", "property_id": "PROP1", "environment_id": "ENV1"},
        )
        reused = build_reused_payload(
            root,
            "AUD-SAAS",
            {"max_pages": 25},
            project_id="P1",
            property_id="PROP1",
            environment_id="ENV1",
        )
        assert reused["max_pages"] == 25
        assert reused["configuration_source_audit_id"] == "AUD-SAAS"
        assert reused["configuration_source_hash"] == snapshot.configuration_hash
        assert reused["execution_series_id"] == snapshot.execution_series_id
        assert "max_pages" in reused["configuration_changed_fields"]


def test_saas_reuse_rejects_cross_scope_and_client_managed_provenance() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        source = _complete_workspace(root, "AUD-SAAS")
        payload = normalize_audit_job_payload({"urls": ["https://example.com/"]})
        persist_audit_configuration(
            source.root,
            audit_id="AUD-SAAS",
            kind=KIND_AUDIT_PAYLOAD,
            configuration=payload,
            scope={"project_id": "P1", "property_id": "PROP1", "environment_id": "ENV1"},
        )

        with pytest.raises(ValueError, match="outro property_id"):
            build_reused_payload(
                root,
                "AUD-SAAS",
                {},
                project_id="P1",
                property_id="OTHER",
                environment_id="ENV1",
            )

        with pytest.raises(ValueError, match="server-managed"):
            build_reused_payload(
                root,
                "AUD-SAAS",
                {"execution_series_id": "SER-CLIENT"},
                project_id="P1",
                property_id="PROP1",
                environment_id="ENV1",
            )


def test_web_contract_exposes_source_audit_only_as_optional_audit_input() -> None:
    request = ExecutionJobCreate(
        property_id="PROP1",
        environment_id="ENV1",
        job_type="AUDIT",
        source_audit_id="AUD-SAAS",
        payload={"max_pages": 15},
    )
    assert request.source_audit_id == "AUD-SAAS"
    assert request.job_type == "AUDIT"
