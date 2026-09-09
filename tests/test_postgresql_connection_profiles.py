from __future__ import annotations

import pytest

from rasai.platform.postgres_compat import (
    PostgreSQLConfigurationError,
    redact_postgres_url,
    require_postgres_url,
)


def test_local_docker_postgresql_url_is_supported() -> None:
    value = "postgresql://rasai_app:local-secret@127.0.0.1:5432/rasai_control_plane"
    assert require_postgres_url(value) == value
    assert redact_postgres_url(value) == (
        "postgresql://rasai_app@127.0.0.1:5432/rasai_control_plane"
    )


def test_hosted_postgresql_url_preserves_tls_and_connection_parameters() -> None:
    value = (
        "postgresql://rasai_app:p%40ss%3Aword@db.example-host.net:5432/rasai_control_plane"
        "?sslmode=require&connect_timeout=10&application_name=rasai"
    )
    assert require_postgres_url(value) == value
    redacted = redact_postgres_url(value)
    assert redacted == (
        "postgresql://rasai_app@db.example-host.net:5432/rasai_control_plane"
    )
    assert "p%40ss%3Aword" not in redacted
    assert "sslmode" not in redacted


def test_postgres_scheme_alias_is_supported_for_hosted_services() -> None:
    value = "postgres://rasai_app:secret@managed-db.example.net:6543/rasai_control_plane?sslmode=verify-full"
    assert require_postgres_url(value) == value


def test_postgresql_url_requires_host_and_database_name() -> None:
    with pytest.raises(PostgreSQLConfigurationError):
        require_postgres_url("postgresql:///rasai_control_plane")
    with pytest.raises(PostgreSQLConfigurationError):
        require_postgres_url("postgresql://db.example-host.net")
