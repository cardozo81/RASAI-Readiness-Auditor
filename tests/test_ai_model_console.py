from __future__ import annotations

from rasai import console_environment as base_environment
from rasai import console_provider_environment as provider_environment
from rasai.ai_model_catalog import MODEL_FILE_ENV, MODEL_SOURCE_ENV
from rasai.ai_model_console import install


def test_model_catalog_settings_join_managed_console_catalog() -> None:
    install()
    assert MODEL_SOURCE_ENV in base_environment.ENV_NAMES
    assert MODEL_FILE_ENV in base_environment.ENV_NAMES
    assert MODEL_SOURCE_ENV in provider_environment.SPEC_BY_NAME
    assert MODEL_FILE_ENV in provider_environment.SPEC_BY_NAME
    assert provider_environment.SPEC_BY_NAME[MODEL_SOURCE_ENV].default == "factory"
    assert provider_environment.SPEC_BY_NAME[MODEL_FILE_ENV].default == "ai-models.toml"
    assert provider_environment.SPEC_BY_NAME[MODEL_SOURCE_ENV].sensitive is False
    assert provider_environment.SPEC_BY_NAME[MODEL_FILE_ENV].sensitive is False


def test_model_catalog_console_validation_is_fail_closed() -> None:
    install()
    assert base_environment._validate(MODEL_SOURCE_ENV, "FILE") == "file"
    assert base_environment._validate(MODEL_FILE_ENV, "config/ai-models.toml") == "config/ai-models.toml"

    for invalid in ("", "remote", "saas"):
        try:
            base_environment._validate(MODEL_SOURCE_ENV, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid model source accepted: {invalid!r}")
