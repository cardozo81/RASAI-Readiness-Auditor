from __future__ import annotations

import json
import os

import pytest

from rasai.platform.models import ExternalDataset
from rasai.platform.postgres_admin import migrate_postgres
from rasai.platform.postgres_store import PostgreSQLPlatformStore


POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


def _truncate(store: PostgreSQLPlatformStore) -> None:
    tables = (
        "search_monitor_runs",
        "search_monitor_queries",
        "notifications",
        "external_records",
        "external_datasets",
        "usage_events",
        "integrations",
        "alert_rules",
        "comparison_runs",
        "golden_baselines",
        "audit_scope_links",
        "page_identity_urls",
        "page_identities",
        "schedules",
        "milestones",
        "audit_index",
        "memberships",
        "environments",
        "properties",
        "projects",
        "workspaces",
        "users",
        "organizations",
    )
    store._connection.execute("TRUNCATE TABLE " + ",".join(tables) + " RESTART IDENTITY CASCADE")


def _scope(store: PostgreSQLPlatformStore):
    return store.ensure_local_hierarchy(
        project_name="Extended PostgreSQL parity",
        origin="https://client.example",
    )


def test_page_identity_alert_notification_and_integration_parity() -> None:
    assert POSTGRES_URL is not None
    migrate_postgres(POSTGRES_URL)
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _truncate(store)
        org, workspace, project, prop, environment = _scope(store)

        page = store.create_page_identity(
            prop.property_id,
            "Auto Insurance Landing",
            metadata={"password": "TEST_ONLY_PAGE_PASSWORD", "max_tokens": 512, "kind": "landing"},
        )
        assert page.metadata["password"] == "[REDACTED]"
        assert page.metadata["max_tokens"] == 512
        store.link_page_url(
            page.page_identity_id,
            environment.environment_id,
            "https://client.example/seguro-auto",
        )
        linked = store._connection.execute(
            "SELECT normalized_url FROM page_identity_urls WHERE page_identity_id=?",
            (page.page_identity_id,),
        ).fetchone()
        assert linked is not None
        assert linked["normalized_url"] == "https://client.example/seguro-auto"

        other = store.get_or_create_property(
            project.project_id,
            "Other property",
            "https://other.example",
        )
        other_env = store.get_or_create_environment(
            other.property_id,
            "production",
            "PRODUCTION",
            "https://other.example",
        )
        with pytest.raises(ValueError, match="same Property"):
            store.link_page_url(page.page_identity_id, other_env.environment_id, "https://other.example/a")

        alert = store.add_alert_rule(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            name="Material regressions",
            event_statuses=("REGRESSED", "NEW"),
            min_severity="HIGH",
            destination="WEBHOOK",
            destination_env="RASAI_ALERT_WEBHOOK_URL",
        )
        rules = store.list_alert_rules(property_id=prop.property_id, enabled_only=True)
        assert [item.alert_rule_id for item in rules] == [alert.alert_rule_id]
        assert rules[0].destination_env == "RASAI_ALERT_WEBHOOK_URL"

        notification_id = store.add_notification(
            alert_rule_id=alert.alert_rule_id,
            comparison_id=None,
            milestone_id=None,
            status="PENDING",
            payload={
                "authorization": "Bearer TEST_ONLY_BEARER_VALUE",
                "max_tokens": 256,
                "message": "regression detected",
            },
            destination="WEBHOOK",
            delivery_error="password=TEST_ONLY_ERROR_PASSWORD",
        )
        notification = store._connection.execute(
            "SELECT payload_json,delivery_error,destination FROM notifications WHERE notification_id=?",
            (notification_id,),
        ).fetchone()
        assert notification is not None
        payload = json.loads(str(notification["payload_json"]))
        assert payload["authorization"] == "[REDACTED]"
        assert payload["max_tokens"] == 256
        assert "TEST_ONLY_BEARER_VALUE" not in str(notification["payload_json"])
        assert "TEST_ONLY_ERROR_PASSWORD" not in str(notification["delivery_error"])

        integration = store.add_integration(
            organization_id=org.organization_id,
            workspace_id=workspace.workspace_id,
            project_id=project.project_id,
            property_id=prop.property_id,
            provider="generic",
            name="Provider-safe",
            secret_env="PROVIDER_API_KEY",
            configuration={
                "endpoint": "https://api.example.test",
                "api_key_env": "PROVIDER_API_KEY",
                "max_tokens": 2048,
            },
        )
        assert integration.secret_env == "PROVIDER_API_KEY"
        assert integration.configuration["max_tokens"] == 2048
        assert store.list_integrations(organization_id=org.organization_id)[0].integration_id == integration.integration_id

        with pytest.raises(ValueError, match="inline secret field"):
            store.add_integration(
                organization_id=org.organization_id,
                project_id=project.project_id,
                property_id=prop.property_id,
                provider="unsafe",
                name="Provider-unsafe",
                configuration={"api_key": "TEST_ONLY_INLINE_KEY"},
            )


def test_external_dataset_usage_and_schedule_secret_safety_parity() -> None:
    assert POSTGRES_URL is not None
    migrate_postgres(POSTGRES_URL)
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _truncate(store)
        org, _workspace, project, prop, environment = _scope(store)

        dataset = ExternalDataset(
            dataset_id="EXT-PG-SAFETY",
            organization_id=org.organization_id,
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            source_type="TEST",
            period_start="2026-09-01",
            period_end="2026-09-09",
            captured_at="2026-09-09T12:00:00+00:00",
            artifact_path=None,
            artifact_sha256=None,
            row_count=1,
            metadata={"password": "TEST_ONLY_DATASET_PASSWORD", "max_tokens": 64},
        )
        store.add_external_dataset(
            dataset,
            [{
                "record_id": "1",
                "observed_at": "2026-09-09T12:00:00+00:00",
                "normalized_url": "https://client.example/a",
                "dimensions": {"device": "desktop"},
                "metrics": {"requests": 1},
                "metadata": {"access_token": "TEST_ONLY_RECORD_TOKEN", "note": "safe"},
            }],
        )
        persisted_dataset = store.list_external_datasets(property_id=prop.property_id)[0]
        assert persisted_dataset.metadata["password"] == "[REDACTED]"
        assert persisted_dataset.metadata["max_tokens"] == 64
        record = store.external_records(dataset.dataset_id)[0]
        assert record["metadata"]["access_token"] == "[REDACTED]"
        assert record["metadata"]["note"] == "safe"

        usage = store.add_usage_event(
            organization_id=org.organization_id,
            project_id=project.project_id,
            property_id=prop.property_id,
            category="AI_CALL",
            quantity=1,
            unit="call",
            provider="fixture",
            metadata={"api_key": "TEST_ONLY_USAGE_KEY", "input_tokens": 100, "output_tokens": 20},
        )
        assert usage.metadata["api_key"] == "[REDACTED]"
        assert usage.metadata["input_tokens"] == 100
        assert usage.metadata["output_tokens"] == 20

        schedule = store.add_schedule(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            name="safe-secret-reference",
            kind="INTERVAL",
            command_argv=("integration-run", "--api-key-env", "PROVIDER_API_KEY"),
            interval_minutes=60,
        )
        assert schedule.command_argv[-1] == "PROVIDER_API_KEY"

        with pytest.raises(ValueError, match="credential-bearing option"):
            store.add_schedule(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                name="unsafe-secret-value",
                kind="INTERVAL",
                command_argv=("integration-run", "--api-key", "TEST_ONLY_RAW_API_KEY"),
                interval_minutes=60,
            )
