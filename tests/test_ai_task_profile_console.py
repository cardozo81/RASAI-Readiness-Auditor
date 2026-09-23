from __future__ import annotations

import pytest

from rasai import console_environment as base_environment
from rasai import console_provider_environment as provider_environment
from rasai.ai_task_profile_console import install
from rasai.ai_task_profiles import (
    DEFAULT_USER_PROFILE_FILE,
    PROFILE_FILE_ENV,
    PROFILE_SOURCE_ENV,
)


def test_task_profile_settings_join_managed_console_catalog() -> None:
    install()
    assert PROFILE_SOURCE_ENV in base_environment.ENV_NAMES
    assert PROFILE_FILE_ENV in base_environment.ENV_NAMES
    assert PROFILE_SOURCE_ENV in provider_environment.SPEC_BY_NAME
    assert PROFILE_FILE_ENV in provider_environment.SPEC_BY_NAME
    assert provider_environment.SPEC_BY_NAME[PROFILE_SOURCE_ENV].default == "auto"
    assert provider_environment.SPEC_BY_NAME[PROFILE_FILE_ENV].default == DEFAULT_USER_PROFILE_FILE
    assert provider_environment.SPEC_BY_NAME[PROFILE_SOURCE_ENV].sensitive is False
    assert provider_environment.SPEC_BY_NAME[PROFILE_FILE_ENV].sensitive is False


def test_task_profile_console_validation_is_fail_closed() -> None:
    install()
    assert base_environment._validate(PROFILE_SOURCE_ENV, "FILE") == "file"
    assert (
        base_environment._validate(PROFILE_FILE_ENV, "config/custom-personas.toml")
        == "config/custom-personas.toml"
    )
    with pytest.raises(ValueError):
        base_environment._validate(PROFILE_SOURCE_ENV, "remote")
    with pytest.raises(ValueError):
        base_environment._validate(PROFILE_FILE_ENV, "")
