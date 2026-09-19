"""Persisted-data-only refinements for existing catalog report sections.

No page, section, navigation or CSS structure is changed here.  The module only enriches
existing tables/subsections with evidence that is already persisted and prevents a
missing current-provider result from hiding valid historical/browser observations.
"""
from __future__ import annotations

import json
from pathlib import Path
from rasai.observability.store import observability_database_path
import sqlite3
import sys
from typing import Any, Mapping

_INSTALLED = False
_CRUX_SOURCE = "CHROME_UX_REPORT_HISTORY"
_SIDE_CAR_NAMES = {
    _CRUX_SOURCE: "Chrome UX Report History",
    "COMMON_CRAWL_CDX_HISTORY": "Common Crawl",
    "MICROSOFT_CLARITY_LIVE_INSIGHTS": "Microsoft Clarity",
}


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _safe_json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _observability(database: Any) -> tuple[list[dict[str, Any]], sqlite3.Connection | None]:
    path = observability_database_path(Path(database).parent)
    if not path.is_file():
        return [], None
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    if not _table_exists(connection, "datasets"):
        connection.close()
        return [], None
    rows = [dict(row) for row in connection.execute("SELECT * FROM datasets ORDER BY collected_at,dataset_id")]
    return rows, connection


def _dataset_count(connection: sqlite3.Connection, table: str, dataset_id: str) -> int:
    if not _table_exists(connection, table):
        return 0
    columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    if "dataset_id" not in columns:
        return 0
    row = connection.execute(
        f"SELECT COUNT(*) FROM {table} WHERE dataset_id=?", (dataset_id,)
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _source_table(source_type: str) -> str | None:
    if source_type == _CRUX_SOURCE:
        return "crux_history"
    if source_type == "COMMON_CRAWL_CDX_HISTORY":
        return "web_archive_observations"
    if source_type == "MICROSOFT_CLARITY_LIVE_INSIGHTS":
        return "behavioral_observations"
    if source_type.startswith("GOOGLE_SEARCH_CONSOLE_"):
        suffix = source_type.removeprefix("GOOGLE_SEARCH_CONSOLE_")
        return "index_observations" if "INDEX" in suffix else "search_performance"
    return None


def _sidecar_name(source_type: str) -> str:
    if source_type.startswith("GOOGLE_SEARCH_CONSOLE_"):
        suffix = source_type.removeprefix("GOOGLE_SEARCH_CONSOLE_").replace("_", " ").title()
        return f"Google Search Console · {suffix}"
    return _SIDE_CAR_NAMES.get(source_type, source_type.replace("_", " ").title())


def _install_external_integrations() -> None:
    from rasai import catalog_report_integrations as integrations

    current = integrations._external_integrations
    if bool(getattr(current, "_rasai_catalog_projection_consistency", False)):
        return

    def external(database: Any, audit_id: str):
        rows = list(current(database, audit_id))
        datasets, connection = _observability(database)
        if connection is None:
            return rows
        try:
            for dataset in datasets:
                source_type = str(dataset.get("source_type") or "")
                table = _source_table(source_type)
                if table is None:
                    continue
                dataset_id = str(dataset.get("dataset_id") or "")
                metadata = _safe_json(dataset.get("metadata"), {})
                count = _dataset_count(connection, table, dataset_id)
                errors = 0
                if isinstance(metadata, Mapping):
                    try:
                        errors = int(metadata.get("errors") or 0)
                    except (TypeError, ValueError):
                        errors = 0
                status = "SUCCESS" if count > 0 and not errors else "PARTIAL" if count > 0 else "NO_DATA"
                attempts = 1
                if isinstance(metadata, Mapping):
                    try:
                        attempts = max(1, int(metadata.get("requests") or 1))
                    except (TypeError, ValueError):
                        attempts = 1
                rows.append(
                    {
                        "name": _sidecar_name(source_type),
                        "status": status,
                        "attempts": attempts,
                        "successes": 1 if count > 0 else 0,
                        "duration_ms": None,
                        "http_status": None,
                        "error": f"{errors} erro(s)" if errors else None,
                        "url": None,
                        "reference": dataset.get("artifact_path"),
                        "raw": {
                            "details_json": json.dumps(
                                {
                                    "dataset_id": dataset_id,
                                    "source_type": source_type,
                                    "capture_method": dataset.get("capture_method"),
                                    "period_start": dataset.get("period_start"),
                                    "period_end": dataset.get("period_end"),
                                    "rows": count,
                                    "metadata": metadata,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            )
                        },
                    }
                )
        finally:
            connection.close()
        return rows

    external._rasai_catalog_projection_consistency = True
    external._rasai_original = current
    integrations._external_integrations = external


def _install_crux_history_cat05() -> None:
    from rasai import catalog_report_search_trust as trust
    from rasai import catalog_report_page as page

    current = trust._external_html
    if bool(getattr(current, "_rasai_catalog_projection_consistency", False)):
        return

    def external_html(database: Any, data: Any) -> str:
        html = current(database, data)
        datasets, connection = _observability(database)
        if connection is None:
            return html
        try:
            crux = [row for row in datasets if str(row.get("source_type") or "") == _CRUX_SOURCE]
            if not crux:
                return html
            details = []
            total = 0
            for dataset in crux:
                dataset_id = str(dataset.get("dataset_id") or "")
                count = _dataset_count(connection, "crux_history", dataset_id)
                total += count
                metadata = _safe_json(dataset.get("metadata"), {})
                details.append(
                    (
                        dataset_id,
                        dataset.get("capture_method") or "—",
                        dataset.get("collected_at") or "—",
                        dataset.get("period_start") or "—",
                        dataset.get("period_end") or "—",
                        count,
                        dataset.get("artifact_path") or "—",
                        ", ".join(str(value) for value in (metadata.get("metrics") or ()))
                        if isinstance(metadata, Mapping)
                        else "—",
                    )
                )
            block = "<div class='subsection'><h3>CrUX History</h3>"
            block += "<div class='metric-grid'>" + page._metric("Datasets", len(crux)) + page._metric("Pontos históricos", total) + "</div>"
            block += page._table(
                ("Dataset", "Método", "Coletado em", "Período início", "Período fim", "Pontos", "Artefato", "Métricas"),
                details,
                empty="Nenhum dataset CrUX History persistido nesta AUD.",
            )
            block += "</div>"
            return html + block
        finally:
            connection.close()

    external_html._rasai_catalog_projection_consistency = True
    external_html._rasai_original = current
    trust._external_html = external_html


def _browser_snapshot_metrics(database: Any, audit_id: str) -> list[tuple[str, Any, str]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        if not (_table_exists(connection, "page_snapshots") and _table_exists(connection, "pages")):
            return []
        rows = connection.execute(
            """SELECT ps.browser_metadata,ps.device FROM page_snapshots ps
               JOIN pages p ON p.page_id=ps.page_id WHERE p.audit_id=? ORDER BY ps.captured_at""",
            (audit_id,),
        ).fetchall()
    finally:
        connection.close()

    values: dict[str, list[float]] = {
        "FCP same-session": [],
        "LCP same-session": [],
        "CLS same-session": [],
        "TTFB same-session": [],
    }
    for row in rows:
        metadata = _safe_json(row["browser_metadata"], {})
        open_web = metadata.get("open_web_metrics") if isinstance(metadata, Mapping) else None
        if not isinstance(open_web, Mapping):
            continue
        paint = open_web.get("paint") if isinstance(open_web.get("paint"), Mapping) else {}
        layout = open_web.get("layout") if isinstance(open_web.get("layout"), Mapping) else {}
        navigation = open_web.get("navigation") if isinstance(open_web.get("navigation"), Mapping) else {}
        raw = {
            "FCP same-session": paint.get("first_contentful_paint_ms"),
            "LCP same-session": paint.get("largest_contentful_paint_ms"),
            "CLS same-session": layout.get("cumulative_layout_shift"),
            "TTFB same-session": navigation.get("ttfb_from_navigation_start_ms"),
        }
        for key, value in raw.items():
            if isinstance(value, (int, float)):
                values[key].append(float(value))

    output: list[tuple[str, Any, str]] = []
    for label, items in values.items():
        if not items:
            continue
        low, high = min(items), max(items)
        if "CLS" in label:
            formatted = f"{low:.3f}" if low == high else f"{low:.3f} – {high:.3f}"
        else:
            formatted = f"{low:.0f} ms" if low == high else f"{low:.0f} – {high:.0f} ms"
        output.append(("Navegador · " + label, formatted, "Medição da sessão capturada"))
    return output


def _install_browser_metrics() -> None:
    from rasai import catalog_report_metrics as metrics
    from rasai import catalog_state_trust as state_trust
    from rasai import execution_consistency_runtime as consistency

    current = consistency._consistent_web_metric_rows
    if not bool(getattr(current, "_rasai_catalog_projection_consistency", False)):
        def web_rows(database: Any, audit_id: str):
            rows = list(current(database, audit_id))
            existing = {str(row[0]) for row in rows if row}
            for row in _browser_snapshot_metrics(database, audit_id):
                if row[0] not in existing:
                    rows.append(row)
            return rows

        web_rows._rasai_catalog_projection_consistency = True
        web_rows._rasai_original = current
        consistency._consistent_web_metric_rows = web_rows
        metrics._web_metric_rows = web_rows

    current_count = state_trust._browser_performance_count
    if not bool(getattr(current_count, "_rasai_catalog_projection_consistency", False)):
        def browser_count(database: Any, audit_id: str) -> int:
            base = int(current_count(database, audit_id) or 0)
            return base + len(_browser_snapshot_metrics(database, audit_id))

        browser_count._rasai_catalog_projection_consistency = True
        browser_count._rasai_original = current_count
        state_trust._browser_performance_count = browser_count


def _sync_site_bindings() -> None:
    """Refresh references imported by value after late report installers run."""
    site = sys.modules.get("rasai.catalog_report_site")
    if site is None:
        return
    from rasai import catalog_report_integrations as integrations
    from rasai import catalog_report_metrics as metrics
    from rasai import catalog_report_page as page

    bindings = {
        "_catalog_body": page._catalog_body,
        "_catalog_status": page._catalog_status,
        "_catalog_sources": page._catalog_sources,
        "_search_intelligence_html": page._search_intelligence_html,
        "_catalog_metrics": metrics._catalog_metrics,
        "_web_metric_rows": metrics._web_metric_rows,
        "_ai_integrations_body": integrations._ai_integrations_body,
    }
    for name, value in bindings.items():
        if hasattr(site, name):
            setattr(site, name, value)


def _wrap_late_report_installers() -> None:
    """Keep catalog_report_site aligned with renderers replaced after module import."""
    from rasai import catalog_report_adherence as adherence
    from rasai import catalog_report_search_trust as search_trust

    for module, name in (
        (adherence, "install_catalog_report_adherence"),
        (search_trust, "install"),
    ):
        current = getattr(module, name)
        if bool(getattr(current, "_rasai_catalog_projection_sync", False)):
            continue

        def wrapped(*args: Any, __current=current, **kwargs: Any):
            result = __current(*args, **kwargs)
            _sync_site_bindings()
            return result

        wrapped._rasai_catalog_projection_sync = True
        wrapped._rasai_original = current
        setattr(module, name, wrapped)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        _sync_site_bindings()
        return
    _install_external_integrations()
    _install_crux_history_cat05()
    _install_browser_metrics()
    _wrap_late_report_installers()
    _sync_site_bindings()
    _INSTALLED = True


__all__ = ["install"]
