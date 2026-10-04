from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from rasai.ai_cost_policy import resolve_observed_cost
from rasai.ai_native_usage import (
    MANUS_CREDIT,
    PERPLEXITY_SEARCH_REQUEST,
    PER_REQUEST,
    PROVIDER_CREDITS,
    NativeUsageComponent,
    native_usage_totals,
)
from rasai.ai_pricing_catalog import load_factory_pricing_catalog
from rasai.catalog_report_integrations import _native_usage_display
from rasai.dynamic_ai_routing import _price_auto_attempt
from rasai.m18_ai import AttemptStatus, ProviderAttempt, ProviderUsage
from rasai.m18_persistence import M18Persistence
from rasai.persistence import AuditPersistence, AuditWorkspace
from rasai.platform.usage_ingestion import ingest_audit_usage

UTC = timezone.utc
AT = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)


def _perplexity_usage(*, billable: bool, search_type: str = "WEB") -> tuple[ProviderUsage, dict[str, str]]:
    usage = ProviderUsage(
        native_usage=(
            NativeUsageComponent(
                unit=PERPLEXITY_SEARCH_REQUEST,
                quantity=1,
                source_metric="search.request",
                component_type="REQUEST",
                billable=billable,
                observed_at=AT,
            ),
        )
    )
    return usage, {"search_type": search_type, "operation_mode": "REALTIME"}


def _base_audit(workspace: AuditWorkspace, audit_id: str) -> None:
    with AuditPersistence(workspace):
        pass
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.execute(
                """INSERT INTO audits(
                       audit_id,project_name,status,completion_status,primary_language,market,
                       max_pages,audit_mode,capabilities,limitations,created_at,started_at,
                       completed_at,auditor_version,ruleset_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    audit_id,
                    "native-usage-test",
                    "RUNNING",
                    None,
                    "pt-BR",
                    "BR",
                    1,
                    None,
                    "[]",
                    "[]",
                    AT.isoformat(),
                    AT.isoformat(),
                    None,
                    "test",
                    "test",
                ),
            )
    finally:
        connection.close()


def _persist_perplexity_attempt(workspace: AuditWorkspace, audit_id: str) -> None:
    usage, conditions = _perplexity_usage(billable=True)
    pricing = resolve_observed_cost(
        "PERPLEXITY",
        "",
        usage,
        AT,
        surface="SEARCH_API",
        runtime_conditions=conditions,
    )
    attempt = ProviderAttempt(
        provider="PERPLEXITY",
        model=None,
        reasoning_profile="NONE",
        provider_rank=999,
        attempt_index=1,
        snapshot_id="",
        url="https://example.com/",
        started_at=AT,
        finished_at=AT,
        duration_ms=1,
        status=AttemptStatus.SUCCESS,
        usage=usage,
        estimated_cost=pricing.estimated_cost,
        cost_currency=pricing.currency,
        pricing_version=pricing.pricing_version,
        pricing_context=pricing.pricing_context,
        pricing_rule_id=pricing.pricing_rule_id,
        pricing_source_reference=pricing.pricing_source_reference,
        pricing_runtime_conditions=pricing.runtime_conditions,
        surface="SEARCH_API",
        pricing_model=pricing.pricing_model,
        request_message_summary="search request",
    )
    with M18Persistence(workspace) as store:
        store.add_attempt(
            attempt_id="AIA-NATIVE-1",
            audit_id=audit_id,
            page_id=None,
            snapshot_id=None,
            url=attempt.url,
            device=None,
            attempt=attempt,
            operation="SEARCH_INTELLIGENCE",
        )


def test_factory_catalog_declares_only_materialized_native_usage_contracts() -> None:
    catalog = load_factory_pricing_catalog()
    assert catalog.metadata.catalog_version == "RASAI-PRICING-2026-10-03.7"
    perplexity = catalog.native_policy(
        "PERPLEXITY",
        "SEARCH_API",
        PERPLEXITY_SEARCH_REQUEST,
    )
    manus = catalog.native_policy("MANUS", "API_V2", MANUS_CREDIT)
    assert perplexity is not None
    assert perplexity.pricing_model == PER_REQUEST
    assert perplexity.currency == "USD"
    assert {rule.rule_id for rule in perplexity.rules} == {
        "perplexity-search-web-realtime",
        "perplexity-search-fast-realtime",
    }
    assert manus is not None
    assert manus.pricing_model == PROVIDER_CREDITS
    assert manus.currency is None
    assert manus.rules == ()


@pytest.mark.parametrize(
    ("search_type", "expected"),
    (("WEB", 0.005), ("FAST", 0.001)),
)
def test_perplexity_request_pricing_uses_native_unit_not_tokens(
    search_type: str,
    expected: float,
) -> None:
    usage, conditions = _perplexity_usage(billable=True, search_type=search_type)
    pricing = resolve_observed_cost(
        "PERPLEXITY",
        "",
        usage,
        AT,
        surface="SEARCH_API",
        runtime_conditions=conditions,
    )
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
    assert pricing.estimated_cost == pytest.approx(expected)
    assert pricing.currency == "USD"
    assert pricing.pricing_model == PER_REQUEST
    assert pricing.native_usage_unit == PERPLEXITY_SEARCH_REQUEST
    assert pricing.native_usage_quantity == pytest.approx(1.0)


def test_explicit_nonbillable_request_has_real_zero_not_invented_token_cost() -> None:
    usage, conditions = _perplexity_usage(billable=False)
    pricing = resolve_observed_cost(
        "PERPLEXITY",
        "",
        usage,
        AT,
        surface="SEARCH_API",
        runtime_conditions=conditions,
    )
    assert pricing.estimated_cost == pytest.approx(0.0)
    assert pricing.currency == "USD"
    assert pricing.pricing_rule_id == "perplexity-search-web-realtime"
    assert usage.input_tokens is None
    assert usage.output_tokens is None


def test_auto_repricing_preserves_native_surface_and_per_request_provenance() -> None:
    usage, conditions = _perplexity_usage(billable=True)
    attempt = ProviderAttempt(
        provider="PERPLEXITY",
        model=None,
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="SNP-NATIVE-AUTO",
        url="https://example.com/",
        started_at=AT,
        finished_at=AT,
        duration_ms=1,
        status=AttemptStatus.SUCCESS,
        usage=usage,
        surface="SEARCH_API",
        pricing_runtime_conditions=tuple(sorted(conditions.items())),
    )

    priced = _price_auto_attempt(attempt)

    assert priced.estimated_cost == pytest.approx(0.005)
    assert priced.cost_currency == "USD"
    assert priced.pricing_model == PER_REQUEST
    assert priced.pricing_rule_id == "perplexity-search-web-realtime"
    assert priced.surface == "SEARCH_API"


def test_auto_repricing_clears_stale_money_for_provider_credits_and_keeps_trace() -> None:
    usage = ProviderUsage(
        native_usage=(
            NativeUsageComponent(
                MANUS_CREDIT,
                12,
                "task.detail.task.credit_usage",
                "CONSUMPTION",
                None,
                AT,
            ),
        )
    )
    attempt = ProviderAttempt(
        provider="MANUS",
        model=None,
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="SNP-MANUS-AUTO",
        url="https://example.com/",
        started_at=AT,
        finished_at=AT,
        duration_ms=1,
        status=AttemptStatus.SUCCESS,
        usage=usage,
        estimated_cost=99.0,
        cost_currency="USD",
        surface="API_V2",
    )

    priced = _price_auto_attempt(attempt)

    assert priced.estimated_cost is None
    assert priced.cost_currency is None
    assert priced.pricing_model == PROVIDER_CREDITS
    assert priced.pricing_context == "UNPRICED_PROVIDER_CREDITS"
    assert priced.pricing_source_reference == "https://open.manus.ai/docs/v2/task.detail"
    assert priced.surface == "API_V2"


def test_manus_primary_credit_usage_is_unpriced_and_reconciliation_is_not_double_counted() -> None:
    components = (
        NativeUsageComponent(
            MANUS_CREDIT,
            12,
            "task.detail.task.credit_usage",
            "CONSUMPTION",
            None,
            AT,
        ),
        NativeUsageComponent(
            MANUS_CREDIT,
            12,
            "usage.list.cost",
            "RECONCILIATION",
            None,
            AT,
        ),
        NativeUsageComponent(
            MANUS_CREDIT,
            2,
            "usage.list.refund",
            "REFUND",
            False,
            AT,
        ),
        NativeUsageComponent(
            MANUS_CREDIT,
            3,
            "usage.list.grant",
            "GRANT",
            False,
            AT,
        ),
    )
    usage = ProviderUsage(native_usage=components)
    pricing = resolve_observed_cost(
        "MANUS",
        "",
        usage,
        AT,
        surface="API_V2",
    )
    assert native_usage_totals(components) == {MANUS_CREDIT: pytest.approx(12.0)}
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.total_tokens is None
    assert pricing.estimated_cost is None
    assert pricing.currency is None
    assert pricing.pricing_model == PROVIDER_CREDITS
    assert pricing.native_usage_unit == MANUS_CREDIT
    assert pricing.native_usage_quantity == pytest.approx(12.0)


def test_mixed_token_and_native_usage_fails_closed_without_speculative_composite_pricing() -> None:
    native, conditions = _perplexity_usage(billable=True)
    mixed = ProviderUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        native_usage=native.native_usage,
    )
    pricing = resolve_observed_cost(
        "PERPLEXITY",
        "",
        mixed,
        AT,
        surface="SEARCH_API",
        runtime_conditions=conditions,
    )
    assert pricing.estimated_cost is None
    assert pricing.currency is None


def test_sqlite_round_trip_preserves_native_unit_quantity_and_pricing_trace(tmp_path) -> None:
    audit_id = "AUD-NATIVE-1"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    _base_audit(workspace, audit_id)
    _persist_perplexity_attempt(workspace, audit_id)

    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        attempt = connection.execute(
            "SELECT * FROM ai_provider_attempts WHERE attempt_id='AIA-NATIVE-1'"
        ).fetchone()
        native = connection.execute(
            "SELECT * FROM ai_provider_native_usage WHERE attempt_id='AIA-NATIVE-1'"
        ).fetchone()
        snapshots = connection.execute(
            "SELECT provider,surface,native_usage_unit,pricing_model,currency "
            "FROM provider_native_pricing_catalog ORDER BY provider"
        ).fetchall()
    finally:
        connection.close()

    assert attempt is not None
    assert attempt["input_tokens"] is None
    assert attempt["output_tokens"] is None
    assert attempt["surface"] == "SEARCH_API"
    assert attempt["pricing_model"] == PER_REQUEST

    assert native is not None
    assert native["native_usage_unit"] == PERPLEXITY_SEARCH_REQUEST
    assert native["native_usage_quantity"] == pytest.approx(1.0)
    assert native["source_metric"] == "search.request"
    assert native["pricing_rule_id"] == "perplexity-search-web-realtime"
    assert native["pricing_source_reference"].startswith("https://docs.perplexity.ai/")
    assert native["estimated_cost"] == pytest.approx(0.005)

    by_provider = {row["provider"]: row for row in snapshots}
    assert by_provider["PERPLEXITY"]["native_usage_unit"] == PERPLEXITY_SEARCH_REQUEST
    assert by_provider["PERPLEXITY"]["currency"] == "USD"
    assert by_provider["MANUS"]["native_usage_unit"] == MANUS_CREDIT
    assert by_provider["MANUS"]["currency"] is None


class _CaptureStore:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_usage_once(self, **kwargs):
        self.events.append(kwargs)
        return {"usage_event_id": f"USE-{len(self.events)}"}


def test_saas_ingestion_preserves_native_quantity_without_duplicating_call_cost(tmp_path) -> None:
    audit_id = "AUD-NATIVE-SAAS"
    workspace = AuditWorkspace.create(tmp_path, audit_id)
    _base_audit(workspace, audit_id)
    _persist_perplexity_attempt(workspace, audit_id)

    store = _CaptureStore()
    audit = SimpleNamespace(
        audit_id=audit_id,
        workspace_path=str(workspace.root),
        status="COMPLETE",
        event_time=AT.isoformat(),
    )
    inserted = ingest_audit_usage(
        store,
        audit,
        organization_id="ORG-1",
        project_id="PRJ-1",
        property_id="PROP-1",
        environment_id="ENV-1",
        user_id="USR-1",
        job_id="JOB-1",
    )
    assert inserted == 2
    call = next(event for event in store.events if event["category"] == "AI_PROVIDER_CALL")
    native = next(event for event in store.events if event["category"] == "AI_NATIVE_USAGE")
    assert call["unit"] == "call"
    assert call["cost_estimate"] is None
    assert native["unit"] == PERPLEXITY_SEARCH_REQUEST
    assert native["quantity"] == pytest.approx(1.0)
    assert native["cost_estimate"] == pytest.approx(0.005)
    metadata = native["metadata"]
    assert metadata["pricing_model"] == PER_REQUEST
    assert metadata["native_usage_unit"] == PERPLEXITY_SEARCH_REQUEST
    assert metadata["native_usage_quantity"] == pytest.approx(1.0)


def test_report_humanizes_native_units_instead_of_exposing_internal_identifier() -> None:
    rendered = _native_usage_display(
        {
            "_native_usage": [{
                "native_usage_unit": PERPLEXITY_SEARCH_REQUEST,
                "native_usage_quantity": 1,
                "component_type": "REQUEST",
                "source_metric": "search.request",
            }]
        },
        include_trace=True,
    )
    assert "1 requisição de busca Perplexity" in rendered
    assert "PERPLEXITY_SEARCH_REQUEST" not in rendered
