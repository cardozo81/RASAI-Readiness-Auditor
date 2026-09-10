"""Device-context selection for user-facing audits.

The canonical default is MOBILE to minimize unnecessary rendering, traffic and
semantic-provider cost. Callers that need multiple devices must select ``both``
explicitly.
"""

from __future__ import annotations

import os

from rasai.domain import DeviceContext

DEVICE_CONTEXT_ENV = "RASAI_DEVICE_CONTEXT"
_ALLOWED = {"mobile", "desktop", "both"}


def normalize_device_context(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized not in _ALLOWED:
        raise ValueError(f"{DEVICE_CONTEXT_ENV} must be one of: mobile, desktop, both")
    return normalized


def configured_device_context(*, cli_value: str | None = None, default: str = "mobile") -> str:
    raw = cli_value if cli_value is not None else os.environ.get(DEVICE_CONTEXT_ENV, default)
    return normalize_device_context(raw)


def devices_from_context(value: str) -> tuple[DeviceContext, ...]:
    normalized = normalize_device_context(value)
    if normalized == "mobile":
        return (DeviceContext.MOBILE,)
    if normalized == "desktop":
        return (DeviceContext.DESKTOP,)
    return (DeviceContext.DESKTOP, DeviceContext.MOBILE)


def runtime_devices() -> tuple[DeviceContext, ...]:
    return devices_from_context(os.environ.get(DEVICE_CONTEXT_ENV, "mobile"))
