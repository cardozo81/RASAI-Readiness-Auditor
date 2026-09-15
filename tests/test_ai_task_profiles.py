from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from rasai.ai_task_profile_runtime import _inject_payload
from rasai.ai_task_profiles import (
    PROFILE_FILE_ENV,
    PROFILE_SOURCE_ENV,
    REQUIRED_PROFILE_IDS,
    active_task_profile_catalog,
    load_factory_task_profile_catalog,
    load_task_profile_catalog,
    profile_identity,
    profiles_for_improvement_domains,
    render_task_profiles,
    restore_factory_task_profile_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_semantic_override(path: Path, *, version: str, role: str = "custom semantic reviewer") -> None:
    path.write_text(
        f"""
[metadata]
schema_version = 1
catalog_version = "test-override-{version}"
reference_date = "2026-09-15"
description = "test"

[profiles.SEMANTIC_READINESS]
version = "{version}"
role = "{role}"
objective = "custom objective"
competencies = ["semantic testing"]
guidance = "custom guidance"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_factory_catalog_contains_all_required_profiles() -> None:
    catalog = load_factory_task_profile_catalog()
    assert set(REQUIRED_PROFILE_IDS).issubset(catalog.profiles)
    assert catalog.profile("SECURITY_PASSIVE").version == "1.0"
    assert "security architect" in catalog.profile("SECURITY_PASSIVE").role


def test_repository_operator_catalog_is_sparse_by_default() -> None:
    document = tomllib.loads((ROOT / "config" / "ai-task-profiles.toml").read_text(encoding="utf-8"))
    assert document["profiles"] == {}

    effective = load_task_profile_catalog(path=ROOT / "config" / "ai-task-profiles.toml")
    factory = load_factory_task_profile_catalog()
    assert effective.profiles == factory.profiles


def test_factory_catalog_can_reconstruct_an_editable_profile_file(tmp_path: Path) -> None:
    target = restore_factory_task_profile_catalog(tmp_path / "profiles.toml")
    restored = load_task_profile_catalog(path=target)
    factory = load_factory_task_profile_catalog()
    assert restored.profiles == factory.profiles


def test_partial_operator_file_overrides_only_selected_profile(tmp_path: Path) -> None:
    path = tmp_path / "profiles.toml"
    _write_semantic_override(path, version="9.9")

    catalog = load_task_profile_catalog(path=path)
    assert catalog.profile("SEMANTIC_READINESS").version == "9.9"
    assert catalog.profile("SEMANTIC_READINESS").role == "custom semantic reviewer"
    assert catalog.profile("SOURCE_QUALITY").version == "1.0"


def test_active_catalog_reloads_operator_edits_without_process_restart(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "profiles.toml"
    _write_semantic_override(path, version="1.1-user", role="first custom role")
    monkeypatch.setenv(PROFILE_SOURCE_ENV, "file")
    monkeypatch.setenv(PROFILE_FILE_ENV, str(path))

    first = active_task_profile_catalog()
    assert first.profile("SEMANTIC_READINESS").version == "1.1-user"
    assert first.profile("SEMANTIC_READINESS").role == "first custom role"

    _write_semantic_override(path, version="1.2-user", role="updated custom role")

    second = active_task_profile_catalog()
    assert second.profile("SEMANTIC_READINESS").version == "1.2-user"
    assert second.profile("SEMANTIC_READINESS").role == "updated custom role"


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
