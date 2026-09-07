"""Canonical CLI adapter for the RASAI product control plane.

The original platform CLI is kept as an additive command surface. This adapter
selects the integrity-hardened/multi-domain store without duplicating parser or
command logic. It can be removed once the canonical store becomes the only
backend implementation.
"""
from __future__ import annotations

from .central_store import CentralPlatformStore
from . import cli as _cli


def main(argv: list[str] | None = None) -> int:
    _cli.PlatformStore = CentralPlatformStore  # type: ignore[attr-defined]
    return _cli.main(argv)
