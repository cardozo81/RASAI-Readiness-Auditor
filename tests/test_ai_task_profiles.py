from __future__ import annotations

from pathlib import Path

import pytest

from rasai.ai_task_profile_runtime import _inject_payload
from rasai.ai_task_profiles import (
    REQUIRED_PROFILE_IDS,
    load_factory_task_profile_catalog,
    load_task_profile_catalog,
    profile_identity,
    profiles_for_improvement_domains,
    render_task_profiles,
)


def test_factory_catalog_contains_all_required_profiles() -> None:
    catalog = load_factory_task_profile_catalog()
    assert set(REQUIRED_PROFILE_IDS).issubset(catalog.profiles)
    assert catalog.profile("SECURITY_PASSIVE").version == "1.0"
    assert "security architect" in catalog.profile("SECURITY_PASSIVE").role


def test_partial_operator_file_overrides_only_selected_profile(tmp_path: Path) -> None:
    path = tmp_path / "profiles.toml"
    path.write_text(
        """
[metadata]
schema_version = 1
catalog_version = "test-override"
reference_date = "2026-09-15"
description = "test"

[profiles.SEMANTIC_READINESS]
version = "9.9"
role = "custom semantic reviewer"
objective = "custom objective"
competencies = ["semantic testing"]
guidance = "custom guidance"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    catalog = load_task_profile_catalog(path=path)
    assert catalog.profile("SEMANTIC_READINESS").version == "9.9"
    assert catalog.profile("SEMANTIC_READINESS").role == "custom semantic reviewer"
    assert catalog.profile("SOURCE_QUALITY").version == "1.0"


def test_profile_file_cannot_define_contract_or_safety_fields(tmp_path: Path) -> None:
    path = tmp_path / "profiles.toml"
    path.write_text(
        """
[metadata]
schema_version = 1
catalog_version = "invalid"
reference_date = "2026-09-15"
description = "test"

[profiles.SEMANTIC_READINESS]
version = "1"
role = "reviewer"
objective = "review"
competencies = ["semantics"]
guidance = "bounded"
safety_policy = "disabled"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="campos não suportados"):
        load_task_profile_catalog(path=path)


def test_improvement_domains_compose_specialized_profiles_without_duplicates() -> None:
    profiles = profiles_for_improvement_domains(
        ("TECHNICAL_HTML", "PERFORMANCE", "SECURITY", "BEST_PRACTICES", "ACCESSIBILITY")
    )
    assert profiles == (
        "TECHNICAL_HTML",
        "PERFORMANCE",
        "SECURITY_PASSIVE",
        "ACCESSIBILITY",
    )


def test_render_and_identity_are_versioned() -> None:
    rendered = render_task_profiles(("SOURCE_QUALITY", "SECURITY_PASSIVE"))
    ids, versions = profile_identity(("SOURCE_QUALITY", "SECURITY_PASSIVE"))
    assert "Task specialization profile: SOURCE_QUALITY (version 1.0)." in rendered
    assert "Task specialization profile: SECURITY_PASSIVE (version 1.0)." in rendered
    assert ids == "SOURCE_QUALITY,SECURITY_PASSIVE"
    assert versions == "1.0,1.0"


def test_payload_injection_preserves_normative_instructions() -> None:
    payload = {"model": "x", "instructions": "Return JSON only. Never invent evidence."}
    result = _inject_payload(payload, "SOURCE_QUALITY")
    assert result["instructions"].startswith("Task specialization profile: SOURCE_QUALITY")
    assert result["instructions"].endswith("Return JSON only. Never invent evidence.")
    assert payload["instructions"] == "Return JSON only. Never invent evidence."
