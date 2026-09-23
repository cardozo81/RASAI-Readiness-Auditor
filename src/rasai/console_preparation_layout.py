"""Preparation-layout marker for the interactive console.

The final preparation UI is installed by :mod:`rasai.console_catalog_workflow` after all
capability refinements are composed. This module remains the early composition marker
used by the console entrypoint; it contains no alternate preparation contract.
"""
from __future__ import annotations

from types import ModuleType


def install(console_module: ModuleType) -> None:
    """Mark the console as ready for the final catalog-driven preparation layer."""
    if getattr(console_module, "_rasai_canonical_preparation_layout", False):
        return
    console_module._rasai_canonical_preparation_layout = True
