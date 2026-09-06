"""Top-level SearchGEO command router.

Only the additive M26 `visibility` command is intercepted here. Every existing
command is delegated unchanged to cli_extensions, preserving the current audit
pipeline and its M23/M24/provider behavior.
"""
from __future__ import annotations

import sys
from typing import Sequence

from searchgeo import cli_extensions


def main(argv: Sequence[str] | None = None) -> int:
    effective = list(argv) if argv is not None else list(sys.argv[1:])
    if effective and effective[0] == "visibility":
        from searchgeo.m26_cli import main as visibility_main

        return visibility_main(effective[1:])
    return cli_extensions.main(effective)
