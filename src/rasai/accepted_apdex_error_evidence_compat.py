"""Compatibility hooks for the additive M25 error-evidence proxy layer."""
from __future__ import annotations

from typing import Any


def install() -> None:
    from rasai import accepted_apdex_error_evidence as evidence

    if getattr(evidence._ContextProxy, "_rasai_cdp_unwrap", False):
        return

    def new_cdp_session(self: Any, page: Any) -> Any:
        real_page = getattr(page, "_page", page)
        return self._context.new_cdp_session(real_page)

    evidence._ContextProxy.new_cdp_session = new_cdp_session
    evidence._ContextProxy._rasai_cdp_unwrap = True


__all__ = ["install"]
