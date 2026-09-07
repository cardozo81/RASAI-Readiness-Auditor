"""Top-level RASAI command router.

Additive specialist commands are intercepted here. Existing audit commands are
delegated unchanged to cli_extensions, preserving the current audit pipeline.
"""
from __future__ import annotations

import sys
from typing import Sequence

from searchgeo import cli_extensions
from searchgeo.report_registry import install as install_report_registry


def main(argv: Sequence[str] | None = None) -> int:
    install_report_registry()
    effective = list(argv) if argv is not None else list(sys.argv[1:])
    if effective and effective[0] == "visibility":
        from searchgeo.m26_cli import main as visibility_main
        return visibility_main(effective[1:])
    if effective and effective[0] == "scoring":
        from searchgeo.score_geo_003_cli import main as scoring_main
        return scoring_main(effective[1:])
    if effective and effective[0] == "monitor":
        from searchgeo.monitoring.cli import main as monitoring_main
        return monitoring_main(effective[1:])
    if effective and effective[0] in {"observe", "observability"}:
        from searchgeo.observability.cli import main as observability_main
        return observability_main(effective[1:])
    if effective and effective[0] == "quality":
        from searchgeo.quality.cli import main as quality_main
        return quality_main(effective[1:])
    return cli_extensions.main(effective)
