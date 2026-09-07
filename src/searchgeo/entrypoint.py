"""Top-level RASAI command router.

Additive specialist commands are intercepted here. Existing audit commands are
delegated unchanged to cli_extensions, preserving the current audit pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Sequence

from searchgeo import cli_extensions
from searchgeo.report_registry import install as install_report_registry

_LOGGER = logging.getLogger(__name__)


def _audits_root(argv: list[str]) -> Path:
    for index, value in enumerate(argv):
        if value == "--audits-root" and index + 1 < len(argv):
            return Path(argv[index + 1])
        if value.startswith("--audits-root="):
            return Path(value.split("=", 1)[1])
    return Path("audits")


def _try_refresh_platform_index(argv: list[str]) -> None:
    """Best-effort post-audit control-plane indexing.

    Product metadata must never turn a successfully persisted AUD into a failed
    audit. Any platform indexing error is therefore logged and kept fail-open.
    """
    try:
        from searchgeo.platform.indexing import index_audits
        from searchgeo.platform.store import PlatformStore

        root = _audits_root(argv)
        with PlatformStore.open(root) as store:
            index_audits(store, root, strict=False)
    except Exception:
        _LOGGER.exception("RASAI platform index refresh failed after successful audit")


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
    if effective and effective[0] == "platform":
        from searchgeo.platform.cli import main as platform_main
        return platform_main(effective[1:])
    code = cli_extensions.main(effective)
    if code == 0 and effective and effective[0] == "audit":
        _try_refresh_platform_index(effective)
    return code
