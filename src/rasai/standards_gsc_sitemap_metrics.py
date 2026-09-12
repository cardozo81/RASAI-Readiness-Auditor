"""Advisory metrics from persisted Google Search Console Sitemap datasets.

The module never calls Google. It reads the latest persisted
``GOOGLE_SEARCH_CONSOLE_SITEMAPS`` dataset metadata from ``observability.db`` and
projects source-labelled observations into ``audit.db``. Deprecated indexed counts
are deliberately not used.
"""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _fmt_metric, _insert_panel, _record, load_metrics

_SOURCE_SITEMAPS = "GOOGLE_SEARCH_CONSOLE_SITEMAPS"
_GSC_SITEMAP_METRIC_IDS = (
    "gsc_sitemap_count",
    "gsc_sitemap_error_free_rate",
    "gsc_sitemap_warning_free_rate",
    "gsc_sitemap_pending_rate",
    "gsc_sitemap_reported_submitted_urls",
)


def _latest_dataset(connection: sqlite3.Connection) -> tuple[str, dict[str, Any]] | None:
    row = connection.execute(
        """SELECT dataset_id,metadata FROM datasets
           WHERE source_type=? ORDER BY collected_at DESC,dataset_id DESC LIMIT 1""",
        (_SOURCE_SITEMAPS,),
    ).fetchone()
    if row is None:
        return None
    try:
        metadata = json.loads(str(row["metadata"] or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        metadata = {}
    return str(row["dataset_id"]), metadata if isinstance(metadata, dict) else {}


def _nonnegative_int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator <= 0 else round(numerator * 100.0 / denominator, 3)


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
        scope="ORIGIN",
        state="NO_DATA" if value is None else "MEASURED",
        value=value,
        numerator=float(numerator),
        denominator=float(denominator),
        unit="percent",
        source="Google Search Console Sitemaps API",
        methodology=methodology,
        relation_degree=5,
        details=details,
    )


def reconcile_gsc_sitemap_metrics(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Project latest persisted Search Console sitemap metadata into advisory metrics."""

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
        if metric_table is None or "datasets" not in sidecar_tables:
            return

        latest = _latest_dataset(observability_connection)
        with audit_connection:
            placeholders = ",".join("?" for _ in _GSC_SITEMAP_METRIC_IDS)
            audit_connection.execute(
                f"DELETE FROM standards_metric_observations WHERE audit_id=? AND metric_id IN ({placeholders})",
                (audit_id, *_GSC_SITEMAP_METRIC_IDS),
            )
            if latest is None:
                return

            dataset_id, metadata = latest
            raw_sitemaps = metadata.get("sitemaps")
            sitemaps = [item for item in raw_sitemaps if isinstance(item, dict)] if isinstance(raw_sitemaps, list) else []
            common = {
                "dataset_id": dataset_id,
                "sitemaps": len(sitemaps),
                "boundary": (
                    "Metrics describe only the latest Search Console Sitemaps API dataset for the configured property. "
                    "Deprecated contents[].indexed values are intentionally ignored."
                ),
            }

            _record(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_sitemap_count",
                label="GSC Sitemap Count",
                scope="ORIGIN",
                state="MEASURED",
                value=float(len(sitemaps)),
                unit="sitemaps",
                source="Google Search Console Sitemaps API",
                methodology="Count of sitemap entries in the latest persisted Search Console Sitemaps dataset",
                relation_degree=5,
                details=common,
            )

            error_counts = [value for item in sitemaps if (value := _nonnegative_int(item.get("errors"))) is not None]
            warning_counts = [value for item in sitemaps if (value := _nonnegative_int(item.get("warnings"))) is not None]
            pending_values = [item.get("is_pending") for item in sitemaps if isinstance(item.get("is_pending"), bool)]

            _record_ratio(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_sitemap_error_free_rate",
                label="GSC Sitemap Error-free Rate",
                numerator=sum(value == 0 for value in error_counts),
                denominator=len(error_counts),
                methodology="Sitemaps with errors=0 / sitemap entries exposing a determinate errors count",
                details=common,
            )
            _record_ratio(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_sitemap_warning_free_rate",
                label="GSC Sitemap Warning-free Rate",
                numerator=sum(value == 0 for value in warning_counts),
                denominator=len(warning_counts),
                methodology="Sitemaps with warnings=0 / sitemap entries exposing a determinate warnings count",
                details=common,
            )
            _record_ratio(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_sitemap_pending_rate",
                label="GSC Sitemap Pending Rate",
                numerator=sum(bool(value) for value in pending_values),
                denominator=len(pending_values),
                methodology="Sitemaps with isPending=true / sitemap entries exposing a determinate isPending flag",
                details={**common, "direction": "LOWER_IS_BETTER"},
            )

            submitted_total = 0
            submitted_seen = False
            for item in sitemaps:
                submitted = item.get("submitted")
                if not isinstance(submitted, list):
                    continue
                for content in submitted:
                    if not isinstance(content, dict):
                        continue
                    value = _nonnegative_int(content.get("submitted"))
                    if value is None:
                        continue
                    submitted_seen = True
                    submitted_total += value

            submitted_value: float | None
            if not sitemaps:
                submitted_value = 0.0
            elif submitted_seen:
                submitted_value = float(submitted_total)
            else:
                submitted_value = None
            _record(
                audit_connection,
                audit_id=audit_id,
                metric_id="gsc_sitemap_reported_submitted_urls",
                label="GSC Sitemap Reported Submitted URLs",
                scope="ORIGIN",
                state="NO_DATA" if submitted_value is None else "MEASURED",
                value=submitted_value,
                unit="urls",
                source="Google Search Console Sitemaps API",
                methodology="Sum of contents[].submitted values reported across the latest persisted sitemap entries",
                relation_degree=5,
                details={
                    **common,
                    "boundary": (
                        "This is the sum reported by Search Console for sitemap content types; it is not an indexed-URL count. "
                        "Deprecated contents[].indexed is not used."
                    ),
                },
            )
    finally:
        observability_connection.close()
        audit_connection.close()


def enrich_gsc_sitemap_report(*, audit_id: str, workspace: AuditWorkspace) -> None:
    """Add a compact Search Console Sitemap metrics panel to observability.html."""

    rows = {
        str(row["metric_id"]): row
        for row in load_metrics(audit_id, workspace)
        if str(row["metric_id"]) in _GSC_SITEMAP_METRIC_IDS
    }
    if not rows:
        return

    cards: list[str] = []
    for metric_id in _GSC_SITEMAP_METRIC_IDS:
        row = rows.get(metric_id)
        if row is None:
            continue
        cards.append(
            "<div class='metric'><small>" + escape(str(row["label"])) + "</small><strong>"
            + _fmt_metric(row) + "</strong><span>GSC · Sitemaps</span></div>"
        )
    if not cards:
        return

    _insert_panel(
        Path(workspace.root) / "report" / "observability.html",
        "RASAI_GSC_SITEMAP_METRICS",
        "<section class='panel'><h2>Saúde observacional dos Sitemaps no Google Search Console</h2>"
        "<p>Usa apenas o dataset de Sitemaps já persistido. Errors, warnings, pending e submitted vêm da fonte Google; "
        "o campo deprecated de indexed não é usado e nenhuma taxa de indexação é inferida.</p>"
        "<div class='metric-grid'>" + "".join(cards) + "</div></section>",
    )
