from __future__ import annotations

from rasai import console_environment as base_environment
from rasai import console_provider_environment as provider_environment
from rasai.ai_pricing_catalog import PRICING_FILE_ENV, PRICING_SOURCE_ENV
from rasai.ai_pricing_console import install


def test_pricing_settings_join_managed_console_catalog() -> None:
    install()
    assert PRICING_SOURCE_ENV in base_environment.ENV_NAMES
    assert PRICING_FILE_ENV in base_environment.ENV_NAMES
    assert PRICING_SOURCE_ENV in provider_environment.SPEC_BY_NAME
    assert PRICING_FILE_ENV in provider_environment.SPEC_BY_NAME
    assert provider_environment.SPEC_BY_NAME[PRICING_SOURCE_ENV].default == "factory"
    assert provider_environment.SPEC_BY_NAME[PRICING_FILE_ENV].default == "ai-pricing.toml"
    assert provider_environment.SPEC_BY_NAME[PRICING_SOURCE_ENV].sensitive is False
    assert provider_environment.SPEC_BY_NAME[PRICING_FILE_ENV].sensitive is False


def test_pricing_console_validation_is_fail_closed() -> None:
    install()
    assert base_environment._validate(PRICING_SOURCE_ENV, "FILE") == "file"
    assert base_environment._validate(PRICING_FILE_ENV, "pricing/custom.toml") == "pricing/custom.toml"

    for invalid in ("", "remote", "saas"):
        try:
            base_environment._validate(PRICING_SOURCE_ENV, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid pricing source accepted: {invalid!r}")
