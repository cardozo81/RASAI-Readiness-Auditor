"""Top-level SearchGEO command router.

Additive specialist commands are intercepted here. Existing audit commands are
delegated unchanged to cli_extensions, preserving the current audit pipeline.
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
    if effective and effective[0] == "scoring":
        from searchgeo.score_geo_003_cli import main as scoring_main

        return scoring_main(effective[1:])
    return cli_extensions.main(effective)
