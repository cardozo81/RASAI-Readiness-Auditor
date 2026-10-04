from __future__ import annotations

import json
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
            connection.execute("DELETE FROM ai_native_pricing_policies")
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
        native_prices = connection.execute(
            "SELECT COUNT(*) FROM ai_native_pricing_policies"
        ).fetchone()
        assert providers is not None and int(providers[0]) >= 8
        assert models is not None and int(models[0]) == len(model_catalog.models)
        assert prices is not None and int(prices[0]) >= len(pricing_catalog.models)
        assert native_prices is not None
        assert int(native_prices[0]) == len(pricing_catalog.native_usage)

        mimo_rule = connection.execute(
            "SELECT conditions_json FROM ai_pricing_rules WHERE catalog_version=? AND rule_id=?",
            (pricing_catalog.metadata.catalog_version, "mimo-v2.6-flash-payg-realtime"),
        ).fetchone()
        assert mimo_rule is not None
        assert json.loads(str(mimo_rule[0])) == {
            "commercial_mode": "PAYG",
            "operation_mode": "REALTIME",
            "region": "GLOBAL",
        }

        perplexity = connection.execute(
            """SELECT pricing_model,currency,rules_json
               FROM ai_native_pricing_policies
               WHERE catalog_version=? AND provider_code='PERPLEXITY'
                 AND surface='SEARCH_API' AND native_usage_unit='PERPLEXITY_SEARCH_REQUEST'""",
            (pricing_catalog.metadata.catalog_version,),
        ).fetchone()
        assert perplexity is not None
        assert str(perplexity[0]) == "PER_REQUEST"
        assert str(perplexity[1]) == "USD"
        assert {item["rule_id"] for item in json.loads(str(perplexity[2]))} == {
            "perplexity-search-web-realtime",
            "perplexity-search-fast-realtime",
        }

        manus = connection.execute(
            """SELECT pricing_model,currency,rules_json
               FROM ai_native_pricing_policies
               WHERE catalog_version=? AND provider_code='MANUS'
                 AND surface='API_V2' AND native_usage_unit='MANUS_CREDIT'""",
            (pricing_catalog.metadata.catalog_version,),
        ).fetchone()
        assert manus is not None
        assert str(manus[0]) == "PROVIDER_CREDITS"
        assert manus[1] is None
        assert json.loads(str(manus[2])) == []
    finally:
        connection.close()
