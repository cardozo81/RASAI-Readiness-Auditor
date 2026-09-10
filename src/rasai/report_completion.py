"""Final materialization and completeness gate for audit-owned HTML surfaces.

A successful URL audit must not silently leave its canonical audit report site half
materialized. This module rebuilds projections only from the immutable audit workspace;
it performs no network calls and does not recalculate scoring.

Specialist post-audit surfaces (Search Intelligence, Observability, AI Visibility and
Quality) are intentionally outside this gate because they are produced by their own
commands. Synthetic Apdex pages are required only when their persisted runs are enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Callable

from rasai.persistence import AuditWorkspace


AUDIT_ALWAYS_PAGES: tuple[str, ...] = (
    "index.html",
    "readiness.html",
    "scoring.html",
    "content-suggestions.html",
    "crawling-discovery.html",
    "accessibility.html",
    "web-performance.html",
    "remediation.html",
    "ai-usage.html",
    "references.html",
)


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
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
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
        # Some additive run tables have no explicit enabled column. Presence of a run
        # still means the corresponding report must be materialized.
        row = connection.execute(
            f"SELECT 1 FROM {table} WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
        return row is not None
    return row is not None and bool(row[0])


def expected_audit_report_pages(*, audit_id: str, workspace: AuditWorkspace) -> tuple[str, ...]:
    """Return the HTML pages owned by a normal ``rasai audit`` execution."""
    expected = list(AUDIT_ALWAYS_PAGES)
    connection = sqlite3.connect(workspace.database)
    try:
        devices = {
            str(row[0]).upper()
            for row in connection.execute(
                """SELECT DISTINCT ps.device
                   FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=? AND ps.device IS NOT NULL""",
                (audit_id,),
            ).fetchall()
        }
        if "MOBILE" in devices:
            expected.append("mobile.html")
        if "DESKTOP" in devices:
            expected.append("desktop.html")
        if _enabled_run(connection, "synthetic_apdex_runs", audit_id):
            expected.append("apdex.html")
        if _enabled_run(connection, "synthetic_ux_apdex_runs", audit_id):
            expected.append("apdex-experience.html")
    finally:
        connection.close()
    return tuple(dict.fromkeys(expected))


def inspect_audit_report_site(*, audit_id: str, workspace: AuditWorkspace) -> AuditReportCompletion:
    report_dir = workspace.root / "report"
    expected = expected_audit_report_pages(audit_id=audit_id, workspace=workspace)
    generated = tuple(sorted(path.name for path in report_dir.glob("*.html") if path.is_file())) if report_dir.is_dir() else ()
    generated_set = set(generated)
    missing = tuple(name for name in expected if name not in generated_set)
    return AuditReportCompletion(expected, generated, missing)


def finalize_audit_report_site(*, audit_id: str, workspace: AuditWorkspace) -> AuditReportCompletion:
    """Rebuild every audit-owned projection from persisted data, then validate it.

    Renderers are isolated: one reporting-domain failure does not prevent the remaining
    pages from being refreshed. The caller decides whether a missing expected page is a
    fatal process result; the audit evidence itself remains untouched.
    """
    from rasai import report_navigation
    from rasai.m20_reporting import enrich_m20_report_site
    from rasai.m21_reporting import enrich_m21_report_site
    from rasai.m23_reporting import enrich_m23_report_site
    from rasai.m24_reporting import enrich_m24_report_site
    from rasai.m25_reporting import enrich_m25_report_site
    from rasai.rasai_readiness_reporting import enrich_rasai_reporting
    from rasai.report_consistency_v2 import reconcile_report_outputs
    from rasai.report_manifest import write_report_manifest
    from rasai.report_site import materialize_report_site
    from rasai.report_validation_reconciliation import reconcile_validated_report_details
    from rasai.score_geo_004_reporting import write_score_geo_004_report

    errors: list[str] = []

    def run(label: str, function: Callable[[], object]) -> None:
        try:
            function()
        except Exception as exc:  # reporting repair must continue across domains
            errors.append(f"{label}:{type(exc).__name__}:{str(exc)[:240]}")

    # Base site first, then additive projections. All functions below are local/read-only
    # with respect to audit evidence; they materialize HTML/CSS/manifest only.
    run("base", lambda: materialize_report_site(audit_id=audit_id, workspace=workspace))
    run("content", lambda: enrich_m20_report_site(audit_id=audit_id, workspace=workspace))
    run("web-performance", lambda: enrich_m21_report_site(audit_id=audit_id, workspace=workspace))
    run("readiness", lambda: enrich_rasai_reporting(audit_id=audit_id, workspace=workspace))
    run("crawling-discovery", lambda: enrich_m24_report_site(audit_id=audit_id, workspace=workspace))

    # Synthetic reports are regenerated only if their persisted execution was enabled.
    expected_before = expected_audit_report_pages(audit_id=audit_id, workspace=workspace)
    if "apdex.html" in expected_before:
        run("apdex", lambda: enrich_m23_report_site(audit_id=audit_id, workspace=workspace))
    if "apdex-experience.html" in expected_before:
        run("apdex-experience", lambda: enrich_m25_report_site(audit_id=audit_id, workspace=workspace))

    # Scoring is rendered before the final semantic consistency pass. The consistency
    # pass must be last among report-domain enrichers because earlier renderers may
    # re-introduce legacy placeholders (for example Apdex inside Web Performance).
    run("scoring", lambda: write_score_geo_004_report(audit_id=audit_id, workspace=workspace))
    report_dir = workspace.root / "report"
    run("consistency", lambda: reconcile_report_outputs(audit_id=audit_id, workspace=workspace))
    run("navigation", lambda: report_navigation.normalize_report_navigation(report_dir))
    run("validated-presentation", lambda: reconcile_validated_report_details(audit_id=audit_id, workspace=workspace))
    run("manifest", lambda: write_report_manifest(report_dir))

    inspected = inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
    return AuditReportCompletion(
        expected_pages=inspected.expected_pages,
        generated_pages=inspected.generated_pages,
        missing_pages=inspected.missing_pages,
        renderer_errors=tuple(errors),
    )
