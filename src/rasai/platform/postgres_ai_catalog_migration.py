"""PostgreSQL schema for administrable AI provider/model/pricing catalogs.

The control plane stores published catalog data relationally. Workers still receive
immutable per-job snapshots, so backoffice edits cannot change an in-flight audit.
"""
from __future__ import annotations

from typing import Any

from .postgres_compat import PostgresConnectionAdapter

AI_CATALOG_SCHEMA_VERSION = 1


_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS ai_catalog_schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS ai_providers (
        provider_code TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        adapter_type TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
        explicit_only INTEGER NOT NULL DEFAULT 0 CHECK (explicit_only IN (0,1)),
        credential_env TEXT NOT NULL,
        model_env TEXT NOT NULL,
        reasoning_env TEXT,
        endpoint_env TEXT,
        documentation_url TEXT,
        credential_url TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ai_model_catalogs (
        catalog_version TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        reference_date TEXT NOT NULL,
        verified_on TEXT NOT NULL,
        review_recommended_on TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('DRAFT','VALIDATED','PUBLISHED','DISABLED')),
        sha256 TEXT,
        created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
        created_at TEXT NOT NULL,
        published_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS ai_models (
        catalog_version TEXT NOT NULL REFERENCES ai_model_catalogs(catalog_version) ON DELETE CASCADE,
        provider_code TEXT NOT NULL REFERENCES ai_providers(provider_code) ON DELETE RESTRICT,
        model_code TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
        selectable INTEGER NOT NULL CHECK (selectable IN (0,1)),
        adapter_default INTEGER NOT NULL CHECK (adapter_default IN (0,1)),
        public_default INTEGER NOT NULL CHECK (public_default IN (0,1)),
        auto_eligible INTEGER NOT NULL CHECK (auto_eligible IN (0,1)),
        qualification TEXT NOT NULL,
        rasai_class TEXT NOT NULL,
        rank INTEGER NOT NULL,
        recommended_depth TEXT NOT NULL,
        recommended_use TEXT NOT NULL,
        reasoning_values_json TEXT NOT NULL,
        default_reasoning TEXT NOT NULL,
        capabilities_json TEXT NOT NULL DEFAULT '[]',
        context_window INTEGER,
        max_output_tokens INTEGER,
        effective_from TEXT,
        effective_until TEXT,
        source_reference TEXT NOT NULL,
        PRIMARY KEY(catalog_version, provider_code, model_code)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ai_models_provider ON ai_models(provider_code,catalog_version,enabled,model_code)",
    """CREATE TABLE IF NOT EXISTS ai_pricing_catalogs (
        catalog_version TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        reference_date TEXT NOT NULL,
        verified_on TEXT NOT NULL,
        review_recommended_on TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('DRAFT','VALIDATED','PUBLISHED','DISABLED')),
        sha256 TEXT,
        created_by TEXT REFERENCES users(user_id) ON DELETE SET NULL,
        created_at TEXT NOT NULL,
        published_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS ai_pricing_rules (
        catalog_version TEXT NOT NULL REFERENCES ai_pricing_catalogs(catalog_version) ON DELETE CASCADE,
        provider_code TEXT NOT NULL REFERENCES ai_providers(provider_code) ON DELETE RESTRICT,
        model_code TEXT NOT NULL,
        pricing_model TEXT NOT NULL,
        reasoning_billing TEXT NOT NULL,
        region TEXT NOT NULL,
        currency TEXT NOT NULL,
        source_reference TEXT NOT NULL,
        rule_id TEXT NOT NULL,
        context TEXT NOT NULL,
        priority INTEGER NOT NULL,
        effective_from TEXT NOT NULL,
        effective_until TEXT,
        input_tokens_gte INTEGER,
        input_tokens_gt INTEGER,
        input_tokens_lte INTEGER,
        input_tokens_lt INTEGER,
        weekdays_utc_json TEXT NOT NULL DEFAULT '[]',
        time_windows_utc_json TEXT NOT NULL DEFAULT '[]',
        input_price_per_million DOUBLE PRECISION NOT NULL,
        cached_input_price_per_million DOUBLE PRECISION NOT NULL,
        output_price_per_million DOUBLE PRECISION NOT NULL,
        PRIMARY KEY(catalog_version, rule_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ai_pricing_model ON ai_pricing_rules(provider_code,model_code,catalog_version)",
    """CREATE TABLE IF NOT EXISTS ai_job_catalog_snapshots (
        job_id TEXT PRIMARY KEY,
        model_catalog_version TEXT NOT NULL REFERENCES ai_model_catalogs(catalog_version) ON DELETE RESTRICT,
        model_catalog_sha256 TEXT NOT NULL,
        pricing_catalog_version TEXT NOT NULL REFERENCES ai_pricing_catalogs(catalog_version) ON DELETE RESTRICT,
        pricing_catalog_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS ai_catalog_events (
        event_id TEXT PRIMARY KEY,
        catalog_kind TEXT NOT NULL CHECK (catalog_kind IN ('MODEL','PRICING')),
        catalog_version TEXT NOT NULL,
        action TEXT NOT NULL,
        actor_user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
        details_json TEXT NOT NULL DEFAULT '{}',
        occurred_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ai_catalog_events_version ON ai_catalog_events(catalog_kind,catalog_version,occurred_at)",
)


def current_ai_catalog_schema_version(connection: Any) -> int:
    exists = connection.execute(
        "SELECT to_regclass('public.ai_catalog_schema_migrations') AS table_name"
    ).fetchone()
    if exists is None or exists[0] is None:
        return 0
    row = connection.execute(
        "SELECT COALESCE(MAX(version),0) AS version FROM ai_catalog_schema_migrations"
    ).fetchone()
    return int(row[0]) if row is not None else 0


def apply_ai_catalog_migrations(connection: PostgresConnectionAdapter) -> tuple[int, ...]:
    current = current_ai_catalog_schema_version(connection)
    if current > AI_CATALOG_SCHEMA_VERSION:
        raise RuntimeError(
            f"PostgreSQL AI catalog schema {current} is newer than supported {AI_CATALOG_SCHEMA_VERSION}"
        )
    if current == AI_CATALOG_SCHEMA_VERSION:
        return ()
    with connection:
        for statement in _STATEMENTS:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO ai_catalog_schema_migrations(version) VALUES(?) ON CONFLICT(version) DO NOTHING",
            (AI_CATALOG_SCHEMA_VERSION,),
        )
    return (AI_CATALOG_SCHEMA_VERSION,)


def require_current_ai_catalog_schema(connection: Any) -> int:
    version = current_ai_catalog_schema_version(connection)
    if version != AI_CATALOG_SCHEMA_VERSION:
        raise RuntimeError(
            "PostgreSQL AI catalog schema is not current "
            f"(current={version}, supported={AI_CATALOG_SCHEMA_VERSION}); "
            "run 'rasai platform database migrate' before starting the PostgreSQL backend"
        )
    return version
