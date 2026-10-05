"""Device-context selection for RASAi audits.

The canonical default is MOBILE to minimize unnecessary rendering and external
provider cost. CLI and direct runtime calls use the same default contract.
"""

from __future__ import annotations

import os

from rasai.domain import DeviceContext

DEVICE_CONTEXT_ENV = "RASAI_DEVICE_CONTEXT"
_ALLOWED = {"mobile", "desktop"}
_RUNTIME_ALLOWED = {"mobile", "desktop", "both"}


def normalize_device_context(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in _ALLOWED:
        raise ValueError(f"{DEVICE_CONTEXT_ENV} must be one of: mobile, desktop")
    return normalized


def normalize_runtime_device_context(value: str) -> str:
    """Accept the historical multi-device value only for persisted/runtime recovery."""
    normalized = value.strip().casefold()
    if normalized not in _RUNTIME_ALLOWED:
        raise ValueError(f"{DEVICE_CONTEXT_ENV} runtime value must be one of: mobile, desktop, both")
    return normalized


def configured_device_context(*, cli_value: str | None = None, default: str = "mobile") -> str:
    raw = cli_value if cli_value is not None else os.environ.get(DEVICE_CONTEXT_ENV, default)
    return normalize_device_context(raw)


def devices_from_context(value: str) -> tuple[DeviceContext, ...]:
    """Resolve runtime devices, retaining read/recovery support for historical both."""
    normalized = normalize_runtime_device_context(value)
    if normalized == "mobile":
        return (DeviceContext.MOBILE,)
    if normalized == "desktop":
        return (DeviceContext.DESKTOP,)
    return (DeviceContext.DESKTOP, DeviceContext.MOBILE)




def canonical_single_device_mix(value: str) -> str:
    """Project one audit device into the legacy CAT-07 transport field."""
    normalized = normalize_device_context(value)
    if normalized == "mobile":
        return "mobile=100,desktop=0,tablet=0"
    return "mobile=0,desktop=100,tablet=0"


def runtime_devices() -> tuple[DeviceContext, ...]:
    """Return devices selected for runtime execution using the canonical MOBILE default."""
    return devices_from_context(os.environ.get(DEVICE_CONTEXT_ENV, "mobile"))