"""Runtime bridge for configurable synthetic measurement profiles.

The core Apdex formulas remain untouched. This installer synchronizes the effective
client/hardware/network envelopes across M23 and M25 so CLI, interactive console and
SaaS workers execute and report the same selected conditions.
"""
from __future__ import annotations

from dataclasses import replace
import os
from typing import Any, Mapping

from rasai.m23_apdex_profiles import profile_from_presets
from rasai.synthetic_runtime_profiles import configured_preset, selected_profile_ids

_INSTALLED = False
_EFFECTIVE_PROFILE_IDS: dict[str, dict[str, str]] = {}


def _ids_from_profile(profile: Any) -> dict[str, str]:
    return {
        "client": str(profile.client_profile_id),
        "hardware": str(profile.hardware_profile_id),
        "network": str(profile.network_profile_id),
    }


def _profile_ids_for(device: str, env: Mapping[str, str] | None = None) -> dict[str, str]:
    normalized = device.strip().upper()
    if env is None and normalized in _EFFECTIVE_PROFILE_IDS:
        return dict(_EFFECTIVE_PROFILE_IDS[normalized])
    environment = env if env is not None else os.environ
    return selected_profile_ids(normalized, environment)


def _profile_for(device: str, env: Mapping[str, str] | None = None):
    ids = _profile_ids_for(device, env)
    return profile_from_presets(
        device=device,
        client_profile_id=ids["client"],
        hardware_profile_id=ids["hardware"],
        network_profile_id=ids["network"],
    )


def _navigation_config_with_profiles(config: Any, env: Mapping[str, str] | None = None):
    """Return M23 config with effective Mobile/Desktop presets, formula unchanged."""
    return replace(
        config,
        mobile_profile=_profile_for("MOBILE", env),
        desktop_profile=_profile_for("DESKTOP", env),
    )


def _capture_cli_profiles(args: Any, result: Any, environment: Mapping[str, str]) -> None:
    """Keep M25 aligned with the profile precedence already resolved by M23 CLI."""
    _EFFECTIVE_PROFILE_IDS.clear()
    _EFFECTIVE_PROFILE_IDS["MOBILE"] = _ids_from_profile(result.mobile_profile)
    _EFFECTIVE_PROFILE_IDS["DESKTOP"] = _ids_from_profile(result.desktop_profile)
    _EFFECTIVE_PROFILE_IDS["TABLET"] = {
        kind: configured_preset(
            kind,
            "TABLET",
            environment,
            getattr(args, f"apdex_tablet_{kind}_profile", None),
        )
        for kind in ("client", "hardware", "network")
    }


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import cli_extensions, console_m23, m23_cli, m25_apdex_experience as ux

    # M25 resolves one profile per synthetic population device at measurement time.
    ux._profile_for_device = lambda device: _profile_for(device)

    original_as_dict = ux.ExperienceApdexConfig.as_dict
    if not getattr(original_as_dict, "_rasai_synthetic_profiles", False):
        def as_dict_with_profiles(self: Any) -> dict[str, Any]:
            result = dict(original_as_dict(self))
            result["runtime_profiles"] = {
                device: _profile_ids_for(device)
                for device in ("MOBILE", "DESKTOP", "TABLET")
            }
            result["profile_semantics"] = {
                "client": "viewport/DPR/touch plus Chromium-aligned browser identity",
                "hardware": "relative CPU slowdown through Chrome DevTools Protocol",
                "network": "controlled RTT/download/upload envelope through Chrome DevTools Protocol",
                "not_emulated": ["physical RAM", "physical GPU", "thermal state", "OS scheduler"],
            }
            return result

        as_dict_with_profiles._rasai_synthetic_profiles = True
        ux.ExperienceApdexConfig.as_dict = as_dict_with_profiles

    # M23 already resolves profile CLI > environment > defaults. Capture that effective
    # selection instead of replacing it, so explicit CLI overrides remain authoritative
    # and M25/Tablet inherits the same precedence model.
    original_cli = m23_cli.configured_apdex
    if not getattr(original_cli, "_rasai_synthetic_profiles", False):
        def configured_apdex_with_profile_capture(args: Any, env: Mapping[str, str] | None = None):
            environment = env if env is not None else os.environ
            result = original_cli(args, environment)
            _capture_cli_profiles(args, result, environment)
            return result

        configured_apdex_with_profile_capture._rasai_synthetic_profiles = True
        configured_apdex_with_profile_capture._rasai_original = original_cli
        m23_cli.configured_apdex = configured_apdex_with_profile_capture
        if getattr(cli_extensions, "configured_apdex", None) is original_cli:
            cli_extensions.configured_apdex = configured_apdex_with_profile_capture
        if getattr(console_m23, "configured_apdex", None) is original_cli:
            console_m23.configured_apdex = configured_apdex_with_profile_capture

    # The interactive console can build an M23 config directly from state during
    # validation. Project persisted environment presets into that path as well.
    original_console_config = console_m23.config_from_state
    if not getattr(original_console_config, "_rasai_synthetic_profiles", False):
        def config_from_state_with_profiles(state: Any):
            return _navigation_config_with_profiles(original_console_config(state), os.environ)

        config_from_state_with_profiles._rasai_synthetic_profiles = True
        config_from_state_with_profiles._rasai_original = original_console_config
        console_m23.config_from_state = config_from_state_with_profiles

    _INSTALLED = True
