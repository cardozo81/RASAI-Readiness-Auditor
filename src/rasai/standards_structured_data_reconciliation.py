"""Derived structured-data readiness reconciliation.

BR-GEO-035 already determines whether structured-data types and relevant properties are
identifiable when the rule is applicable. This module exposes that deterministic result
as an advisory aggregate without pretending to measure Schema.org required/recommended
property completeness and without changing SARI-001/SCORE-GEO-004.
"""
from __future__ import annotations

from html import escape
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _record, load_metrics
from rasai.standards_service_registry import service

_METRIC_ID = "structured_data_type_property_identifiability_rate"
_RULE_ID = "BR-GEO-035"


def reconcile_structured_data_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Materialize BR-GEO-035 as an explicit aggregate over determinate executions."""

    item = service("derived-readiness")
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if not {"standards_metric_observations", "standards_service_runs", "rule_executions"}.issubset(tables):
            return
        enabled = connection.execute(
            """SELECT effective_enabled FROM standards_service_runs
               WHERE audit_id=? AND service_id='derived-readiness'""",
            (audit_id,),
        ).fetchone()
        if enabled is None or not bool(enabled[0]):
            return

        rows = connection.execute(
            """SELECT result FROM rule_executions
               WHERE audit_id=? AND rule_id=? AND result IN ('PASS','FAIL','WARNING')""",
            (audit_id, _RULE_ID),
        ).fetchall()
        determinate = len(rows)
        passed = sum(str(row["result"]) == "PASS" for row in rows)
        value = None if determinate == 0 else round(passed * 100.0 / determinate, 3)

        with connection:
            connection.execute(
                "DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id=?",
                (audit_id, _METRIC_ID),
            )
            _record(
                connection,
                audit_id=audit_id,
                metric_id=_METRIC_ID,
                label="Structured Data Type/Property Identifiability Rate",
                scope="DEVICE_SNAPSHOT",
                state="NO_DATA" if value is None else "MEASURED",
                value=value,
                numerator=float(passed),
                denominator=float(determinate),
                unit="percent",
                source="RASAi RuleExecutions",
                methodology=f"{_RULE_ID} PASS / determinate applicable executions",
                relation_degree=item.relation_degree,
                details={
                    "rule_id": _RULE_ID,
                    "boundary": (
                        "Measures whether types and relevant properties are identifiable. "
                        "It does not claim Schema.org required/recommended-property completeness."
                    ),
                },
            )
    finally:
        connection.close()


def enrich_structured_data_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    row = next(
        (
            item for item in load_metrics(audit_id, workspace)
            if str(item["metric_id"]) == _METRIC_ID
        ),
        None,
    )
    if row is None:
        return
    card = (
        "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
        + _fmt_metric(row)
        + "</strong><span>DEVICE_SNAPSHOT · BR-GEO-035 determinável</span></div>"
    )
    _insert_panel(
        workspace.root / "report" / "crawling-discovery.html",
        "RASAI_STRUCTURED_DATA_IDENTIFIABILITY",
        "<section class='panel'><h2>Dados estruturados · tipos e propriedades</h2>"
        "<p>Consolidação determinística de BR-GEO-035. Mede identificabilidade dos tipos e propriedades relevantes "
        "quando a regra é aplicável; não afirma completude de propriedades obrigatórias/recomendadas de Schema.org.</p>"
        "<div class='metric-grid'>" + card + "</div>"
        "<p><a href='standards.html'>Abrir metodologia e métricas de referência</a></p></section>",
    )


def install() -> None:
    """Reconcile the metric after base standards materialization and refresh projections."""

    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_metrics import write_standards_report

    if getattr(report_completion, "_rasai_structured_data_metric_reconciliation", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_structured_data_metric(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            reconcile_structured_data_metrics(audit_id=audit_id, workspace=workspace)
            write_standards_report(audit_id=audit_id, workspace=workspace)
            enrich_structured_data_report(audit_id=audit_id, workspace=workspace)
            report_dir = workspace.root / "report"
            report_navigation.normalize_report_navigation(report_dir)
            enhance_report_directory(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"structured-data-metrics:{type(exc).__name__}:{str(exc)[:400]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_structured_data_metric
    report_completion._rasai_structured_data_metric_reconciliation = True
