"""Runtime bridge for configurable synthetic measurement profiles.

The core Apdex formulas remain untouched. This installer only replaces the profile
lookup used by Synthetic User Experience Apdex and enriches its persisted configuration
with the exact client/hardware/network preset IDs used for the run.
"""
from __future__ import annotations

import os
from typing import Any

from rasai.m23_apdex_profiles import profile_from_presets
from rasai.synthetic_runtime_profiles import selected_profile_ids

_INSTALLED = False


def _profile_for(device: str):
    ids = selected_profile_ids(device, os.environ)
    return profile_from_presets(
        device=device,
        client_profile_id=ids["client"],
        hardware_profile_id=ids["hardware"],
        network_profile_id=ids["network"],
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import m25_apdex_experience as ux

    ux._profile_for_device = _profile_for

    original_as_dict = ux.ExperienceApdexConfig.as_dict

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

    ux.ExperienceApdexConfig.as_dict = as_dict_with_profiles
    _INSTALLED = True
