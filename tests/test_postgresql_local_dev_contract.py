from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_postgresql_compose_is_pinned_private_and_persistent() -> None:
    compose = (ROOT / "compose.postgres.yml").read_text(encoding="utf-8")
    assert "image: postgres:18" in compose
    assert "container_name: rasai-postgres-dev" in compose
    assert '127.0.0.1:${POSTGRES_HOST_PORT:-5432}:5432' in compose
    assert "rasai_postgres_data:/var/lib/postgresql" in compose
    assert "name: rasai_postgres_data" in compose
    assert "pg_isready" in compose
    assert 'POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:' in compose
    assert "platform database migrate" not in compose
    assert "docker-entrypoint-initdb.d" not in compose


def test_local_environment_template_is_safe_and_runtime_overlay_is_ignored() -> None:
    template = (ROOT / ".env.postgres.example").read_text(encoding="utf-8")
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "POSTGRES_DB=rasai_control_plane" in template
    assert "POSTGRES_USER=rasai_app" in template
    assert "POSTGRES_PASSWORD=CHANGE_ME_GENERATE_LOCALLY" in template
    assert "POSTGRES_HOST_PORT=5432" in template
    assert ".env.*" in ignore
    assert "!.env.*.example" in ignore


def test_windows_helpers_keep_start_stop_safe_and_reset_explicitly_destructive() -> None:
    start = (ROOT / "scripts" / "postgres" / "start.ps1").read_text(encoding="utf-8")
    stop = (ROOT / "scripts" / "postgres" / "stop.ps1").read_text(encoding="utf-8")
    status = (ROOT / "scripts" / "postgres" / "status.ps1").read_text(encoding="utf-8")
    reset = (ROOT / "scripts" / "postgres" / "reset.ps1").read_text(encoding="utf-8")

    assert ".env.postgres.local" in start
    assert "RandomNumberGenerator" in start
    assert "5432" in start and "5433" in start
    assert "docker compose" in start
    assert " up -d" in start
    assert "platform database migrate" not in start
    assert "POSTGRES_PASSWORD=$password" in start
    assert "Write-Host $password" not in start

    assert "docker compose" in stop
    assert " down" in stop
    assert " down -v" not in stop

    assert "pg_isready" in status
    assert "server_encoding" in status
    assert "timezone" in status.casefold()
    assert "SELECT version();" in status

    assert "[switch]$ConfirmReset" in reset
    assert "if (-not $ConfirmReset)" in reset
    assert " down -v" in reset
    assert ".env.postgres.local será preservado" in reset


def test_local_postgresql_documentation_preserves_sqlite_and_aud_boundaries() -> None:
    doc = (ROOT / "docs" / "POSTGRESQL_LOCAL_DEVELOPMENT.md").read_text(encoding="utf-8")
    assert "SQLite continua sendo o default" in doc
    assert "RASAI_PLATFORM_DB_BACKEND" in doc
    assert "RASAI_PLATFORM_DATABASE_URL" in doc
    assert "AUD-*/audit.db" in doc
    assert "SARI-001" in doc
    assert "SCORE-GEO-004" in doc
    assert "rasai platform database migrate" in doc
