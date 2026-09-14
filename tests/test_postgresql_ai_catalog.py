from __future__ import annotations

import os

import pytest

from rasai.ai_catalog_control_plane import publish_model_catalog, publish_pricing_catalog
from rasai.ai_model_catalog import load_factory_model_catalog
from rasai.ai_pricing_catalog import load_factory_pricing_catalog
from rasai.platform.postgres_admin import migrate_postgres, postgres_schema_status
from rasai.platform.postgres_ai_catalog_migration import AI_CATALOG_SCHEMA_VERSION
from rasai.platform.postgres_compat import connect_postgres

POSTGRES_URL = os.getenv("RASAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="RASAI_TEST_POSTGRES_URL is not configured")


def test_postgresql_ai_catalog_schema_and_factory_publication() -> None:
    assert POSTGRES_URL is not None
    status, _ = migrate_postgres(POSTGRES_URL)
    assert status.state == "CURRENT"
    assert status.ai_catalog_current_version == AI_CATALOG_SCHEMA_VERSION
    assert postgres_schema_status(POSTGRES_URL).ai_catalog_current_version == AI_CATALOG_SCHEMA_VERSION

    connection = connect_postgres(POSTGRES_URL)
    try:
        with connection:
            connection.execute("DELETE FROM ai_job_catalog_snapshots")
            connection.execute("DELETE FROM ai_catalog_events")
            connection.execute("DELETE FROM ai_models")
            connection.execute("DELETE FROM ai_pricing_rules")
            connection.execute("DELETE FROM ai_model_catalogs")
            connection.execute("DELETE FROM ai_pricing_catalogs")
            connection.execute("DELETE FROM ai_providers")

        model_catalog = load_factory_model_catalog()
        pricing_catalog = load_factory_pricing_catalog()
        model_hash = publish_model_catalog(connection, model_catalog)
        pricing_hash = publish_pricing_catalog(connection, pricing_catalog)
        assert len(model_hash) == 64
        assert len(pricing_hash) == 64

        providers = connection.execute("SELECT COUNT(*) FROM ai_providers").fetchone()
        models = connection.execute("SELECT COUNT(*) FROM ai_models").fetchone()
        prices = connection.execute("SELECT COUNT(*) FROM ai_pricing_rules").fetchone()
        assert providers is not None and int(providers[0]) >= 8
        assert models is not None and int(models[0]) == len(model_catalog.models)
        assert prices is not None and int(prices[0]) >= len(pricing_catalog.models)
    finally:
        connection.close()
