"""Runtime bridge for configurable synthetic measurement profiles.

The core Apdex formulas remain untouched. This installer only resolves the selected
client/hardware/network envelopes and injects them into the existing M23/M25 runtime
configuration paths. The same environment contract is therefore honored by CLI,
interactive console and SaaS workers.
"""
from __future__ import annotations

from dataclasses import replace
import os
from typing import Any, Mapping

from rasai.m23_apdex_profiles import profile_from_presets
from rasai.synthetic_runtime_profiles import selected_profile_ids

_INSTALLED = False


def _profile_for(device: str, env: Mapping[str, str] | None = None):
    environment = env if env is not None else os.environ
    ids = selected_profile_ids(device, environment)
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
                device: selected_profile_ids(device, os.environ)
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

    # Public CLI: preserve CLI > environment > defaults and only replace the profile
    # objects in the already validated M23 configuration.
    original_cli = m23_cli.configured_apdex
    if not getattr(original_cli, "_rasai_synthetic_profiles", False):
        def configured_apdex_with_profiles(args: Any, env: Mapping[str, str] | None = None):
            result = original_cli(args, env)
            environment = env if env is not None else os.environ
            return _navigation_config_with_profiles(result, environment)

        configured_apdex_with_profiles._rasai_synthetic_profiles = True
        configured_apdex_with_profiles._rasai_original = original_cli
        m23_cli.configured_apdex = configured_apdex_with_profiles
        if getattr(cli_extensions, "configured_apdex", None) is original_cli:
            cli_extensions.configured_apdex = configured_apdex_with_profiles
        if getattr(console_m23, "configured_apdex", None) is original_cli:
            console_m23.configured_apdex = configured_apdex_with_profiles

    # Interactive console builds M23 config directly from state, so project the same
    # persisted environment presets into that path as well.
    original_console_config = console_m23.config_from_state
    if not getattr(original_console_config, "_rasai_synthetic_profiles", False):
        def config_from_state_with_profiles(state: Any):
            return _navigation_config_with_profiles(original_console_config(state), os.environ)

        config_from_state_with_profiles._rasai_synthetic_profiles = True
        config_from_state_with_profiles._rasai_original = original_console_config
        console_m23.config_from_state = config_from_state_with_profiles

    _INSTALLED = True
