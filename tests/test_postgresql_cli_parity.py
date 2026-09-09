from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

import pytest

from rasai.platform.canonical_cli import main as platform_main
from rasai.platform.database import PLATFORM_BACKEND_ENV, PLATFORM_DATABASE_URL_ENV
from rasai.platform.postgres_admin import migrate_postgres
from rasai.platform.postgres_store import PostgreSQLPlatformStore
from rasai.search_intelligence.monitoring_cli import main as search_monitor_main


POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


def _reset(store: PostgreSQLPlatformStore) -> None:
    store._connection.execute(
        """TRUNCATE TABLE
           search_monitor_runs,search_monitor_queries,notifications,external_records,
           external_datasets,usage_events,integrations,alert_rules,comparison_runs,
           golden_baselines,audit_scope_links,page_identity_urls,page_identities,
           schedules,milestones,audit_index,memberships,environments,properties,
           projects,workspaces,users,organizations RESTART IDENTITY CASCADE"""
    )


def _select_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    assert POSTGRES_URL is not None
    monkeypatch.setenv(PLATFORM_BACKEND_ENV, "postgresql")
    monkeypatch.setenv(PLATFORM_DATABASE_URL_ENV, POSTGRES_URL)


def test_platform_public_cli_uses_postgresql_backend(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert POSTGRES_URL is not None
    migrate_postgres(POSTGRES_URL)
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _reset(store)
    _select_postgres(monkeypatch)

    assert platform_main(["org", "add", "--name", "CLI Organization", "--slug", "cli-org"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["slug"] == "cli-org"

    assert platform_main(["user", "add", "--name", "CLI Analyst", "--email", "cli@example.test"]) == 0
    user = json.loads(capsys.readouterr().out)
    assert user["email"] == "cli@example.test"

    assert platform_main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["counts"]["organizations"] == 1
    assert "postgresql://" in status["database"]
    password = _password(POSTGRES_URL)
    if password:
        assert password not in json.dumps(status)

    assert platform_main(["data", "status"]) == 0
    governance = json.loads(capsys.readouterr().out)
    assert governance["database_backend"] == "postgresql"
    if password:
        assert password not in json.dumps(governance)


def test_search_monitor_public_cli_uses_postgresql_registry(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert POSTGRES_URL is not None
    migrate_postgres(POSTGRES_URL)
    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        _reset(store)
        _org, _workspace, project, prop, environment = store.ensure_local_hierarchy(
            project_name="CLI Search",
            origin="https://client.example",
        )
    _select_postgres(monkeypatch)

    with tempfile.TemporaryDirectory() as directory:
        audits_root = Path(directory)
        assert search_monitor_main([
            "--audits-root", str(audits_root),
            "query", "add",
            "--project", project.project_id,
            "--property", prop.property_id,
            "--environment", environment.environment_id,
            "--query", "seguro auto",
            "--domain", "client.example",
            "--mode", "fixture",
            "--provider", "serpapi",
        ]) == 0
        add_output = capsys.readouterr().out
        query_id = next(
            line.split("=", 1)[1].strip()
            for line in add_output.splitlines()
            if line.startswith("query_id=")
        )
        # Preserve the public SEARCH-MONITOR-001 identifier contract already used
        # by the SQLite implementation; PostgreSQL must not introduce a new ID family.
        assert query_id.startswith("SQRY-")

        assert search_monitor_main([
            "--audits-root", str(audits_root),
            "query", "list",
        ]) == 0
        listing = capsys.readouterr().out
        assert query_id in listing
        assert "seguro auto" in listing

        assert search_monitor_main([
            "--audits-root", str(audits_root),
            "run", "--query-id", query_id, "--dry-run",
        ]) == 0
        dry_run = capsys.readouterr().out
        assert "SERP HTTP request ceiling=" in dry_run
        assert "AI provider call ceiling=0" in dry_run

    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        row = store._connection.execute(
            "SELECT query,domain_of_interest FROM search_monitor_queries WHERE query_id=?",
            (query_id,),
        ).fetchone()
        assert row is not None
        assert row["query"] == "seguro auto"
        assert row["domain_of_interest"] == "client.example"


def test_postgresql_backend_rejects_sqlite_path_override(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _select_postgres(monkeypatch)
    code = platform_main(["--platform-db", "should-not-be-used.db", "status"])
    assert code == 2
    error = capsys.readouterr().err
    assert "SQLite-only" in error
    assert "fallback" not in error.casefold()


def _password(url: str) -> str | None:
    from urllib.parse import urlsplit

    return urlsplit(url).password
