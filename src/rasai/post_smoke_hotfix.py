"""Small mechanical corrections over :mod:`post_smoke_alignment`.

Kept separate so the final smoke patch stays reviewable: the governed Common Crawl hook
uses the current collector signature and the catalog snapshot sees transient SERP terms
while the legacy post-AUD Search branch remains suppressed.
"""
from __future__ import annotations

from pathlib import Path
import os
import sqlite3
import sys
from typing import Any

_INSTALLED = False


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _latest_common_crawl_dataset(workspace_root: str | Path) -> str:
    database = Path(workspace_root) / "observability.db"
    if not database.is_file():
        raise RuntimeError("COMMON_CRAWL_PRESEAL_DATASET_MISSING")
    connection = sqlite3.connect(database)
    try:
        if not _table_exists(connection, "datasets"):
            raise RuntimeError("COMMON_CRAWL_PRESEAL_DATASET_MISSING")
        row = connection.execute(
            """SELECT dataset_id FROM datasets
               WHERE source_type='COMMON_CRAWL_CDX_HISTORY'
               ORDER BY collected_at DESC,rowid DESC LIMIT 1"""
        ).fetchone()
    finally:
        connection.close()
    if row is None or not row[0]:
        raise RuntimeError("COMMON_CRAWL_PRESEAL_DATASET_MISSING")
    return str(row[0])


def _install_common_crawl_hook() -> None:
    from rasai import external_observability_runtime as external
    from rasai import external_sari
    from rasai.audit_phase_runtime import register_collection_hook
    from rasai.external_observability_policy import COMMON_CRAWL_ENABLED_ENV
    from rasai.standards_service_registry import service, service_state

    current = external.collect_configured_external_observability

    def collector(*, audit_id: str, workspace: Any, source_blocked: bool = False):
        environment = dict(os.environ)
        without_common = dict(environment)
        without_common[COMMON_CRAWL_ENABLED_ENV] = "false"
        outcomes = dict(
            current(audit_id=audit_id, workspace=workspace, env=without_common) or {}
        )

        state_info = service_state(service("common-crawl"), environment)
        common = external._base_result(state_info)
        if source_blocked:
            common.update(
                targets_attempted=0,
                targets_succeeded=0,
                datasets=[],
                errors=[],
                collection_state="BLOCKED",
                reason="SOURCE_BLOCKED",
            )
        elif bool(state_info.get("effective_enabled")):
            max_urls = external.common_crawl_max_urls(
                environment.get(external.COMMON_CRAWL_MAX_URLS_ENV)
            )
            if max_urls == 0:
                common.update(
                    targets_attempted=0,
                    targets_succeeded=0,
                    datasets=[],
                    errors=[],
                    collection_state="NO_DATA",
                    reason="COMMON_CRAWL_MAX_URLS_ZERO",
                )
            else:
                try:
                    dataset_id = external.collect_common_crawl_history(
                        audit_workspace=workspace.root,
                        max_urls=max_urls,
                        collection_count=external.common_crawl_index_count(
                            environment.get(external.COMMON_CRAWL_INDEX_COUNT_ENV)
                        ),
                        timeout=external._positive_float(
                            environment.get(external.STANDARDS_TIMEOUT_ENV),
                            external.DEFAULT_STANDARDS_TIMEOUT_SECONDS,
                        ),
                    )
                    common.update(
                        targets_attempted=1,
                        targets_succeeded=1,
                        datasets=[dataset_id],
                        errors=[],
                        collection_state="SUCCESS",
                        scope="URL",
                    )
                except Exception as exc:
                    common.update(
                        targets_attempted=1,
                        targets_succeeded=0,
                        datasets=[],
                        errors=[external._safe_error("COMMON_CRAWL", exc)],
                        collection_state="ERROR",
                    )
        outcomes["common-crawl"] = common
        external._upsert_service_run(
            audit_id=audit_id,
            workspace=workspace,
            service_id="common-crawl",
            result=common,
        )
        from rasai.governed_optional_runtime import _aggregate
        return {"collection_state": _aggregate(outcomes), "services": outcomes}

    collector._rasai_post_smoke_common_crawl_canonical = True
    collector._rasai_original = current
    register_collection_hook("EXTERNAL_OBSERVABILITY", collector, order=50)

    def persisted_only(*, audit_workspace: Any, **_kwargs: Any) -> str:
        return _latest_common_crawl_dataset(audit_workspace)

    persisted_only._rasai_post_smoke_persisted_only = True
    external_sari.collect_common_crawl_history = persisted_only


def _install_catalog_snapshot_search_alignment() -> None:
    from rasai import console_catalog_plan as plan
    from rasai.post_smoke_alignment import _EFFECTIVE_SEARCH_QUERIES

    current = plan.catalog_snapshot
    if bool(getattr(current, "_rasai_effective_search_catalog", False)):
        return

    def catalog_snapshot(state: Any):
        rows = list(current(state))
        queries = _EFFECTIVE_SEARCH_QUERIES.get()
        if not queries:
            return tuple(rows)
        output = []
        for raw in rows:
            row = dict(raw)
            catalog_id = str(row.get("id") or row.get("catalog_id") or "").upper()
            if catalog_id == "CAT-05" and bool(row.get("selected")):
                row["status"] = "APTO"
                row["detail"] = (
                    f"{len(queries)} consulta(s) SERP incluída(s) no contrato efetivo desta execução"
                )
            output.append(row)
        return tuple(output)

    catalog_snapshot._rasai_effective_search_catalog = True
    catalog_snapshot._rasai_original = current
    plan.catalog_snapshot = catalog_snapshot
    workflow = sys.modules.get("rasai.console_catalog_workflow")
    if workflow is not None and hasattr(workflow, "catalog_snapshot"):
        workflow.catalog_snapshot = catalog_snapshot


def _install_materialized_sidecar_counts() -> None:
    """A dataset with zero rows is an execution artifact, not a 'source with data'."""
    from rasai import post_smoke_alignment as alignment

    def sidecar_counts(database: Any) -> dict[str, int]:
        result: dict[str, int] = {}
        sidecar = Path(database).parent / "observability.db"
        if not sidecar.is_file():
            return result
        connection = sqlite3.connect(sidecar)
        connection.row_factory = sqlite3.Row
        try:
            if not _table_exists(connection, "datasets"):
                return result
            for raw in connection.execute("SELECT * FROM datasets").fetchall():
                dataset = dict(raw)
                source = str(dataset.get("source_type") or "")
                dataset_id = str(dataset.get("dataset_id") or "")
                candidate_tables = (
                    ("crux_history",)
                    if source == "CHROME_UX_REPORT_HISTORY"
                    else ("web_archive_observations",)
                    if source == "COMMON_CRAWL_CDX_HISTORY"
                    else ("behavioral_observations",)
                    if source == "MICROSOFT_CLARITY_LIVE_INSIGHTS"
                    else ("search_performance", "index_observations")
                    if source.startswith("GOOGLE_SEARCH_CONSOLE_")
                    else ()
                )
                count = 0
                for table in candidate_tables:
                    if not _table_exists(connection, table):
                        continue
                    columns = {
                        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
                    }
                    if "dataset_id" not in columns:
                        continue
                    row = connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE dataset_id=?", (dataset_id,)
                    ).fetchone()
                    count += int(row[0] or 0) if row else 0
                if count > 0:
                    result[source] = result.get(source, 0) + count
        finally:
            connection.close()
        return result

    alignment._sidecar_source_counts = sidecar_counts


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_common_crawl_hook()
    _install_catalog_snapshot_search_alignment()
    _install_materialized_sidecar_counts()
    _INSTALLED = True


__all__ = ["install"]
