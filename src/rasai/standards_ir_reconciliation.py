"""Strict Information Retrieval reconciliation for standards metrics.

Unjudged results are never converted to non-relevant documents. Precision/MRR require a
fully judged observed top 10; nDCG additionally requires an explicit ideal relevance
vector; Recall additionally requires an explicit total relevant denominator.
"""
from __future__ import annotations

import json
import math
import sqlite3
from statistics import fmean
from typing import Any, Iterable, Mapping

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _record
from rasai.standards_service_registry import service

_IR_METRIC_IDS = (
    "precision_at_10",
    "ndcg_at_10",
    "judged_mrr",
    "judged_mrr_at_10",
    "recall_at_10",
    "relevance_judgment_coverage_at_10",
)


def _json(value: Any, default: Any = None) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _grade(metadata: Mapping[str, Any]) -> float | None:
    raw = metadata.get("relevance_grade")
    if raw is None and "relevant" in metadata:
        raw = 1 if metadata.get("relevant") is True else 0 if metadata.get("relevant") is False else None
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return value


def _numeric_grades(value: Any) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None
    result: list[float] = []
    for raw in value:
        if isinstance(raw, bool):
            return None
        try:
            grade = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(grade) or grade < 0:
            return None
        result.append(grade)
    return result


def _dcg(grades: Iterable[float]) -> float:
    return sum((2.0 ** grade - 1.0) / math.log2(index + 2.0) for index, grade in enumerate(grades))


def _ndcg_with_explicit_ideal(retrieved: list[float], ideal: list[float], k: int) -> float | None:
    if len(retrieved) < k or len(ideal) < k:
        return None
    ideal_dcg = _dcg(ideal[:k])
    if ideal_dcg <= 0:
        return 0.0
    value = _dcg(retrieved[:k]) / ideal_dcg
    if not math.isfinite(value) or value < 0 or value > 1.000000001:
        return None
    return min(1.0, value)


def _total_relevant(metadata: Mapping[str, Any]) -> int | None:
    raw = metadata.get("total_relevant_documents")
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def reconcile_information_retrieval_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Replace permissive judged-result metrics with strict, reproducible variants."""
    item = service("retrieval-metrics")
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if not {"standards_metric_observations", "serp_observations", "serp_results"}.issubset(tables):
            return

        observations = connection.execute(
            """SELECT observation_id,quality_metadata FROM serp_observations
               WHERE audit_id=? AND domain_of_interest IS NOT NULL ORDER BY collected_at""",
            (audit_id,),
        ).fetchall()

        eligible_top10 = 0
        complete_judgment_queries = 0
        partial_or_unjudged = 0
        short_rankings = 0
        precision_values: list[float] = []
        rr_values: list[float] = []
        ndcg_values: list[float] = []
        recall_values: list[float] = []
        ndcg_qrel_queries = 0
        recall_denominator_queries = 0

        for observation in observations:
            rows = connection.execute(
                """SELECT position,metadata FROM serp_results
                   WHERE observation_id=? ORDER BY position LIMIT 10""",
                (observation["observation_id"],),
            ).fetchall()
            if len(rows) < 10:
                short_rankings += 1
                continue
            eligible_top10 += 1
            grades: list[float] = []
            complete = True
            for row in rows:
                metadata = _json(row["metadata"], {}) or {}
                grade = _grade(metadata) if isinstance(metadata, dict) else None
                if grade is None:
                    complete = False
                    break
                grades.append(grade)
            if not complete:
                partial_or_unjudged += 1
                continue

            complete_judgment_queries += 1
            relevant_top10 = sum(grade > 0 for grade in grades)
            precision_values.append(relevant_top10 / 10.0)
            rr_values.append(next((1.0 / rank for rank, grade in enumerate(grades, start=1) if grade > 0), 0.0))

            quality = _json(observation["quality_metadata"], {}) or {}
            if not isinstance(quality, dict):
                quality = {}

            ideal = _numeric_grades(quality.get("ideal_relevance_grades"))
            ndcg = _ndcg_with_explicit_ideal(grades, ideal, 10) if ideal is not None else None
            if ndcg is not None:
                ndcg_values.append(ndcg)
                ndcg_qrel_queries += 1

            total_relevant = _total_relevant(quality)
            if total_relevant is not None and total_relevant >= relevant_top10:
                recall_values.append(0.0 if total_relevant == 0 else relevant_top10 / total_relevant)
                recall_denominator_queries += 1

        with connection:
            placeholders = ",".join("?" for _ in _IR_METRIC_IDS)
            connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_IR_METRIC_IDS),
            )

            coverage = None if eligible_top10 == 0 else complete_judgment_queries * 100.0 / eligible_top10
            _record(
                connection,
                audit_id=audit_id,
                metric_id="relevance_judgment_coverage_at_10",
                label="Relevance Judgment Coverage@10",
                scope="SEARCH_QUERY",
                state="NO_DATA" if coverage is None else "MEASURED",
                value=None if coverage is None else round(coverage, 3),
                numerator=complete_judgment_queries,
                denominator=eligible_top10,
                unit="percent",
                source="Search Intelligence relevance judgments",
                methodology="Queries with all top-10 results explicitly judged / queries with at least 10 observed results",
                relation_degree=item.relation_degree,
                details={
                    "short_rankings_excluded": short_rankings,
                    "partial_or_unjudged_excluded": partial_or_unjudged,
                    "boundary": "Missing judgments are unknown, never coerced to non-relevant.",
                },
            )

            for metric_id, label, values, methodology, extra in (
                (
                    "precision_at_10",
                    "Precision@10",
                    precision_values,
                    "Mean Precision@10 over queries whose observed top 10 all have explicit relevance judgments",
                    {},
                ),
                (
                    "judged_mrr_at_10",
                    "Judged MRR@10",
                    rr_values,
                    "Mean reciprocal rank within top 10 over queries whose observed top 10 all have explicit relevance judgments",
                    {},
                ),
                (
                    "ndcg_at_10",
                    "nDCG@10",
                    ndcg_values,
                    "Mean nDCG@10 only when top-10 judgments and explicit ideal_relevance_grades are both persisted",
                    {"queries_with_explicit_ideal": ndcg_qrel_queries},
                ),
                (
                    "recall_at_10",
                    "Recall@10",
                    recall_values,
                    "Mean Recall@10 only when top-10 judgments and explicit total_relevant_documents are both persisted",
                    {"queries_with_explicit_total_relevant": recall_denominator_queries},
                ),
            ):
                value = None if not values else round(fmean(values), 6)
                _record(
                    connection,
                    audit_id=audit_id,
                    metric_id=metric_id,
                    label=label,
                    scope="SEARCH_QUERY",
                    state="NO_DATA" if value is None else "MEASURED",
                    value=value,
                    denominator=len(values),
                    unit="ratio",
                    source="Search Intelligence explicit relevance judgments",
                    methodology=methodology,
                    relation_degree=item.relation_degree,
                    details={
                        "complete_top10_judged_queries": complete_judgment_queries,
                        "boundary": "No missing relevance judgment or denominator is inferred.",
                        **extra,
                    },
                )
    finally:
        connection.close()


def install() -> None:
    """Reconcile strict IR metrics after the standards collector and refresh projections."""
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_metrics import enrich_existing_reports, write_standards_report

    if getattr(report_completion, "_rasai_strict_ir_reconciliation", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_strict_ir(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            reconcile_information_retrieval_metrics(audit_id=audit_id, workspace=workspace)
            write_standards_report(audit_id=audit_id, workspace=workspace)
            enrich_existing_reports(audit_id=audit_id, workspace=workspace)
            report_dir = workspace.root / "report"
            report_navigation.normalize_report_navigation(report_dir)
            enhance_report_directory(report_dir)
            write_report_manifest(report_dir)
        except Exception as exc:
            errors.append(f"strict-ir:{type(exc).__name__}:{str(exc)[:400]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_strict_ir
    report_completion._rasai_strict_ir_reconciliation = True
