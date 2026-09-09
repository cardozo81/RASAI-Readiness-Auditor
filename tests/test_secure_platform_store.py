from __future__ import annotations

import json
from pathlib import Path

import pytest

from rasai.platform.database import open_platform_store
from rasai.platform.secure_store import SecurePlatformStore


def test_sqlite_default_uses_shared_secure_store(tmp_path: Path) -> None:
    with open_platform_store(audits_root=tmp_path) as store:
        assert isinstance(store, SecurePlatformStore)
        org, workspace, project, prop, environment = store.ensure_local_hierarchy(
            project_name="Secure SQLite",
            origin="https://client.example",
        )

        page = store.create_page_identity(
            prop.property_id,
            "Home",
            metadata={"password": "must-not-persist", "max_tokens": 120},
        )
        assert page.metadata["password"] == "[REDACTED]"
        assert page.metadata["max_tokens"] == 120

        integration = store.add_integration(
            organization_id=org.organization_id,
            workspace_id=workspace.workspace_id,
            project_id=project.project_id,
            property_id=prop.property_id,
            provider="fixture",
            name="safe",
            secret_env="FIXTURE_API_KEY",
            configuration={"api_key_env": "FIXTURE_API_KEY", "max_tokens": 50},
        )
        assert integration.secret_env == "FIXTURE_API_KEY"
        assert integration.configuration["max_tokens"] == 50

        with pytest.raises(ValueError, match="inline secret field"):
            store.add_integration(
                organization_id=org.organization_id,
                project_id=project.project_id,
                property_id=prop.property_id,
                provider="fixture",
                name="unsafe",
                configuration={"password": "should-never-persist"},
            )

        schedule = store.add_schedule(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            name="safe-ref",
            kind="INTERVAL",
            command_argv=("job", "--api-key-env", "FIXTURE_API_KEY"),
            interval_minutes=60,
        )
        assert schedule.command_argv[-1] == "FIXTURE_API_KEY"

        with pytest.raises(ValueError, match="credential-bearing option"):
            store.add_schedule(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                name="unsafe",
                kind="INTERVAL",
                command_argv=("job", "--password", "should-never-persist"),
                interval_minutes=60,
            )

        notification_id = store.add_notification(
            alert_rule_id=None,
            comparison_id=None,
            milestone_id=None,
            status="PENDING",
            payload={"authorization": "Bearer should-never-persist", "input_tokens": 12},
            destination="NONE",
            delivery_error="password=should-never-persist",
        )
        row = store._connection.execute(
            "SELECT payload_json,delivery_error FROM notifications WHERE notification_id=?",
            (notification_id,),
        ).fetchone()
        assert row is not None
        payload = json.loads(str(row["payload_json"]))
        assert payload["authorization"] == "[REDACTED]"
        assert payload["input_tokens"] == 12
        assert "should-never-persist" not in str(row["payload_json"])
        assert "should-never-persist" not in str(row["delivery_error"])
