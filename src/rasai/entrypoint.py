"""Top-level RASAi command router.

Additive specialist commands are intercepted here. Existing audit commands are
delegated unchanged to cli_extensions, preserving the current audit pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Sequence

from rasai import cli_extensions
from rasai.report_registry import install as install_report_registry
from rasai.runtime_completion_extensions import install_runtime_completion_extensions

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
        from rasai.platform.database import open_platform_store
        from rasai.platform.indexing import index_audits

        root = _audits_root(argv)
        with open_platform_store(audits_root=root) as store:
            index_audits(store, root, strict=False)
    except Exception:
        _LOGGER.exception("RASAi platform index refresh failed after successful audit")


def _run_audit_and_finalize(effective: list[str]) -> int:
    """Run one audit and materialize the current scoring method page last.

    Scoring itself still runs before recommendations. Only the HTML projection is
    deferred so the method page and canonical navigation reflect the final persisted
    report site without changing score arithmetic. The canonical report filename is
    stable across scoring-version revisions.
    """
    from rasai import m9
    from rasai import report_navigation
    from rasai.persistence import AuditWorkspace
    from rasai.score_geo_004_reporting import REPORT_FILE, write_score_geo_004_report

    original_run_audit = cli_extensions._legacy_cli.run_audit
    original_score_writer = m9.write_score_geo_004_report
    captured: list[object] = []

    def capture_run(*args, **kwargs):
        result = original_run_audit(*args, **kwargs)
        captured.append(result)
        return result

    def defer_score_report(*, audit_id: str, workspace: AuditWorkspace) -> Path:
        return workspace.root / "report" / REPORT_FILE

    cli_extensions._legacy_cli.run_audit = capture_run
    m9.write_score_geo_004_report = defer_score_report
    try:
        code = cli_extensions.main(effective)
    finally:
        cli_extensions._legacy_cli.run_audit = original_run_audit
        m9.write_score_geo_004_report = original_score_writer

    if code == 0 and captured:
        result = captured[-1]
        try:
            workspace = AuditWorkspace.open(result.audit_root)
            score_path = write_score_geo_004_report(
                audit_id=result.audit_id,
                workspace=workspace,
            )
            report_navigation.normalize_report_navigation(score_path.parent)
        except Exception:
            _LOGGER.exception("Current scoring final report projection failed")
    return code


def main(argv: Sequence[str] | None = None) -> int:
    install_report_registry()
    install_runtime_completion_extensions()
    effective = list(argv) if argv is not None else list(sys.argv[1:])
    if effective and effective[0] in {"search", "serp"}:
        from rasai.search_intelligence.cli import main as search_main
        return search_main(effective[1:])
    if effective and effective[0] in {"search-history", "search_history"}:
        from rasai.search_intelligence.history_cli import main as search_history_main
        return search_history_main(effective[1:])
    if effective and effective[0] in {"search-monitor", "search_monitor"}:
        from rasai.search_intelligence.monitoring_cli import main as search_monitor_main
        return search_monitor_main(effective[1:])
    if effective and effective[0] in {"property-config", "property_config"}:
        from rasai.property_config_cli import main as property_config_main
        return property_config_main(effective[1:])
    if effective and effective[0] == "api":
        try:
            from rasai.web.cli import main as api_main
        except ImportError as exc:
            raise SystemExit("RASAi web dependencies are not installed; install with: pip install -e '.[web]'") from exc
        return api_main(effective[1:])
    if effective and effective[0] == "worker":
        from rasai.worker_cli import main as worker_main
        return worker_main(effective[1:])
    if effective and effective[0] == "visibility":
        from rasai.m26_cli import main as visibility_main
        return visibility_main(effective[1:])
    if effective and effective[0] == "scoring":
        from rasai.score_geo_004_cli import main as scoring_main
        return scoring_main(effective[1:])
    if effective and effective[0] == "monitor":
        from rasai.monitoring.cli import main as monitoring_main
        return monitoring_main(effective[1:])
    if effective and effective[0] in {"observe", "observability"}:
        from rasai.observability.cli import main as observability_main
        return observability_main(effective[1:])
    if effective and effective[0] == "quality":
        from rasai.quality.cli import main as quality_main
        return quality_main(effective[1:])
    if effective and effective[0] == "platform":
        from rasai.platform.canonical_cli import main as platform_main
        return platform_main(effective[1:])
    if effective and effective[0] == "audit":
        code = _run_audit_and_finalize(effective)
        if code == 0:
            _try_refresh_platform_index(effective)
        return code
    return cli_extensions.main(effective)