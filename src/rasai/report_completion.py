"""Final materialization and completeness gate for audit-owned HTML surfaces.

Canonical HTML existence is stable across audits. Optional collectors and data domains
remain optional, but their public surface is always expected in the final mini-site and
must render an explicit no-data/disabled state when no specialized content exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from rasai.persistence import AuditWorkspace
from rasai.report_contract import CANONICAL_FILENAMES

AUDIT_ALWAYS_PAGES: tuple[str, ...] = CANONICAL_FILENAMES


@dataclass(frozen=True, slots=True)
class AuditReportCompletion:
    expected_pages: tuple[str, ...]
    generated_pages: tuple[str, ...]
    missing_pages: tuple[str, ...]
    renderer_errors: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing_pages


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _enabled_run(connection: sqlite3.Connection, table: str, audit_id: str) -> bool:
    if not _table_exists(connection, table):
        return False
    try:
        row = connection.execute(
            f"SELECT enabled FROM {table} WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        row = connection.execute(
            f"SELECT 1 FROM {table} WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
        return row is not None
    return row is not None and bool(row[0])


def _workspace_run_enabled(*, workspace: AuditWorkspace, audit_id: str, table: str) -> bool:
    connection = sqlite3.connect(workspace.database)
    try:
        return _enabled_run(connection, table, audit_id)
    finally:
        connection.close()


def expected_audit_report_pages(*, audit_id: str, workspace: AuditWorkspace) -> tuple[str, ...]:
    """Return the stable public HTML surface set for every completed URL audit.

    ``audit_id`` and ``workspace`` remain part of the signature for API compatibility.
    They no longer determine whether a canonical page exists; capability state belongs
    inside each page rather than in the navigation/file set.
    """
    del audit_id, workspace
    return AUDIT_ALWAYS_PAGES


def inspect_audit_report_site(*, audit_id: str, workspace: AuditWorkspace) -> AuditReportCompletion:
    report_dir = workspace.root / "report"
    expected = expected_audit_report_pages(audit_id=audit_id, workspace=workspace)
    generated = (
        tuple(sorted(path.name for path in report_dir.glob("*.html") if path.is_file()))
        if report_dir.is_dir()
        else ()
    )
    generated_set = set(generated)
    missing = tuple(name for name in expected if name not in generated_set)
    return AuditReportCompletion(expected, generated, missing)


def finalize_audit_report_site(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    context_interpretations: Sequence[Any] = (),
    routing_snapshot: Mapping[str, Any] | None = None,
) -> AuditReportCompletion:
    """Rebuild persisted projections, then add execution-local presentation data."""
    from rasai import report_navigation
    from rasai.improvement_intelligence import write_improvement_report
    from rasai.m20_reporting import enrich_m20_report_site
    from rasai.m21_reporting import enrich_m21_report_site
    from rasai.m23_reporting import enrich_m23_report_site
    from rasai.m24_reporting import enrich_m24_report_site
    from rasai.m25_overview_reporting import enrich_m25_overview_summary
    from rasai.m25_reporting import enrich_m25_report_site
    from rasai.rasai_readiness_reporting import enrich_rasai_reporting
    from rasai.report_ai_cost_attribution import enrich_ai_cost_attribution
    from rasai.report_ai_runtime_enrichment import enrich_ai_runtime_report
    from rasai.report_consistency_v2 import reconcile_report_outputs
    from rasai.report_manifest import write_report_manifest
    from rasai.report_site import materialize_report_site
    from rasai.report_validation_reconciliation import reconcile_validated_report_details
    from rasai.score_geo_004_reporting import write_score_geo_004_report

    errors: list[str] = []

    def run(label: str, function: Callable[[], object]) -> None:
        try:
            function()
        except Exception as exc:
            errors.append(f"{label}:{type(exc).__name__}:{str(exc)[:240]}")

    run("base", lambda: materialize_report_site(audit_id=audit_id, workspace=workspace))
    run("content", lambda: enrich_m20_report_site(audit_id=audit_id, workspace=workspace))
    run("web-performance", lambda: enrich_m21_report_site(audit_id=audit_id, workspace=workspace))
    run("readiness", lambda: enrich_rasai_reporting(audit_id=audit_id, workspace=workspace))
    run("crawling-discovery", lambda: enrich_m24_report_site(audit_id=audit_id, workspace=workspace))

    # Optional collectors remain conditional. Only HTML existence is static.
    if _workspace_run_enabled(
        workspace=workspace, audit_id=audit_id, table="synthetic_apdex_runs"
    ):
        run("apdex", lambda: enrich_m23_report_site(audit_id=audit_id, workspace=workspace))
    if _workspace_run_enabled(
        workspace=workspace, audit_id=audit_id, table="synthetic_ux_apdex_runs"
    ):
        run("apdex-experience", lambda: enrich_m25_report_site(audit_id=audit_id, workspace=workspace))
        run(
            "apdex-experience-overview",
            lambda: enrich_m25_overview_summary(audit_id=audit_id, workspace=workspace),
        )

    run("scoring", lambda: write_score_geo_004_report(audit_id=audit_id, workspace=workspace))
    # Improvement Intelligence is audit-owned even when disabled. The writer is read-only
    # and materializes an explicit state page without creating an AI request.
    run(
        "improvement-intelligence",
        lambda: write_improvement_report(audit_id=audit_id, workspace=workspace),
    )
    report_dir = workspace.root / "report"
    run("consistency", lambda: reconcile_report_outputs(audit_id=audit_id, workspace=workspace))
    run("navigation", lambda: report_navigation.normalize_report_navigation(report_dir))
    run(
        "validated-presentation",
        lambda: reconcile_validated_report_details(audit_id=audit_id, workspace=workspace),
    )
    run(
        "ai-runtime-presentation",
        lambda: enrich_ai_runtime_report(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        ),
    )
    run(
        "ai-cost-attribution",
        lambda: enrich_ai_cost_attribution(audit_id=audit_id, workspace=workspace),
    )
    run("manifest", lambda: write_report_manifest(report_dir))

    inspected = inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
    return AuditReportCompletion(
        expected_pages=inspected.expected_pages,
        generated_pages=inspected.generated_pages,
        missing_pages=inspected.missing_pages,
        renderer_errors=tuple(errors),
    )
