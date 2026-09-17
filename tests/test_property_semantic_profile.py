from __future__ import annotations

import pytest

from rasai.property_semantic_profile import (
    BUSINESS_DESCRIPTION_ENV,
    BUSINESS_SECTOR_ENV,
    POSITIONING_ENV,
    PRIMARY_GOAL_ENV,
    PRIMARY_OFFERING_ENV,
    TARGET_AUDIENCE_PROFILE_ENV,
    build_property_semantic_profile,
    configured_property_semantic_profile,
)


def test_property_semantic_profile_defaults_to_auto() -> None:
    profile = build_property_semantic_profile()
    assert profile.is_fully_auto is True
    assert profile.configured_fields == ()
    assert set(profile.auto_fields) == {
        "business_sector",
        "business_description",
        "primary_offering",
        "target_audience_profile",
        "primary_goal",
        "positioning",
    }


def test_property_semantic_profile_preserves_declared_text_as_data() -> None:
    profile = build_property_semantic_profile(
        business_sector="Software B2B",
        business_description="Plataforma de gestão financeira empresarial.",
        primary_offering="SaaS financeiro",
        target_audience_profile="CFOs e gestores financeiros de PMEs brasileiras",
        primary_goal="Gerar demonstrações qualificadas",
        positioning="Reduzir complexidade operacional financeira",
    )
    payload = profile.provider_payload()
    assert payload["business_sector"] == "Software B2B"
    assert set(payload["configured_fields"]) == {
        "business_sector",
        "business_description",
        "primary_offering",
        "target_audience_profile",
        "primary_goal",
        "positioning",
    }
    assert "untrusted contextual data" in payload["data_boundary"]


def test_property_semantic_profile_reads_environment_without_mutating_auto() -> None:
    env = {
        BUSINESS_SECTOR_ENV: "Health software",
        BUSINESS_DESCRIPTION_ENV: "auto",
        PRIMARY_OFFERING_ENV: "Clinical SaaS",
        TARGET_AUDIENCE_PROFILE_ENV: "",
        PRIMARY_GOAL_ENV: "Lead generation",
        POSITIONING_ENV: "auto",
    }
    profile = configured_property_semantic_profile(env)
    assert profile.business_sector == "Health software"
    assert profile.business_description == "auto"
    assert profile.target_audience_profile == "auto"
    assert set(profile.configured_fields) == {
        "business_sector",
        "primary_offering",
        "primary_goal",
    }


def test_property_semantic_profile_rejects_control_characters_and_oversize() -> None:
    with pytest.raises(ValueError, match="control character"):
        build_property_semantic_profile(business_sector="Software\x00Finance")
    with pytest.raises(ValueError, match="exceeds"):
        build_property_semantic_profile(business_sector="x" * 201)
