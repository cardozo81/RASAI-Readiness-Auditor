from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rasai.ai_catalog_validation import validate_catalog_alignment
from rasai.ai_model_catalog import (
    MODEL_FILE_ENV,
    MODEL_SOURCE_ENV,
    load_factory_model_catalog,
    load_model_catalog,
    restore_factory_model_catalog,
)
from rasai.ai_model_runtime import apply_model_catalog


def _new_openai_model():
    catalog = load_factory_model_catalog()
    template = catalog.model_definition("OPENAI", "gpt-5.6-luna")
    assert template is not None
    new_model = replace(
        template,
        model="gpt-5.7-test",
        public_default=False,
        adapter_default=False,
        rank=8,
        qualification="PROVISIONAL",
        rasai_class="PROVISIONAL",
        reasoning_values=("LOW", "MEDIUM"),
        default_reasoning="LOW",
        source_reference="https://example.invalid/openai-new-model",
    )
    return replace(catalog, models=(*catalog.models, new_model), source="TEST")


def test_factory_model_catalog_covers_current_integrated_providers() -> None:
    catalog = load_factory_model_catalog()
    assert catalog.metadata.schema_version == 1
    assert catalog.metadata.catalog_version == "RASAI-MODELS-2026-09-14"
    assert {
        "OPENAI", "DEEPSEEK", "MIMO", "XAI", "QWEN", "GEMINI", "ANTHROPIC", "COPILOT"
    }.issubset(set(catalog.provider_names()))
    assert catalog.public_default("OPENAI").model == "gpt-5.6-luna"
    assert catalog.adapter_default("OPENAI").model == "gpt-5.6-terra"


def test_local_model_catalog_can_be_selected_without_code_change(tmp_path: Path) -> None:
    target = restore_factory_model_catalog(tmp_path / "ai-models.toml")
    loaded = load_model_catalog(
        env={MODEL_SOURCE_ENV: "file", MODEL_FILE_ENV: str(target)},
        cwd=tmp_path,
    )
    assert loaded.catalog_models() == load_factory_model_catalog().catalog_models()
    assert loaded.source == str(target.resolve())


def test_new_model_for_existing_provider_projects_into_runtime_registry() -> None:
    from rasai import m18_ai
    from rasai.provider_registry import get_provider_registration

    factory = load_factory_model_catalog()
    try:
        apply_model_catalog(_new_openai_model())
        assert "gpt-5.7-test" in m18_ai.SUPPORTED_MODELS["OPENAI"]
        assert ("OPENAI", "gpt-5.7-test") in m18_ai._POLICY_BY_KEY
        registration = get_provider_registration("openai")
        assert registration is not None
        assert "gpt-5.7-test" in registration.supported_models
    finally:
        apply_model_catalog(factory)


def test_unknown_provider_cannot_be_created_by_model_file() -> None:
    factory = load_factory_model_catalog()
    template = factory.model_definition("OPENAI", "gpt-5.6-luna")
    assert template is not None
    unknown = replace(
        template,
        provider="NOT_INTEGRATED",
        model="new-model",
        adapter_default=True,
        public_default=True,
        source_reference="https://example.invalid/new-provider",
    )
    custom = replace(factory, models=(*factory.models, unknown), source="TEST")
    with pytest.raises(ValueError, match="provider sem adapter integrado"):
        apply_model_catalog(custom)


def test_model_specific_reasoning_is_enforced() -> None:
    from rasai.provider_runtime_policy import configured_reasoning

    factory = load_factory_model_catalog()
    try:
        apply_model_catalog(_new_openai_model())
        env = {
            "RASAI_OPENAI_MODEL": "gpt-5.7-test",
            "RASAI_OPENAI_REASONING_EFFORT": "HIGH",
        }
        with pytest.raises(ValueError, match="reasoning effort inválido"):
            configured_reasoning("OPENAI", env, model="gpt-5.7-test")
        env["RASAI_OPENAI_REASONING_EFFORT"] = "MEDIUM"
        assert configured_reasoning("OPENAI", env, model="gpt-5.7-test") == "MEDIUM"
    finally:
        apply_model_catalog(factory)


def test_auto_eligible_new_model_without_pricing_is_excluded_from_economic_auto() -> None:
    from rasai.provider_registry import get_provider_registration
    from rasai.provider_runtime_policy import _auto_model_reason

    factory = load_factory_model_catalog()
    try:
        apply_model_catalog(_new_openai_model())
        registration = get_provider_registration("openai")
        assert registration is not None
        assert _auto_model_reason(registration, "gpt-5.7-test") == "MODEL_UNPRICED_FOR_AUTO"
    finally:
        apply_model_catalog(factory)


def test_factory_model_and_pricing_catalogs_are_aligned_for_auto() -> None:
    alignment = validate_catalog_alignment()
    assert alignment.pricing_orphans == ()
    assert alignment.auto_unpriced == ()
    assert alignment.auto_eligible_models > 0
    assert alignment.priced_models >= alignment.auto_eligible_models
