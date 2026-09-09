from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import pytest

from rasai.platform.canonical_cli import main as platform_main
from rasai.platform.database import (
    PLATFORM_BACKEND_ENV,
    PLATFORM_DATABASE_URL_ENV,
    open_platform_store,
    resolve_platform_database_config,
)
from rasai.platform.postgres_admin import migrate_postgres, postgres_schema_status
from rasai.platform.postgres_compat import PostgreSQLConfigurationError, redact_postgres_url
from rasai.platform.postgres_migrations import POSTGRES_SCHEMA_VERSION
from rasai.platform.postgres_store import PostgreSQLPlatformStore
from rasai.search_intelligence.monitoring import execute_registered_query, new_query
from rasai.search_intelligence.monitoring_database import open_search_monitoring_repository


POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


@pytest.fixture(scope="module", autouse=True)
def _postgres_schema() -> None:
    if POSTGRES_URL:
        status, _applied = migrate_postgres(POSTGRES_URL)
        assert status.state == "CURRENT"
        assert status.current_version == POSTGRES_SCHEMA_VERSION


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
        project_name="PostgreSQL parity",
        origin="https://client.example",
    )


def test_postgresql_migrations_are_explicit_idempotent_and_server_contract_is_healthy() -> None:
    assert POSTGRES_URL is not None
    status_before = postgres_schema_status(POSTGRES_URL)
    assert status_before.state == "CURRENT"
    status_after, applied = migrate_postgres(POSTGRES_URL)
    assert applied == ()
    assert status_after.current_version == POSTGRES_SCHEMA_VERSION
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _truncate(store)
        health = store.health()
        assert health["backend"] == "postgresql"
        assert health["schema_version"] == POSTGRES_SCHEMA_VERSION
        assert health["server_encoding"].upper() == "UTF8"
        assert health["timezone"].upper() in {"UTC", "ETC/UTC"}
        versions = [int(row[0]) for row in store._connection.execute(
            "SELECT version FROM platform_schema_migrations ORDER BY version"
        )]
        assert versions == list(range(1, POSTGRES_SCHEMA_VERSION + 1))


def test_postgresql_database_cli_reports_and_migrates_without_exposing_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert POSTGRES_URL is not None
    monkeypatch.setenv(PLATFORM_BACKEND_ENV, "postgresql")
    monkeypatch.setenv(PLATFORM_DATABASE_URL_ENV, POSTGRES_URL)
    assert platform_main(["database", "status"]) == 0
    status_text = capsys.readouterr().out
    assert '"backend": "postgresql"' in status_text
    assert '"state": "CURRENT"' in status_text
    password = url_password(POSTGRES_URL)
    if password:
        assert password not in status_text

    assert platform_main(["database", "migrate"]) == 0
    migrate_text = capsys.readouterr().out
    assert '"applied_migrations": []' in migrate_text
    if password:
        assert password not in migrate_text


def test_postgresql_control_plane_reuses_canonical_domain_contracts() -> None:
    assert POSTGRES_URL is not None
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _truncate(store)
        org, workspace, project, prop, environment = _scope(store)
        org2, workspace2, project2, prop2, environment2 = _scope(store)
        assert org.organization_id == org2.organization_id
        assert workspace.workspace_id == workspace2.workspace_id
        assert project.project_id == project2.project_id
        assert prop.property_id == prop2.property_id
        assert environment.environment_id == environment2.environment_id

        user = store.get_or_create_user("Analyst", email="analyst@example.test")
        membership_id = store.add_membership(
            org.organization_id,
            user.user_id,
            "ANALYST",
            workspace_id=workspace.workspace_id,
            project_id=project.project_id,
        )
        assert membership_id.startswith("MBR-")
        assert len(store.list_memberships(organization_id=org.organization_id)) == 1

        schedule = store.add_schedule(
            project_id=project.project_id,
            property_id=prop.property_id,
            environment_id=environment.environment_id,
            name="weekly-search",
            kind="INTERVAL",
            command_argv=("search-monitor", "run-due"),
            interval_minutes=60,
            next_run_at="2026-09-09T10:00:00+00:00",
        )
        assert store.list_schedules()[0].schedule_id == schedule.schedule_id
        store.update_schedule_run(
            schedule.schedule_id,
            last_run_at="2026-09-09T10:00:00+00:00",
            last_status="SUCCESS",
            next_run_at="2026-09-09T11:00:00+00:00",
        )
        assert store.list_schedules()[0].last_status == "SUCCESS"

        usage = store.add_usage_event(
            organization_id=org.organization_id,
            project_id=project.project_id,
            property_id=prop.property_id,
            category="SERP_REQUEST",
            quantity=2,
            unit="request",
            provider="fixture",
        )
        assert usage.quantity == 2
        summary = store.usage_summary(org.organization_id)
        assert summary[0]["quantity"] == 2
        assert store.counts()["properties"] == 1
        assert store.data_governance_status()["database_backend"] == "postgresql"


def test_postgresql_transaction_rolls_back_domain_writes() -> None:
    assert POSTGRES_URL is not None
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _truncate(store)
        before = store.counts()["organizations"]
        with pytest.raises(RuntimeError, match="rollback proof"):
            with store.transaction() as connection:
                connection.execute(
                    "INSERT INTO organizations(organization_id,name,slug,status,created_at) VALUES(?,?,?,?,?)",
                    ("ORG-ROLLBACK", "Rollback", "rollback", "ACTIVE", "2026-09-09T00:00:00+00:00"),
                )
                raise RuntimeError("rollback proof")
        assert store.counts()["organizations"] == before


def test_search_monitoring_uses_same_postgresql_control_plane() -> None:
    assert POSTGRES_URL is not None
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fixture1 = root / "serp1.json"
        fixture2 = root / "serp2.json"
        fixture1.write_text(json.dumps({
            "fixture_version": "SERP-FIXTURE-001",
            "query": "seguro auto",
            "results": [
                {"position": 1, "url": "https://leader.example/a", "title": "Leader"},
                {"position": 7, "url": "https://client.example/auto", "title": "Client"},
            ],
        }), encoding="utf-8")
        fixture2.write_text(json.dumps({
            "fixture_version": "SERP-FIXTURE-001",
            "query": "seguro auto",
            "results": [
                {"position": 1, "url": "https://leader.example/a", "title": "Leader"},
                {"position": 4, "url": "https://client.example/auto", "title": "Client"},
            ],
        }), encoding="utf-8")

        with PostgreSQLPlatformStore(POSTGRES_URL) as store:
            _truncate(store)
            _org, _workspace, project, prop, environment = _scope(store)

        with open_search_monitoring_repository(backend="postgresql", database_url=POSTGRES_URL) as repository:
            query = repository.register_query(new_query(
                project_id=project.project_id,
                property_id=prop.property_id,
                environment_id=environment.environment_id,
                query="seguro auto",
                domain_of_interest="client.example",
                engine="google",
                country="BR",
                language="pt-BR",
                device="desktop",
                requested_depth=10,
                mode="fixture",
                provider="serpapi",
                competitive=True,
                compare_content=False,
                ai_competitive=False,
            ))
            first = execute_registered_query(repository, query, audits_root=root, fixture_path=fixture1)
            second = execute_registered_query(repository, query, audits_root=root, fixture_path=fixture2)
            assert first.snapshot.customer_position == 7
            assert second.snapshot.customer_position == 4
            assert "POSITION_IMPROVED" in {change.status for change in second.changes}
            assert len(repository.list_runs(query.query_id)) == 2

        assert not any(root.glob("AUD-*/audit.db"))
        with PostgreSQLPlatformStore(POSTGRES_URL) as store:
            assert int(store._connection.execute("SELECT COUNT(*) FROM search_monitor_queries").fetchone()[0]) == 1
            assert int(store._connection.execute("SELECT COUNT(*) FROM search_monitor_runs").fetchone()[0]) == 2


def test_backend_selection_is_explicit_and_never_silently_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert POSTGRES_URL is not None
    monkeypatch.delenv(PLATFORM_BACKEND_ENV, raising=False)
    monkeypatch.delenv(PLATFORM_DATABASE_URL_ENV, raising=False)
    config = resolve_platform_database_config(audits_root=tmp_path)
    assert config.backend == "sqlite"
    assert config.sqlite_database == tmp_path / ".rasai" / "platform.db"

    monkeypatch.setenv(PLATFORM_BACKEND_ENV, "postgresql")
    with pytest.raises(PostgreSQLConfigurationError):
        resolve_platform_database_config(audits_root=tmp_path)

    monkeypatch.setenv(PLATFORM_DATABASE_URL_ENV, POSTGRES_URL)
    config = resolve_platform_database_config(audits_root=tmp_path)
    assert config.backend == "postgresql"
    assert config.database_url == POSTGRES_URL
    assert "@" in config.display
    password = url_password(POSTGRES_URL)
    if password:
        assert password not in config.display

    with open_platform_store(backend="postgresql", database_url=POSTGRES_URL) as store:
        assert isinstance(store, PostgreSQLPlatformStore)


def url_password(url: str) -> str | None:
    from urllib.parse import urlsplit

    return urlsplit(url).password


def test_redacted_database_url_never_contains_password() -> None:
    value = "postgresql://rasai_app:super-secret@127.0.0.1:5432/rasai_control_plane"
    redacted = redact_postgres_url(value)
    assert "super-secret" not in redacted
    assert redacted == "postgresql://rasai_app@127.0.0.1:5432/rasai_control_plane"
