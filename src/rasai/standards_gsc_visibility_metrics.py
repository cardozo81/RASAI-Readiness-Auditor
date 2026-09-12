"""Additional bounded visibility counts from persisted Search Console rows.

These observations are descriptive counts of the latest persisted Search Analytics
returned-row dataset. They never call Google and must not be interpreted as complete
property coverage because Search Analytics can return top rows.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
import sqlite3

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _record, load_metrics

_SOURCE_SEARCH = "GOOGLE_SEARCH_CONSOLE_SEARCH_ANALYTICS"
_GSC_VISIBILITY_METRIC_IDS = (
    "gsc_returned_distinct_queries",
    "gsc_returned_distinct_urls",
    "gsc_returned_distinct_query_url_pairs",
)


def _latest_dataset(connection: sqlite3.Connection) -> str | None:
    row = connection.execute(
        """SELECT dataset_id FROM datasets
           WHERE source_type=? ORDER BY collected_at DESC,dataset_id DESC LIMIT 1""",
        (_SOURCE_SEARCH,),
    ).fetchone()
    return None if row is None else str(row[0])


def reconcile_gsc_visibility_counts(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Project distinct returned-row query/URL counts from the latest GSC dataset."""

    sidecar = Path(workspace.root) / "observability.db"
    if not sidecar.is_file():
        return

    audit_connection = sqlite3.connect(workspace.database)
    audit_connection.row_factory = sqlite3.Row
    observability_connection = sqlite3.connect(sidecar)
    observability_connection.row_factory = sqlite3.Row
    try:
        metric_table = audit_connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_metric_observations'"
        ).fetchone()
        sidecar_tables = {
            str(row[0])
            for row in observability_connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if metric_table is None or "datasets" not in sidecar_tables or "search_performance" not in sidecar_tables:
            return

        dataset_id = _latest_dataset(observability_connection)
        with audit_connection:
            placeholders = ",".join("?" for _ in _GSC_VISIBILITY_METRIC_IDS)
            audit_connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_GSC_VISIBILITY_METRIC_IDS),
            )
            if dataset_id is None:
                return

            row = observability_connection.execute(
                """SELECT
                       COUNT(*) AS returned_rows,
                       COUNT(DISTINCT CASE WHEN TRIM(COALESCE(query_text,''))<>'' THEN query_text END) AS distinct_queries,
                       COUNT(DISTINCT CASE WHEN TRIM(COALESCE(url,''))<>'' THEN url END) AS distinct_urls
                   FROM search_performance WHERE dataset_id=?""",
                (dataset_id,),
            ).fetchone()
            pair_row = observability_connection.execute(
                """SELECT COUNT(*) FROM (
                       SELECT query_text,url FROM search_performance
                       WHERE dataset_id=?
                         AND TRIM(COALESCE(query_text,''))<>''
                         AND TRIM(COALESCE(url,''))<>''
                       GROUP BY query_text,url
                   )""",
                (dataset_id,),
            ).fetchone()

            returned_rows = int(row["returned_rows"] or 0)
            values = (
                (
                    "gsc_returned_distinct_queries",
                    "GSC Returned-row Distinct Queries",
                    float(row["distinct_queries"] or 0),
                    "queries",
                    "Distinct non-empty query_text values in the latest persisted Search Analytics returned-row dataset",
                ),
                (
                    "gsc_returned_distinct_urls",
                    "GSC Returned-row Distinct URLs",
                    float(row["distinct_urls"] or 0),
                    "urls",
                    "Distinct non-empty URL values in the latest persisted Search Analytics returned-row dataset",
                ),
                (
                    "gsc_returned_distinct_query_url_pairs",
                    "GSC Returned-row Distinct Query-URL Pairs",
                    float(pair_row[0] or 0),
                    "pairs",
                    "Distinct non-empty query_text + URL pairs in the latest persisted Search Analytics returned-row dataset",
                ),
            )
            common = {
                "dataset_id": dataset_id,
                "returned_rows": returned_rows,
                "boundary": (
                    "Counts describe only rows returned and persisted by the bounded Search Console collection. "
                    "They are not complete query, URL or property coverage metrics."
                ),
            }
            for metric_id, label, value, unit, methodology in values:
                _record(
                    audit_connection,
                    audit_id=audit_id,
                    metric_id=metric_id,
                    label=label,
                    scope="ORIGIN",
                    state="MEASURED",
                    value=value,
                    unit=unit,
                    source="Google Search Console Search Analytics API",
                    methodology=methodology,
                    relation_degree=5,
                    details=common,
                )
    finally:
        observability_connection.close()
        audit_connection.close()


def enrich_gsc_visibility_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Add a compact returned-row visibility panel to observability.html."""

    rows = {
        str(row["metric_id"]): row
        for row in load_metrics(audit_id, workspace)
        if str(row["metric_id"]) in _GSC_VISIBILITY_METRIC_IDS
    }
    if not rows:
        return

    cards: list[str] = []
    for metric_id in _GSC_VISIBILITY_METRIC_IDS:
        row = rows.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
            + _fmt_metric(row) + "</strong><span>GSC · returned rows</span></div>"
        )
    if not cards:
        return

    _insert_panel(
        Path(workspace.root) / "report" / "observability.html",
        "RASAI_GSC_RETURNED_VISIBILITY_COUNTS",
        "<section class='panel'><h2>Representação nas linhas retornadas pelo Google Search Console</h2>"
        "<p>Contagens descritivas do dataset Search Analytics persistido mais recente. "
        "Não representam cobertura completa da property, pois a API pode retornar top rows.</p>"
        "<div class='metric-grid'>" + "".join(cards) + "</div></section>",
    )
