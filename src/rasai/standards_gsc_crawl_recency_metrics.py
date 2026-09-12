"""Crawl recency observations derived from persisted Search Console URL Inspection.

No external call is made here. The latest persisted URL Inspection dataset is used and
its ``collected_at`` timestamp is the reproducible reference for crawl-age calculation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
import sqlite3
from typing import Any

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _percentile, _record, load_metrics

_SOURCE_INSPECTION = "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION"
_GSC_CRAWL_RECENCY_METRIC_IDS = (
    "gsc_last_crawl_timestamp_coverage",
    "gsc_last_crawl_age_p50_days",
    "gsc_last_crawl_age_p95_days",
)


def _parse_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_dataset(connection: sqlite3.Connection) -> tuple[str, datetime] | None:
    row = connection.execute(
        """SELECT dataset_id,collected_at FROM datasets
           WHERE source_type=? ORDER BY collected_at DESC,dataset_id DESC LIMIT 1""",
        (_SOURCE_INSPECTION,),
    ).fetchone()
    if row is None:
        return None
    collected_at = _parse_datetime(row["collected_at"])
    if collected_at is None:
        return None
    return str(row["dataset_id"]), collected_at


def reconcile_gsc_crawl_recency_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Project last-crawl timestamp coverage and p50/p95 age from latest GSC inspection."""
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
        tables = {
            str(row[0])
            for row in observability_connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if metric_table is None or "datasets" not in tables or "index_observations" not in tables:
            return

        latest = _latest_dataset(observability_connection)
        with audit_connection:
            placeholders = ",".join("?" for _ in _GSC_CRAWL_RECENCY_METRIC_IDS)
            audit_connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_GSC_CRAWL_RECENCY_METRIC_IDS),
            )
            if latest is None:
                return

            dataset_id, collected_at = latest
            rows = list(observability_connection.execute(
                """SELECT verdict,last_crawl_time FROM index_observations
                   WHERE dataset_id=? ORDER BY record_id""",
                (dataset_id,),
            ).fetchall())
            usable = [row for row in rows if str(row["verdict"] or "").strip().upper() != "ERROR"]
            ages: list[float] = []
            invalid_or_missing = 0
            for row in usable:
                crawled_at = _parse_datetime(row["last_crawl_time"])
                if crawled_at is None or crawled_at > collected_at:
                    invalid_or_missing += 1
                    continue
                ages.append((collected_at - crawled_at).total_seconds() / 86400.0)

            coverage = None if not usable else round(len(ages) * 100.0 / len(usable), 3)
            common = {
                "dataset_id": dataset_id,
                "reference_collected_at": collected_at.isoformat(),
                "usable_inspection_rows": len(usable),
                "valid_last_crawl_timestamps": len(ages),
                "invalid_or_missing_last_crawl_timestamps": invalid_or_missing,
                "boundary": (
                    "Age is calculated against the persisted dataset collected_at timestamp. "
                    "No good/bad threshold is inferred; values are observational Search Console evidence."
                ),
            }
            _record(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_last_crawl_timestamp_coverage",
                label="GSC Last Crawl Timestamp Coverage",
                scope="URL_SET",
                state="NO_DATA" if coverage is None else "MEASURED",
                value=coverage,
                numerator=float(len(ages)),
                denominator=float(len(usable)),
                unit="percent",
                source="Google Search Console URL Inspection API",
                methodology="Usable inspected URLs with a valid non-future lastCrawlTime / usable non-error inspected URLs",
                relation_degree=5,
                details=common,
            )
            for percentile, metric_id, label in (
                (50, "gsc_last_crawl_age_p50_days", "GSC Last Crawl Age p50"),
                (95, "gsc_last_crawl_age_p95_days", "GSC Last Crawl Age p95"),
            ):
                value = _percentile(ages, percentile / 100.0)
                _record(
                    audit_connection,
                    audit_id=audit_id,
                    metric_id=metric_id,
                    label=label,
                    scope="URL_SET",
                    state="NO_DATA" if value is None else "MEASURED",
                    value=None if value is None else round(value, 3),
                    denominator=float(len(ages)),
                    unit="days",
                    source="Google Search Console URL Inspection API",
                    methodology=f"Percentile p{percentile} of last-crawl age in days using dataset collected_at as reference",
                    relation_degree=5,
                    details=common,
                )
    finally:
        observability_connection.close()
        audit_connection.close()


def enrich_gsc_crawl_recency_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    rows = {
        str(row["metric_id"]): row
        for row in load_metrics(audit_id, workspace)
        if str(row["metric_id"]) in _GSC_CRAWL_RECENCY_METRIC_IDS
    }
    if not rows:
        return

    cards: list[str] = []
    for metric_id in _GSC_CRAWL_RECENCY_METRIC_IDS:
        row = rows.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
            + _fmt_metric(row) + "</strong><span>GSC · crawl observado</span></div>"
        )
    if not cards:
        return
    _insert_panel(
        Path(workspace.root) / "report" / "observability.html",
        "RASAI_GSC_CRAWL_RECENCY_METRICS",
        "<section class='panel'><h2>Recência do crawl observado pelo Google</h2>"
        "<p>Derivada de lastCrawlTime do URL Inspection já persistido. A referência temporal é o collected_at do próprio dataset; "
        "não há threshold proprietário de frescor.</p><div class='metric-grid'>" + "".join(cards) + "</div></section>",
    )
