"""Composable synthetic runtime profiles for browser-dependent measurements.

These presets are operational laboratory envelopes, not population statistics and not
claims of physical-device equivalence. They make client geometry/browser identity, CPU
and network assumptions explicit, selectable and reproducible while preserving the
existing RASAi baseline as the default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from rasai.domain import DeviceContext
from rasai.rendering import BrowserProfile

PROFILE_CATALOG_VERSION = "SYNTHETIC-RUNTIME-PROFILES-001"

PROFILE_ENV = {
    ("MOBILE", "client"): "RASAI_APDEX_MOBILE_CLIENT_PROFILE",
    ("MOBILE", "hardware"): "RASAI_APDEX_MOBILE_HARDWARE_PROFILE",
    ("MOBILE", "network"): "RASAI_APDEX_MOBILE_NETWORK_PROFILE",
    ("DESKTOP", "client"): "RASAI_APDEX_DESKTOP_CLIENT_PROFILE",
    ("DESKTOP", "hardware"): "RASAI_APDEX_DESKTOP_HARDWARE_PROFILE",
    ("DESKTOP", "network"): "RASAI_APDEX_DESKTOP_NETWORK_PROFILE",
    ("TABLET", "client"): "RASAI_APDEX_TABLET_CLIENT_PROFILE",
    ("TABLET", "hardware"): "RASAI_APDEX_TABLET_HARDWARE_PROFILE",
    ("TABLET", "network"): "RASAI_APDEX_TABLET_NETWORK_PROFILE",
}
PROFILE_ENV_NAMES = tuple(PROFILE_ENV.values())


@dataclass(frozen=True, slots=True)
class ClientPreset:
    preset_id: str
    device: str
    label: str
    browser_family: str
    os_family: str
    viewport_width: int
    viewport_height: int
    device_scale_factor: float
    is_mobile: bool
    has_touch: bool
    user_agent_template: str
    playwright_descriptor: str

    def browser_profile(self) -> BrowserProfile:
        device = DeviceContext.MOBILE if self.device in {"MOBILE", "TABLET"} else DeviceContext.DESKTOP
        return BrowserProfile(
            device=device,
            viewport_width=self.viewport_width,
            viewport_height=self.viewport_height,
            user_agent=self.user_agent_template,
            device_scale_factor=self.device_scale_factor,
            is_mobile=self.is_mobile,
            has_touch=self.has_touch,
        )


@dataclass(frozen=True, slots=True)
class HardwarePreset:
    preset_id: str
    device: str
    label: str
    cpu_slowdown: float
    note: str


@dataclass(frozen=True, slots=True)
class NetworkPreset:
    preset_id: str
    device: str
    label: str
    rtt_ms: float
    download_kbps: float
    upload_kbps: float
    connection_type: str
    note: str


CLIENT_PRESETS: dict[str, ClientPreset] = {
    "mobile-compact-chromium": ClientPreset("mobile-compact-chromium", "MOBILE", "Mobile compacto · Chromium/Android", "chromium", "android", 360, 800, 3.0, True, True, "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36", "Pixel 7"),
    "mobile-balanced-chromium": ClientPreset("mobile-balanced-chromium", "MOBILE", "Mobile balanceado · Chromium/Android", "chromium", "android", 412, 915, 2.625, True, True, "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36", "Pixel 7"),
    "mobile-large-chromium": ClientPreset("mobile-large-chromium", "MOBILE", "Mobile grande · Chromium/Android", "chromium", "android", 430, 932, 3.0, True, True, "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36", "Pixel 7"),
    "desktop-1366-chromium": ClientPreset("desktop-1366-chromium", "DESKTOP", "Desktop 1366×768 · Chromium", "chromium", "desktop-runtime", 1366, 768, 1.0, False, False, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36", "Desktop Chrome"),
    "desktop-balanced-chromium": ClientPreset("desktop-balanced-chromium", "DESKTOP", "Desktop 1440×900 · Chromium", "chromium", "desktop-runtime", 1440, 900, 1.0, False, False, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36", "Desktop Chrome"),
    "desktop-wide-chromium": ClientPreset("desktop-wide-chromium", "DESKTOP", "Desktop 1920×1080 · Chromium", "chromium", "desktop-runtime", 1920, 1080, 1.0, False, False, "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36", "Desktop Chrome"),
    "tablet-compact-chromium": ClientPreset("tablet-compact-chromium", "TABLET", "Tablet 800×1280 · Chromium/Android", "chromium", "android", 800, 1280, 2.0, True, True, "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36", "Pixel 7"),
    "tablet-balanced-chromium": ClientPreset("tablet-balanced-chromium", "TABLET", "Tablet 1024×1366 · Chromium/Android", "chromium", "android", 1024, 1366, 2.0, True, True, "Mozilla/5.0 (Linux; Android 14; Pixel Tablet) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36", "Pixel 7"),
}

HARDWARE_PRESETS: dict[str, HardwarePreset] = {
    "mobile-entry": HardwarePreset("mobile-entry", "MOBILE", "Mobile entrada · CPU 6×", 6.0, "Envelope conservador de CPU móvel."),
    "mobile-balanced": HardwarePreset("mobile-balanced", "MOBILE", "Mobile balanceado · CPU 4×", 4.0, "Baseline controlado do RASAi."),
    "mobile-premium": HardwarePreset("mobile-premium", "MOBILE", "Mobile premium · CPU 2×", 2.0, "Envelope móvel de maior capacidade."),
    "desktop-constrained": HardwarePreset("desktop-constrained", "DESKTOP", "Desktop restrito · CPU 2×", 2.0, "Laptop/desktop sob restrição relativa."),
    "desktop-balanced": HardwarePreset("desktop-balanced", "DESKTOP", "Desktop balanceado · CPU 1×", 1.0, "Baseline controlado do RASAi."),
    "tablet-entry": HardwarePreset("tablet-entry", "TABLET", "Tablet entrada · CPU 4×", 4.0, "Envelope conservador de tablet."),
    "tablet-balanced": HardwarePreset("tablet-balanced", "TABLET", "Tablet balanceado · CPU 2×", 2.0, "Baseline controlado do RASAi."),
    "tablet-premium": HardwarePreset("tablet-premium", "TABLET", "Tablet premium · CPU 1×", 1.0, "Envelope de maior capacidade."),
}

NETWORK_PRESETS: dict[str, NetworkPreset] = {
    "mobile-3g-constrained": NetworkPreset("mobile-3g-constrained", "MOBILE", "Mobile 3G restrito", 300.0, 768.0, 256.0, "cellular3g", "Cenário degradado controlado."),
    "mobile-4g-balanced": NetworkPreset("mobile-4g-balanced", "MOBILE", "Mobile 4G balanceado", 150.0, 1638.4, 750.0, "cellular4g", "Baseline RASAi/Lighthouse-like conservador."),
    "mobile-4g-fast": NetworkPreset("mobile-4g-fast", "MOBILE", "Mobile 4G rápido", 80.0, 10240.0, 3072.0, "cellular4g", "Cenário 4G de maior capacidade."),
    "mobile-5g": NetworkPreset("mobile-5g", "MOBILE", "Mobile 5G", 35.0, 51200.0, 10240.0, "cellular4g", "Envelope de baixa latência/alto throughput; CDP não possui connectionType 5g."),
    "desktop-constrained": NetworkPreset("desktop-constrained", "DESKTOP", "Desktop rede restrita", 80.0, 5120.0, 2048.0, "ethernet", "Cenário corporativo/remoto restrito."),
    "desktop-balanced": NetworkPreset("desktop-balanced", "DESKTOP", "Desktop banda larga", 40.0, 10240.0, 10240.0, "ethernet", "Baseline controlado do RASAi."),
    "desktop-fiber": NetworkPreset("desktop-fiber", "DESKTOP", "Desktop fibra", 15.0, 102400.0, 51200.0, "ethernet", "Envelope de baixa latência/alto throughput."),
    "tablet-4g-balanced": NetworkPreset("tablet-4g-balanced", "TABLET", "Tablet 4G balanceado", 100.0, 4096.0, 2048.0, "cellular4g", "Baseline controlado do RASAi."),
    "tablet-wifi": NetworkPreset("tablet-wifi", "TABLET", "Tablet Wi-Fi", 40.0, 20480.0, 10240.0, "wifi", "Envelope Wi-Fi de capacidade intermediária."),
}

DEFAULT_CLIENT_PRESET = {"MOBILE": "mobile-balanced-chromium", "DESKTOP": "desktop-balanced-chromium", "TABLET": "tablet-balanced-chromium"}
DEFAULT_HARDWARE_PRESET = {"MOBILE": "mobile-balanced", "DESKTOP": "desktop-balanced", "TABLET": "tablet-balanced"}
DEFAULT_NETWORK_PRESET = {"MOBILE": "mobile-4g-balanced", "DESKTOP": "desktop-balanced", "TABLET": "tablet-4g-balanced"}


def preset_ids(kind: str, device: str) -> tuple[str, ...]:
    normalized = device.strip().upper()
    source: dict[str, Any]
    if kind == "client": source = CLIENT_PRESETS
    elif kind == "hardware": source = HARDWARE_PRESETS
    elif kind == "network": source = NETWORK_PRESETS
    else: raise KeyError(kind)
    return tuple(item.preset_id for item in source.values() if item.device == normalized)


def default_preset(kind: str, device: str) -> str:
    normalized = device.strip().upper()
    if kind == "client": return DEFAULT_CLIENT_PRESET[normalized]
    if kind == "hardware": return DEFAULT_HARDWARE_PRESET[normalized]
    if kind == "network": return DEFAULT_NETWORK_PRESET[normalized]
    raise KeyError(kind)


def env_name(kind: str, device: str) -> str:
    return PROFILE_ENV[(device.strip().upper(), kind)]


def describe_preset(kind: str, preset_id: str) -> str:
    source: dict[str, Any] = {"client": CLIENT_PRESETS, "hardware": HARDWARE_PRESETS, "network": NETWORK_PRESETS}[kind]
    return source[preset_id].label


def validate_preset(kind: str, device: str, preset_id: str) -> str:
    value = preset_id.strip()
    allowed = preset_ids(kind, device)
    if value not in allowed:
        raise ValueError(f"{kind} profile for {device.upper()} must be one of: {', '.join(allowed)}")
    return value


def configured_preset(kind: str, device: str, env: Mapping[str, str], cli_value: str | None = None) -> str:
    value = (str(cli_value).strip() if cli_value is not None else "") or (env.get(env_name(kind, device)) or "").strip() or default_preset(kind, device)
    return validate_preset(kind, device, value)


def selected_profile_ids(device: str, env: Mapping[str, str]) -> dict[str, str]:
    return {kind: configured_preset(kind, device, env) for kind in ("client", "hardware", "network")}


def compose_profile(*, device: str, client_id: str, hardware_id: str, network_id: str) -> dict[str, Any]:
    normalized = device.strip().upper()
    client = CLIENT_PRESETS.get(client_id)
    hardware = HARDWARE_PRESETS.get(hardware_id)
    network = NETWORK_PRESETS.get(network_id)
    if client is None or client.device != normalized: raise ValueError(f"client profile {client_id!r} is not valid for {normalized}")
    if hardware is None or hardware.device != normalized: raise ValueError(f"hardware profile {hardware_id!r} is not valid for {normalized}")
    if network is None or network.device != normalized: raise ValueError(f"network profile {network_id!r} is not valid for {normalized}")
    return {
        "catalog_version": PROFILE_CATALOG_VERSION,
        "device": normalized,
        "client_preset": client,
        "hardware_preset": hardware,
        "network_preset": network,
        "browser_profile": client.browser_profile(),
        "profile_id": f"RASAI_{normalized}_{client.preset_id}_{hardware.preset_id}_{network.preset_id}",
    }
