"""Route SERP/GSC settings to the Search owner regardless of registry source category."""
from __future__ import annotations

from typing import Any

_INSTALLED = False


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import console_ui_catalog as catalog
    from rasai.console_search_configuration_groups import context_label_for_name

    original = catalog.owner_for
    if getattr(original, "_rasai_search_owner_routing", False):
        _INSTALLED = True
        return

    def owner_for(spec: Any) -> str:
        context = context_label_for_name(str(getattr(spec, "name", "")))
        if context is not None:
            return f"Search / {context}"
        return original(spec)

    owner_for._rasai_search_owner_routing = True  # type: ignore[attr-defined]
    owner_for._rasai_original = original  # type: ignore[attr-defined]
    catalog.owner_for = owner_for
    _INSTALLED = True
