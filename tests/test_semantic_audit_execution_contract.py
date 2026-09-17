from __future__ import annotations

import pytest

from rasai.audit_execution_contract import (
    audit_job_environment_overrides,
    audit_job_options,
    normalize_audit_job_payload,
)
from rasai.property_semantic_profile import (
    BUSINESS_DESCRIPTION_ENV,
    BUSINESS_SECTOR_ENV,
    POSITIONING_ENV,
    PRIMARY_GOAL_ENV,
    PRIMARY_OFFERING_ENV,
    TARGET_AUDIENCE_PROFILE_ENV,
)


def test_audit_job_options_expose_property_and_editorial_semantic_context() -> None:
    options = {item.name: item for item in audit_job_options()}
    for name in (
        "property_business_sector",
        "property_business_description",
        "property_primary_offering",
        "property_target_audience_profile",
        "property_primary_goal",
        "property_positioning",
        "content_risk_profile",
        "ymyl_category",
        "page_purpose",
        "intended_audience",
        "experience_requirement",
        "freshness_sensitivity",
        "content_origin",
    ):
        assert name in options
    assert options["property_business_sector"].default == "auto"
    assert options["page_purpose"].default == "auto"


def test_audit_payload_normalizes_and_projects_property_context_to_worker_environment() -> None:
    payload = {
        "property_business_sector": "Software B2B",
        "property_business_description": "Plataforma financeira empresarial",
        "property_primary_offering": "SaaS financeiro",
        "property_target_audience_profile": "CFOs de PMEs brasileiras",
        "property_primary_goal": "Gerar demonstrações",
        "property_positioning": "Menos complexidade operacional",
        "page_purpose": "product-service",
        "intended_audience": "professional",
    }
    normalized = normalize_audit_job_payload(payload)
    overrides = audit_job_environment_overrides(payload)

    assert normalized["property_business_sector"] == "Software B2B"
    assert normalized["page_purpose"] == "product-service"
    assert overrides[BUSINESS_SECTOR_ENV] == "Software B2B"
    assert overrides[BUSINESS_DESCRIPTION_ENV] == "Plataforma financeira empresarial"
    assert overrides[PRIMARY_OFFERING_ENV] == "SaaS financeiro"
    assert overrides[TARGET_AUDIENCE_PROFILE_ENV] == "CFOs de PMEs brasileiras"
    assert overrides[PRIMARY_GOAL_ENV] == "Gerar demonstrações"
    assert overrides[POSITIONING_ENV] == "Menos complexidade operacional"


def test_audit_payload_rejects_invalid_property_context_without_provider_call() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        normalize_audit_job_payload({"property_business_sector": "x" * 201})
