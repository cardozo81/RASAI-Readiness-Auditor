"""Derived observational metrics over already-persisted Google Search Console data.

This module never calls Google. It reads the latest Search Console datasets already
stored in ``observability.db`` and projects bounded, source-labelled observations into
the standards metric table in ``audit.db``. The results are advisory and do not change
SARI-001 or SCORE-GEO-004.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _record, load_metrics

_SOURCE_INSPECTION = "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION"
_SOURCE_SEARCH = "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS"

_GSC_METRIC_IDS = (
    "gsc_url_inspection_verdict_pass_rate",
    "gsc_indexing_allowed_rate",
    "gsc_robots_allowed_rate",
    "gsc_page_fetch_success_rate",
    "gsc_exact_canonical_agreement_rate",
    "gsc_sitemap_association_rate",
    "gsc_returned_search_rows",
    "gsc_returned_row_clicks",
    "gsc_returned_row_impressions",
    "gsc_returned_row_ctr",
    "gsc_returned_row_impression_weighted_position",
)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return decoded if isinstance(decoded, list) else []


def _latest_dataset(connection: sqlite3.Connection, source_type: str) -> str | None:
    row = connection.execute(
        """SELECT dataset_id FROM datasets
           WHERE source_type=? ORDER BY collected_at DESC,dataset_id DESC LIMIT 1""",
        (source_type,),
    ).fetchone()
    return None if row is None else str(row[0])


def _determinate(value: Any, *, unspecified: Iterable[str] = ()) -> bool:
    normalized = str(value or "").strip().upper()
    return bool(normalized) and normalized not in {item.upper() for item in unspecified}


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator * 100.0 / denominator, 3)


def _state(value: float | None) -> str:
    return "NO_DATA" if value is None else "MEASURED"


def _record_ratio(
    connection: sqlite3.Connection,
    *,
    audit_id: str,
    metric_id: str,
    label: str,
    numerator: int,
    denominator: int,
    methodology: str,
    details: Mapping[str, Any],
) -> None:
    value = _ratio(numerator, denominator)
    _record(
        connection,
        audit_id=audit_id,
        metric_id=metric_id,
        label=label,
        scope="URL_SET",
        state=_state(value),
        value=value,
        numerator=float(numerator),
        denominator=float(denominator),
        unit="percent",
        source="Google Search Console URL Inspection API",
        methodology=methodology,
        relation_degree=5,
        details=details,
    )


def _reconcile_inspection(
    audit_connection: sqlite3.Connection,
    observability_connection: sqlite3.Connection,
    *,
    audit_id: str,
) -> None:
    dataset_id = _latest_dataset(observability_connection, _SOURCE_INSPECTION)
    if dataset_id is None:
        return
    rows = list(observability_connection.execute(
        """SELECT url,verdict,coverage_state,indexing_state,robots_txt_state,page_fetch_state,
                  user_canonical,selected_canonical,sitemap_urls
           FROM index_observations WHERE dataset_id=? ORDER BY url,record_id""",
        (dataset_id,),
    ).fetchall())
    non_error = [row for row in rows if str(row["verdict"] or "").upper() != "ERROR"]

    verdict_rows = [
        row for row in non_error
        if _determinate(row["verdict"], unspecified=("VERDICT_UNSPECIFIED",))
    ]
    verdict_pass = sum(str(row["verdict"]).upper() == "PASS" for row in verdict_rows)
    _record_ratio(
        audit_connection,
        audit_id=audit_id,
        metric_id="gsc_url_inspection_verdict_pass_rate",
        label="GSC URL Inspection Verdict PASS Rate",
        numerator=verdict_pass,
        denominator=len(verdict_rows),
        methodology="URL Inspection verdict=PASS / determinate non-error inspected URLs",
        details={"dataset_id": dataset_id, "inspected_rows": len(rows), "non_error_rows": len(non_error)},
    )

    indexing_rows = [
        row for row in non_error
        if _determinate(row["indexing_state"], unspecified=("INDEXING_STATE_UNSPECIFIED",))
    ]
    indexing_allowed = sum(str(row["indexing_state"]).upper() == "INDEXING_ALLOWED" for row in indexing_rows)
    _record_ratio(
        audit_connection,
        audit_id=audit_id,
        metric_id="gsc_indexing_allowed_rate",
        label="GSC Indexing Allowed Rate",
        numerator=indexing_allowed,
        denominator=len(indexing_rows),
        methodology="URL Inspection indexingState=INDEXING_ALLOWED / determinate inspected URLs",
        details={"dataset_id": dataset_id},
    )

    robots_rows = [
        row for row in non_error
        if _determinate(row["robots_txt_state"], unspecified=("ROBOTS_TXT_STATE_UNSPECIFIED",))
    ]
    robots_allowed = sum(str(row["robots_txt_state"]).upper() == "ALLOWED" for row in robots_rows)
    _record_ratio(
        audit_connection,
        audit_id=audit_id,
        metric_id="gsc_robots_allowed_rate",
        label="GSC Robots Allowed Rate",
        numerator=robots_allowed,
        denominator=len(robots_rows),
        methodology="URL Inspection robotsTxtState=ALLOWED / determinate inspected URLs",
        details={"dataset_id": dataset_id},
    )

    fetch_rows = [
        row for row in non_error
        if _determinate(row["page_fetch_state"], unspecified=("PAGE_FETCH_STATE_UNSPECIFIED",))
    ]
    fetch_success = sum(str(row["page_fetch_state"]).upper() == "SUCCESSFUL" for row in fetch_rows)
    _record_ratio(
        audit_connection,
        audit_id=audit_id,
        metric_id="gsc_page_fetch_success_rate",
        label="GSC Page Fetch Successful Rate",
        numerator=fetch_success,
        denominator=len(fetch_rows),
        methodology="URL Inspection pageFetchState=SUCCESSFUL / determinate inspected URLs",
        details={"dataset_id": dataset_id},
    )

    canonical_rows = [
        row for row in non_error
        if str(row["user_canonical"] or "").strip() and str(row["selected_canonical"] or "").strip()
    ]
    canonical_agreement = sum(
        str(row["user_canonical"]).strip() == str(row["selected_canonical"]).strip()
        for row in canonical_rows
    )
    _record_ratio(
        audit_connection,
        audit_id=audit_id,
        metric_id="gsc_exact_canonical_agreement_rate",
        label="GSC Exact User/Google Canonical Agreement Rate",
        numerator=canonical_agreement,
        denominator=len(canonical_rows),
        methodology="Exact userCanonical == googleCanonical / inspected URLs exposing both canonical values",
        details={
            "dataset_id": dataset_id,
            "boundary": "Exact URL equality only; absence of either canonical is excluded from the denominator.",
        },
    )

    sitemap_rows = [row for row in non_error if _determinate(row["verdict"], unspecified=("VERDICT_UNSPECIFIED",))]
    sitemap_associated = sum(bool(_json_list(row["sitemap_urls"])) for row in sitemap_rows)
    _record_ratio(
        audit_connection,
        audit_id=audit_id,
        metric_id="gsc_sitemap_association_rate",
        label="GSC Sitemap Association Rate",
        numerator=sitemap_associated,
        denominator=len(sitemap_rows),
        methodology="Inspected URLs with one or more Search Console sitemap associations / determinate inspected URLs",
        details={
            "dataset_id": dataset_id,
            "boundary": "Association is observational and does not by itself prove sitemap completeness or correctness.",
        },
    )


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _reconcile_search_analytics(
    audit_connection: sqlite3.Connection,
    observability_connection: sqlite3.Connection,
    *,
    audit_id: str,
) -> None:
    dataset_id = _latest_dataset(observability_connection, _SOURCE_SEARCH)
    if dataset_id is None:
        return
    rows = list(observability_connection.execute(
        """SELECT clicks,impressions,ctr,position FROM search_performance
           WHERE dataset_id=? ORDER BY record_id""",
        (dataset_id,),
    ).fetchall())
    if not rows:
        return

    clicks = sum(value for row in rows if (value := _float(row["clicks"])) is not None)
    impressions = sum(value for row in rows if (value := _float(row["impressions"])) is not None)
    weighted_position_numerator = sum(
        position * weight
        for row in rows
        if (position := _float(row["position"])) is not None
        and (weight := _float(row["impressions"])) is not None
        and weight > 0
    )
    weighted_position_denominator = sum(
        weight
        for row in rows
        if _float(row["position"]) is not None
        and (weight := _float(row["impressions"])) is not None
        and weight > 0
    )
    observed_ctr = None if impressions <= 0 else round(clicks * 100.0 / impressions, 3)
    observed_position = (
        None if weighted_position_denominator <= 0
        else round(weighted_position_numerator / weighted_position_denominator, 3)
    )
    common = {
        "dataset_id": dataset_id,
        "returned_rows": len(rows),
        "boundary": (
            "Search Console Search Analytics may return top rows rather than every available row. "
            "These aggregates describe only the persisted returned-row dataset, not complete property totals."
        ),
    }
    for metric_id, label, value, unit, methodology in (
        (
            "gsc_returned_search_rows",
            "GSC Returned Search Analytics Rows",
            float(len(rows)),
            "rows",
            "Count of normalized rows persisted from the latest bounded Search Analytics dataset",
        ),
        (
            "gsc_returned_row_clicks",
            "GSC Returned-row Clicks",
            round(clicks, 3),
            "clicks",
            "Sum of clicks over the persisted returned Search Analytics rows",
        ),
        (
            "gsc_returned_row_impressions",
            "GSC Returned-row Impressions",
            round(impressions, 3),
            "impressions",
            "Sum of impressions over the persisted returned Search Analytics rows",
        ),
        (
            "gsc_returned_row_ctr",
            "GSC Returned-row CTR",
            observed_ctr,
            "percent",
            "Sum(clicks) / Sum(impressions) over the persisted returned Search Analytics rows",
        ),
        (
            "gsc_returned_row_impression_weighted_position",
            "GSC Returned-row Impression-weighted Position",
            observed_position,
            "position",
            "Impression-weighted mean position over the persisted returned Search Analytics rows",
        ),
    ):
        _record(
            audit_connection,
            audit_id=audit_id,
            metric_id=metric_id,
            label=label,
            scope="ORIGIN",
            state="NO_DATA" if value is None else "MEASURED",
            value=value,
            unit=unit,
            source="Google Search Console Search Analytics API",
            methodology=methodology,
            relation_degree=5,
            details=common,
        )


def reconcile_gsc_observational_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Project latest persisted GSC sidecar data into audit-scoped standards metrics."""

    sidecar = Path(workspace.root) / "observability.db"
    if not sidecar.is_file():
        return
    audit_connection = sqlite3.connect(workspace.database)
    audit_connection.row_factory = sqlite3.Row
    observability_connection = sqlite3.connect(sidecar)
    observability_connection.row_factory = sqlite3.Row
    try:
        required = audit_connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_metric_observations'"
        ).fetchone()
        if required is None:
            return
        tables = {
            str(row[0])
            for row in observability_connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "datasets" not in tables:
            return
        with audit_connection:
            placeholders = ",".join("?" for _ in _GSC_METRIC_IDS)
            audit_connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_GSC_METRIC_IDS),
            )
            if "index_observations" in tables:
                _reconcile_inspection(audit_connection, observability_connection, audit_id=audit_id)
            if "search_performance" in tables:
                _reconcile_search_analytics(audit_connection, observability_connection, audit_id=audit_id)
    finally:
        observability_connection.close()
        audit_connection.close()


def enrich_gsc_metrics_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    rows = {
        str(row["metric_id"]): row
        for row in load_metrics(audit_id, workspace)
        if str(row["metric_id"]) in _GSC_METRIC_IDS
    }
    if not rows:
        return
    preferred = (
        "gsc_url_inspection_verdict_pass_rate",
        "gsc_indexing_allowed_rate",
        "gsc_page_fetch_success_rate",
        "gsc_exact_canonical_agreement_rate",
        "gsc_returned_row_impressions",
        "gsc_returned_row_ctr",
        "gsc_returned_row_impression_weighted_position",
    )
    cards: list[str] = []
    for metric_id in preferred:
        row = rows.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
            + _fmt_metric(row) + "</strong><span>Google Search Console · observacional</span></div>"
        )
    _insert_panel(
        Path(workspace.root) / "report" / "observability.html",
        "RASAI_GSC_OBSERVATIONAL_METRICS",
        "<section class='panel'><h2>Métricas observacionais do Google Search Console</h2>"
        "<p>Derivadas somente dos datasets GSC já persistidos nesta auditoria. Não criam chamadas adicionais e não alteram SARI-001/SCORE-GEO-004. "
        "Agregados de Search Analytics descrevem apenas as linhas retornadas/persistidas, que podem ser top rows e não o universo completo da property.</p>"
        "<div class='metric-grid'>" + "".join(cards) + "</div>"
        "<p><a href='standards.html'>Abrir metodologia e fronteiras das métricas</a></p></section>",
    )
