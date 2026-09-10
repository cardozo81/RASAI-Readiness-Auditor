from __future__ import annotations

import os

import pytest

from rasai.platform.identity_directory import IdentityDirectory
from rasai.platform.postgres_admin import migrate_postgres, postgres_schema_status
from rasai.platform.postgres_identity_migration import IDENTITY_SCHEMA_VERSION
from rasai.platform.postgres_store import PostgreSQLPlatformStore


POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


def test_postgresql_identity_schema_is_explicit_current_and_operational() -> None:
    assert POSTGRES_URL is not None
    status, _ = migrate_postgres(POSTGRES_URL)
    assert status.state == "CURRENT"
    assert status.identity_current_version == IDENTITY_SCHEMA_VERSION
    assert status.identity_supported_version == IDENTITY_SCHEMA_VERSION

    with PostgreSQLPlatformStore(POSTGRES_URL) as store:
        user = store.get_or_create_user("OIDC PostgreSQL", email="oidc-postgres@example.test")
        directory = IdentityDirectory(store)
        item = directory.link(
            user_id=user.user_id,
            issuer="https://login.postgres.example.test",
            subject="postgres-subject",
            email=user.email,
        )
        assert item.external_identity_id.startswith("IDN-")
        assert directory.resolve_user_id(
            issuer="https://login.postgres.example.test",
            subject="postgres-subject",
        ) == user.user_id
        assert directory.unlink(item.external_identity_id)

    status = postgres_schema_status(POSTGRES_URL)
    assert status.state == "CURRENT"
    assert status.identity_current_version == IDENTITY_SCHEMA_VERSION
