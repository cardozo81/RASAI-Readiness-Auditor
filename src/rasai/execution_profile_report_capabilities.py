"""Render persisted execution-profile metadata using canonical capability terminology."""
from __future__ import annotations

from html import escape
from typing import Any, Mapping

_INSTALLED = False


def _profile_metrics(configuration: Mapping[str, Any]) -> str:
    from rasai.execution_evidence_reporting import _profile

    profile = _profile(configuration)
    if not profile:
        return (
            "<div class='metric'><small>Perfil de execução</small><strong>Personalizado / sem preset persistido</strong></div>"
            "<div class='metric'><small>Overrides após perfil</small><strong>—</strong></div>"
        )
    label = str(profile.get("label") or profile.get("profile_id") or "-")
    capabilities = ", ".join(
        str(item) for item in profile.get("capabilities", ()) if str(item)
    ) or "—"
    overrides = ", ".join(
        str(item) for item in profile.get("manual_overrides", ()) if str(item)
    ) or "nenhum"
    ai_mode = str(profile.get("ai_mode") or "-")
    return (
        f"<div class='metric'><small>Perfil de execução</small><strong>{escape(label)}</strong></div>"
        f"<div class='metric'><small>Capacidades do perfil</small><strong>{escape(capabilities)}</strong></div>"
        f"<div class='metric'><small>IA do perfil</small><strong>{escape(ai_mode)}</strong></div>"
        f"<div class='metric'><small>Overrides após perfil</small><strong>{escape(overrides)}</strong></div>"
    )


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from rasai import execution_evidence_reporting as report

    report._profile_metrics = _profile_metrics
    _INSTALLED = True
