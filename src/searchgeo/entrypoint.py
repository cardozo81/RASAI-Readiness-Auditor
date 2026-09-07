"""Top-level RASAi command router.

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
        from searchgeo.platform.central_store import CentralPlatformStore
        from searchgeo.platform.indexing import index_audits

        root = _audits_root(argv)
        with CentralPlatformStore.open(root) as store:
            index_audits(store, root, strict=False)
    except Exception:
        _LOGGER.exception("RASAi platform index refresh failed after successful audit")


def _run_audit_and_finalize(effective: list[str]) -> int:
    """Run one audit and materialize SCORE-GEO-003 after every other report.

    Scoring itself still runs at M9, before recommendations. Only the HTML
    projection is deferred. This prevents an early method page from presenting
    a partially materialized report site while keeping score arithmetic and
    persisted evidence order unchanged.
    """
    from searchgeo import m9
    from searchgeo import report_navigation
    from searchgeo.persistence import AuditWorkspace
    from searchgeo.score_geo_003_reporting import write_score_geo_003_report

    original_run_audit = cli_extensions._legacy_cli.run_audit
    original_score_writer = m9.write_score_geo_003_report
    captured: list[object] = []

    def capture_run(*args, **kwargs):
        result = original_run_audit(*args, **kwargs)
        captured.append(result)
        return result

    def defer_score_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
        return workspace.root / "report" / "score-geo-003.html"

    cli_extensions._legacy_cli.run_audit = capture_run
    m9.write_score_geo_003_report = defer_score_report
    try:
        code = cli_extensions.main(effective)
    finally:
        cli_extensions._legacy_cli.run_audit = original_run_audit
        m9.write_score_geo_003_report = original_score_writer

    if code == 0 and captured:
        result = captured[-1]
        try:
            workspace = AuditWorkspace.open(result.audit_root)
            score_path = write_score_geo_003_report(
                audit_id=result.audit_id,
                workspace=workspace,
            )
            report_navigation.normalize_report_navigation(score_path.parent)
        except Exception:
            # Report finalization is a projection. Never invalidate the already
            # persisted audit because a static method page could not be refreshed.
            _LOGGER.exception("SCORE-GEO-003 final report projection failed")
    return code


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
        from searchgeo.platform.canonical_cli import main as platform_main
        return platform_main(effective[1:])
    if effective and effective[0] == "audit":
        code = _run_audit_and_finalize(effective)
        if code == 0:
            _try_refresh_platform_index(effective)
        return code
    return cli_extensions.main(effective)
