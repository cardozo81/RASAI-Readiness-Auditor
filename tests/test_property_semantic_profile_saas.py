from __future__ import annotations

from pathlib import Path

import pytest

from rasai.platform.saas_store import SaaSSecurePlatformStore


def _scope(database: Path):
    store = SaaSSecurePlatformStore(database)
    organization = store.get_or_create_organization("Semantic Org", slug="semantic-org")
    workspace = store.get_or_create_workspace(organization.organization_id, "Semantic Workspace", slug="semantic-ws")
    project = store.get_or_create_project(workspace.workspace_id, "Semantic Project", slug="semantic-project")
    prop = store.get_or_create_property(project.project_id, "Semantic Site", "https://semantic.example.test")
    environment = store.get_or_create_environment(prop.property_id, "Production", "PRODUCTION", prop.canonical_origin)
    user = store.get_or_create_user("Semantic Operator", email="semantic@example.test")
    store.add_membership(
        organization.organization_id,
        user.user_id,
        "OPERATOR",
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
    )
    return store, project, prop, environment, user


def test_property_profile_is_revisioned_and_validated(tmp_path: Path) -> None:
    store, _project, prop, _environment, user = _scope(tmp_path / "platform.db")
    try:
        initial = store.get_property_semantic_profile(prop.property_id)
        assert initial["revision"] == 0
        assert initial["business_sector"] == "auto"

        saved = store.set_property_semantic_profile(
            prop.property_id,
            business_sector="Software B2B",
            business_description="Plataforma financeira",
            primary_offering="SaaS financeiro",
            target_audience_profile="CFOs de PMEs",
            primary_goal="Gerar demonstrações",
            positioning="Simplificar controle financeiro",
            updated_by=user.user_id,
            expected_revision=0,
        )
        assert saved["revision"] == 1
        assert saved["business_sector"] == "Software B2B"

        with pytest.raises(ValueError, match="revision conflict"):
            store.set_property_semantic_profile(
                prop.property_id,
                business_sector="Outro setor",
                updated_by=user.user_id,
                expected_revision=0,
            )
    finally:
        store.close()


def test_audit_job_freezes_property_profile_and_explicit_override_wins(tmp_path: Path) -> None:
    store, project, prop, environment, user = _scope(tmp_path / "platform.db")
    try:
        store.set_property_semantic_profile(
            prop.property_id,
            business_sector="Software B2B",
            business_description="Plataforma financeira",
            primary_offering="SaaS financeiro",
            target_audience_profile="CFOs de PMEs",
            primary_goal="Gerar demonstrações",
            positioning="Simplificar controle financeiro",
            updated_by=user.user_id,
        )

        inherited = store.enqueue_execution_job(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            job_type="AUDIT",
            payload={"ai_provider": "none"},
            requested_by=user.user_id,
        )
        assert inherited.payload["property_business_sector"] == "Software B2B"
        assert inherited.payload["property_primary_offering"] == "SaaS financeiro"

        explicit = store.enqueue_execution_job(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            job_type="AUDIT",
            payload={
                "ai_provider": "none",
                "property_business_sector": "auto",
                "property_primary_goal": "Suporte ao cliente",
            },
            requested_by=user.user_id,
        )
        assert explicit.payload["property_business_sector"] == "auto"
        assert explicit.payload["property_primary_goal"] == "Suporte ao cliente"
        assert explicit.payload["property_primary_offering"] == "SaaS financeiro"

        store.set_property_semantic_profile(
            prop.property_id,
            business_sector="Serviços financeiros",
            updated_by=user.user_id,
        )
        reopened = store.get_execution_job(inherited.job_id)
        assert reopened is not None
        assert reopened.payload["property_business_sector"] == "Software B2B"
    finally:
        store.close()
