from __future__ import annotations

from types import SimpleNamespace

import pytest

from rasai.m23_cli import configured_apdex
from rasai.synthetic_profile_runtime import _capture_cli_profiles, _profile_for
from rasai.synthetic_profile_saas_runtime import normalized_runtime_profiles
from rasai.synthetic_runtime_profiles import (
    PROFILE_ENV_NAMES,
    default_preset,
    preset_ids,
    selected_profile_ids,
)


def _args(**overrides):
    values = {
        "synthetic_apdex": True,
        "apdex_threshold_seconds": 1.0,
        "apdex_experience": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_catalog_defaults_are_valid_for_every_device_and_dimension() -> None:
    assert len(PROFILE_ENV_NAMES) == 9
    for device in ("MOBILE", "DESKTOP", "TABLET"):
        for kind in ("client", "hardware", "network"):
            assert default_preset(kind, device) in preset_ids(kind, device)


def test_navigation_apdex_profile_cli_overrides_environment_without_changing_formula_config() -> None:
    environment = {
        "RASAI_APDEX_MOBILE_CLIENT_PROFILE": "mobile-balanced-chromium",
        "RASAI_APDEX_MOBILE_HARDWARE_PROFILE": "mobile-entry",
        "RASAI_APDEX_MOBILE_NETWORK_PROFILE": "mobile-3g-constrained",
    }
    args = _args(
        apdex_mobile_client_profile="mobile-compact-chromium",
        apdex_mobile_hardware_profile="mobile-premium",
        apdex_mobile_network_profile="mobile-5g",
    )

    config = configured_apdex(args, environment)

    assert config.threshold_seconds == 1.0
    assert config.mobile_profile.client_profile_id == "mobile-compact-chromium"
    assert config.mobile_profile.hardware_profile_id == "mobile-premium"
    assert config.mobile_profile.network_profile_id == "mobile-5g"
    assert config.mobile_profile.cpu_slowdown == 2.0
    assert config.mobile_profile.rtt_ms == 35.0


def test_effective_cli_selection_is_reused_by_experience_including_tablet() -> None:
    environment: dict[str, str] = {}
    args = _args(
        apdex_mobile_network_profile="mobile-4g-fast",
        apdex_desktop_hardware_profile="desktop-constrained",
        apdex_tablet_client_profile="tablet-compact-chromium",
        apdex_tablet_hardware_profile="tablet-premium",
        apdex_tablet_network_profile="tablet-wifi",
    )
    config = configured_apdex(args, environment)

    _capture_cli_profiles(args, config, environment)

    assert _profile_for("MOBILE").network_profile_id == "mobile-4g-fast"
    assert _profile_for("DESKTOP").hardware_profile_id == "desktop-constrained"
    tablet = _profile_for("TABLET")
    assert tablet.client_profile_id == "tablet-compact-chromium"
    assert tablet.hardware_profile_id == "tablet-premium"
    assert tablet.network_profile_id == "tablet-wifi"


def test_saas_profile_payload_uses_same_catalog_and_rejects_cross_device_preset() -> None:
    payload = {
        "apdex_mobile_network_profile": "mobile-5g",
        "apdex_desktop_client_profile": "desktop-wide-chromium",
        "apdex_tablet_network_profile": "tablet-wifi",
    }
    normalized = normalized_runtime_profiles(payload)
    assert normalized["MOBILE"]["network"] == "mobile-5g"
    assert normalized["DESKTOP"]["client"] == "desktop-wide-chromium"
    assert normalized["TABLET"]["network"] == "tablet-wifi"

    with pytest.raises(ValueError):
        normalized_runtime_profiles({"apdex_mobile_network_profile": "desktop-fiber"})


def test_environment_defaults_remain_explicit_and_reproducible() -> None:
    mobile = selected_profile_ids("MOBILE", {})
    desktop = selected_profile_ids("DESKTOP", {})
    tablet = selected_profile_ids("TABLET", {})

    assert mobile == {
        "client": "mobile-balanced-chromium",
        "hardware": "mobile-balanced",
        "network": "mobile-4g-balanced",
    }
    assert desktop == {
        "client": "desktop-balanced-chromium",
        "hardware": "desktop-balanced",
        "network": "desktop-balanced",
    }
    assert tablet == {
        "client": "tablet-balanced-chromium",
        "hardware": "tablet-balanced",
        "network": "tablet-4g-balanced",
    }
