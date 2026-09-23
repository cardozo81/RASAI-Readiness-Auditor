"""Runtime integration for persisted capture-context data.

This installer owns capture/runtime integrations whose persisted data is consumed by
scoring, diagnostics and `report-catalog/`. HTML projection is not owned here.
"""
from __future__ import annotations

from rasai.context_scope import CONTEXT_SCOPE_CONTRACT_VERSION
from rasai.device_context_capture import install as install_device_context_capture
from rasai.open_web_metrics import install as install_open_web_metrics
from rasai.synthetic_apdex_shared_runtime import install as install_synthetic_apdex_shared_runtime
from rasai.synthetic_profile_console_runtime import install as install_synthetic_profile_console_runtime
from rasai.synthetic_profile_runtime import install as install_synthetic_profile_runtime
from rasai.synthetic_profile_saas_runtime import install as install_synthetic_profile_saas_runtime

_INSTALLED = False


def install() -> None:
    """Install context data capture/persistence only."""
    global _INSTALLED
    if _INSTALLED:
        return
    install_device_context_capture()
    install_open_web_metrics()
    install_synthetic_profile_runtime()
    install_synthetic_apdex_shared_runtime()
    install_synthetic_profile_console_runtime()
    install_synthetic_profile_saas_runtime()
    _INSTALLED = True


def contract_version() -> str:
    return CONTEXT_SCOPE_CONTRACT_VERSION
