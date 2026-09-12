"""Deterministic crawl-freshness metrics from persisted GSC URL Inspection data.

The age reference is the Search Console dataset ``collected_at`` timestamp rather than
the current clock, so recomputing the same persisted evidence yields the same result.
No Google request is performed by this module.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import math
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _record, load_metrics

_SOURCE_INSPECTION = "GOOGLE_SEARCH_CONSOLE_URL_INSPECTION"
_GSC_CRAWL_METRIC_IDS = (
    "gsc_last_crawl_time_coverage",
    "gsc_last_crawl_age_p50_days",
    "gsc_last_crawl_age_p75_days",
    "gsc_last_crawl_age_p95_days",
)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 3)


def _latest_dataset(connection: sqlite3.Connection) -> tuple[str, datetime | None] | None:
    row = connection.execute(
        """SELECT dataset_id,collected_at FROM datasets
           WHERE source_type=? ORDER BY collected_at DESC,dataset_id DESC LIMIT 1""",
        (_SOURCE_INSPECTION,),
    ).fetchone()
    if row is None:
        return None
    return str(row["dataset_id"]), _parse_timestamp(row["collected_at"])


def reconcile_gsc_crawl_freshness_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Project latest persisted GSC lastCrawlTime observations into reproducible metrics."""

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
        if metric_table is None or "datasets" not in sidecar_tables or "index_observations" not in sidecar_tables:
            return

        latest = _latest_dataset(observability_connection)
        with audit_connection:
            placeholders = ",".join("?" for _ in _GSC_CRAWL_METRIC_IDS)
            audit_connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_GSC_CRAWL_METRIC_IDS),
            )
            if latest is None:
                return

            dataset_id, collected_at = latest
            rows = list(observability_connection.execute(
                """SELECT verdict,last_crawl_time FROM index_observations
                   WHERE dataset_id=? ORDER BY record_id""",
                (dataset_id,),
            ).fetchall())
            non_error = [row for row in rows if str(row["verdict"] or "").upper() != "ERROR"]
            parsed_times = [
                parsed
                for row in non_error
                if (parsed := _parse_timestamp(row["last_crawl_time"])) is not None
            ]
            coverage = None if not non_error else round(len(parsed_times) * 100.0 / len(non_error), 3)
            common = {
                "dataset_id": dataset_id,
                "dataset_collected_at": collected_at.isoformat() if collected_at is not None else None,
                "non_error_inspection_rows": len(non_error),
                "valid_last_crawl_timestamps": len(parsed_times),
                "boundary": (
                    "lastCrawlTime is the last successful Google crawl reported by URL Inspection. "
                    "Crawl age is referenced to the persisted dataset collected_at timestamp for reproducibility."
                ),
            }
            _record(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_last_crawl_time_coverage",
                label="GSC Last Crawl Time Coverage",
                scope="URL_SET",
                state="NO_DATA" if coverage is None else "MEASURED",
                value=coverage,
                numerator=float(len(parsed_times)),
                denominator=float(len(non_error)),
                unit="percent",
                source="Google Search Console URL Inspection API",
                methodology="Non-error inspected URLs with valid lastCrawlTime / non-error inspected URLs",
                relation_degree=5,
                details=common,
            )

            ages: list[float] = []
            future_timestamps = 0
            if collected_at is not None:
                for crawled_at in parsed_times:
                    seconds = (collected_at - crawled_at).total_seconds()
                    if seconds < 0:
                        future_timestamps += 1
                        continue
                    ages.append(seconds / 86400.0)
            age_details = {
                **common,
                "age_samples": len(ages),
                "future_timestamps_excluded": future_timestamps,
                "percentile_method": "linear interpolation over sorted crawl-age days",
            }
            for metric_id, label, percentile in (
                ("gsc_last_crawl_age_p50_days", "GSC Last Crawl Age p50", 0.50),
                ("gsc_last_crawl_age_p75_days", "GSC Last Crawl Age p75", 0.75),
                ("gsc_last_crawl_age_p95_days", "GSC Last Crawl Age p95", 0.95),
            ):
                value = _percentile(ages, percentile)
                _record(
                    audit_connection,
                    audit_id=audit_id,
                    metric_id=metric_id,
                    label=label,
                    scope="URL_SET",
                    state="NO_DATA" if value is None else "MEASURED",
                    value=value,
                    unit="days",
                    source="Google Search Console URL Inspection API",
                    methodology=(
                        f"p{int(percentile * 100)} of non-negative (dataset collected_at - lastCrawlTime) days "
                        "for the latest persisted URL Inspection dataset"
                    ),
                    relation_degree=5,
                    details=age_details,
                )
    finally:
        observability_connection.close()
        audit_connection.close()


def enrich_gsc_crawl_freshness_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Add GSC crawl freshness cards to observability.html."""

    rows = {
        str(row["metric_id"]): row
        for row in load_metrics(audit_id, workspace)
        if str(row["metric_id"]) in _GSC_CRAWL_METRIC_IDS
    }
    if not rows:
        return

    cards: list[str] = []
    for metric_id in _GSC_CRAWL_METRIC_IDS:
        row = rows.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
            + _fmt_metric(row) + "</strong><span>GSC · crawl freshness</span></div>"
        )
    if not cards:
        return

    _insert_panel(
        Path(workspace.root) / "report" / "observability.html",
        "RASAI_GSC_CRAWL_FRESHNESS_METRICS",
        "<section class='panel'><h2>Freshness observacional do crawl Google</h2>"
        "<p>Derivada de lastCrawlTime do URL Inspection. A idade usa o collected_at do dataset como referência, "
        "não o relógio atual, mantendo o resultado reproduzível para a mesma evidência.</p>"
        "<div class='metric-grid'>" + "".join(cards) + "</div></section>",
    )
