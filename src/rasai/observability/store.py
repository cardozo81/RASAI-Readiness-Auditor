"""Sidecar persistence for observed external data.

The sidecar deliberately lives beside audit.db and never mutates the source audit.
It is derived/rebuildable from preserved artifacts and direct collection results.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable

FORMAT_VERSION = "RASAI-OBS-002"


@dataclass(frozen=True, slots=True)
class Dataset:
    dataset_id: str
    source_type: str
    capture_method: str
    period_start: str | None
    period_end: str | None
    artifact_path: str
    artifact_sha256: str
    metadata: dict[str, Any]
    collected_at: str


_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "search_performance": (
        "record_id", "dataset_id", "source", "observed_date", "query_text", "url", "device", "country",
        "surface", "clicks", "impressions", "ctr", "position", "metadata",
    ),
    "index_observations": (
        "record_id", "dataset_id", "source", "url", "verdict", "coverage_state", "indexing_state",
        "robots_txt_state", "page_fetch_state", "user_canonical", "selected_canonical", "last_crawl_time",
        "crawled_as", "referring_urls", "sitemap_urls", "metadata",
    ),
    "crux_history": (
        "record_id", "dataset_id", "target", "target_scope", "form_factor", "metric", "period_start",
        "period_end", "p75", "good_density", "needs_improvement_density", "poor_density", "metadata",
    ),
}


class ObservabilityStore:
    def __init__(self, audit_workspace: str | Path) -> None:
        self.workspace = Path(audit_workspace)
        if not (self.workspace / "audit.db").is_file():
            raise FileNotFoundError(f"audit database not found: {self.workspace / 'audit.db'}")
        self.path = self.workspace / "observability.db"
        self.artifacts = self.workspace / "artifacts" / "observability"
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def __enter__(self) -> "ObservabilityStore":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        # Normalize any locally created sidecar whose observation tables use a
        # global record_id primary key. The current contract scopes record IDs by
        # dataset because collectors may restart local numbering for each dataset.
        self.connection.execute("PRAGMA foreign_keys=OFF")
        self._create_datasets_table()
        self._normalize_record_primary_keys()
        with self.connection:
            self.connection.executescript(_OBSERVATION_SCHEMA)
        self.connection.execute("PRAGMA foreign_keys=ON")

    def _create_datasets_table(self) -> None:
        with self.connection:
            self.connection.execute(
                """CREATE TABLE IF NOT EXISTS datasets (
                    dataset_id TEXT PRIMARY KEY,
                    format_version TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    capture_method TEXT NOT NULL,
                    period_start TEXT,
                    period_end TEXT,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    collected_at TEXT NOT NULL
                )"""
            )

    def _normalize_record_primary_keys(self) -> None:
        existing = {
            str(row[0])
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        for table, columns in _TABLE_COLUMNS.items():
            if table not in existing or not _has_global_record_pk(self.connection, table):
                continue
            source_table = f"{table}_record_pk_rebuild_source"
            column_list = ",".join(columns)
            with self.connection:
                self.connection.execute(f"ALTER TABLE {table} RENAME TO {source_table}")
                self.connection.executescript(_table_schema(table))
                self.connection.execute(
                    f"INSERT INTO {table} ({column_list}) SELECT {column_list} FROM {source_table}"
                )
                self.connection.execute(f"DROP TABLE {source_table}")

    def replace_dataset(
        self,
        dataset: Dataset,
        *,
        search_rows: Iterable[dict[str, Any]] = (),
        index_rows: Iterable[dict[str, Any]] = (),
        crux_rows: Iterable[dict[str, Any]] = (),
    ) -> None:
        """Replace one dataset through the row-aware atomic persistence path."""
        self.replace_dataset_rows(
            dataset,
            search_rows=search_rows,
            index_rows=index_rows,
            crux_rows=crux_rows,
        )

    def replace_dataset_rows(
        self,
        dataset: Dataset,
        *,
        search_rows: Iterable[dict[str, Any]] = (),
        index_rows: Iterable[dict[str, Any]] = (),
        crux_rows: Iterable[dict[str, Any]] = (),
    ) -> None:
        """Atomically replace one dataset and all of its normalized rows."""
        search = tuple(search_rows)
        index = tuple(index_rows)
        crux = tuple(crux_rows)
        with self.connection:
            self.connection.execute("DELETE FROM datasets WHERE dataset_id=?", (dataset.dataset_id,))
            self.connection.execute(
                """INSERT INTO datasets(
                    dataset_id,format_version,source_type,capture_method,period_start,period_end,
                    artifact_path,artifact_sha256,metadata,collected_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    dataset.dataset_id,
                    FORMAT_VERSION,
                    dataset.source_type,
                    dataset.capture_method,
                    dataset.period_start,
                    dataset.period_end,
                    dataset.artifact_path,
                    dataset.artifact_sha256,
                    _dump(dataset.metadata),
                    dataset.collected_at,
                ),
            )
            for row in search:
                self.connection.execute(
                    "INSERT INTO search_performance VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["record_id"], dataset.dataset_id, row.get("source") or dataset.source_type,
                        row.get("observed_date"), row.get("query_text"), row.get("url"), row.get("device"),
                        row.get("country"), row.get("surface"), _float_or_none(row.get("clicks")),
                        _float_or_none(row.get("impressions")), _float_or_none(row.get("ctr")),
                        _float_or_none(row.get("position")), _dump(row.get("metadata") or {}),
                    ),
                )
            for row in index:
                self.connection.execute(
                    "INSERT INTO index_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["record_id"], dataset.dataset_id, row.get("source") or dataset.source_type,
                        row["url"], row.get("verdict"), row.get("coverage_state"), row.get("indexing_state"),
                        row.get("robots_txt_state"), row.get("page_fetch_state"), row.get("user_canonical"),
                        row.get("selected_canonical"), row.get("last_crawl_time"), row.get("crawled_as"),
                        _dump(list(row.get("referring_urls") or [])), _dump(list(row.get("sitemap_urls") or [])),
                        _dump(row.get("metadata") or {}),
                    ),
                )
            for row in crux:
                self.connection.execute(
                    "INSERT INTO crux_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["record_id"], dataset.dataset_id, row["target"], row["target_scope"],
                        row.get("form_factor"), row["metric"], row.get("period_start"), row.get("period_end"),
                        _float_or_none(row.get("p75")), _float_or_none(row.get("good_density")),
                        _float_or_none(row.get("needs_improvement_density")), _float_or_none(row.get("poor_density")),
                        _dump(row.get("metadata") or {}),
                    ),
                )

    def datasets(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM datasets ORDER BY collected_at DESC,dataset_id"))

    def search_rows(self) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            "SELECT * FROM search_performance ORDER BY COALESCE(observed_date,''),source,query_text,url,dataset_id,record_id"
        ))

    def index_rows(self) -> list[sqlite3.Row]:
        return list(self.connection.execute("SELECT * FROM index_observations ORDER BY source,url,dataset_id,record_id"))

    def crux_rows(self) -> list[sqlite3.Row]:
        return list(self.connection.execute(
            "SELECT * FROM crux_history ORDER BY target,form_factor,metric,period_end,dataset_id,record_id"
        ))


def new_dataset(
    *,
    dataset_id: str,
    source_type: str,
    capture_method: str,
    artifact_path: str,
    artifact_sha256: str,
    period_start: str | None = None,
    period_end: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Dataset:
    return Dataset(
        dataset_id=dataset_id,
        source_type=source_type,
        capture_method=capture_method,
        period_start=period_start,
        period_end=period_end,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        metadata=metadata or {},
        collected_at=datetime.now(timezone.utc).isoformat(),
    )


def _has_global_record_pk(connection: sqlite3.Connection, table: str) -> bool:
    info = list(connection.execute(f"PRAGMA table_info({table})"))
    primary = [str(row[1]) for row in sorted(info, key=lambda item: int(item[5])) if int(row[5]) > 0]
    return primary == ["record_id"]


def _table_schema(table: str) -> str:
    schemas = {
        "search_performance": """
            CREATE TABLE search_performance (
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                observed_date TEXT,
                query_text TEXT,
                url TEXT,
                device TEXT,
                country TEXT,
                surface TEXT,
                clicks REAL,
                impressions REAL,
                ctr REAL,
                position REAL,
                metadata TEXT NOT NULL,
                PRIMARY KEY(dataset_id,record_id)
            );
        """,
        "index_observations": """
            CREATE TABLE index_observations (
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
                source TEXT NOT NULL,
                url TEXT NOT NULL,
                verdict TEXT,
                coverage_state TEXT,
                indexing_state TEXT,
                robots_txt_state TEXT,
                page_fetch_state TEXT,
                user_canonical TEXT,
                selected_canonical TEXT,
                last_crawl_time TEXT,
                crawled_as TEXT,
                referring_urls TEXT NOT NULL,
                sitemap_urls TEXT NOT NULL,
                metadata TEXT NOT NULL,
                PRIMARY KEY(dataset_id,record_id)
            );
        """,
        "crux_history": """
            CREATE TABLE crux_history (
                record_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
                target TEXT NOT NULL,
                target_scope TEXT NOT NULL,
                form_factor TEXT,
                metric TEXT NOT NULL,
                period_start TEXT,
                period_end TEXT,
                p75 REAL,
                good_density REAL,
                needs_improvement_density REAL,
                poor_density REAL,
                metadata TEXT NOT NULL,
                PRIMARY KEY(dataset_id,record_id)
            );
        """,
    }
    return schemas[table]


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


_OBSERVATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS search_performance (
    record_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    observed_date TEXT,
    query_text TEXT,
    url TEXT,
    device TEXT,
    country TEXT,
    surface TEXT,
    clicks REAL,
    impressions REAL,
    ctr REAL,
    position REAL,
    metadata TEXT NOT NULL,
    PRIMARY KEY(dataset_id,record_id)
);
CREATE TABLE IF NOT EXISTS index_observations (
    record_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    verdict TEXT,
    coverage_state TEXT,
    indexing_state TEXT,
    robots_txt_state TEXT,
    page_fetch_state TEXT,
    user_canonical TEXT,
    selected_canonical TEXT,
    last_crawl_time TEXT,
    crawled_as TEXT,
    referring_urls TEXT NOT NULL,
    sitemap_urls TEXT NOT NULL,
    metadata TEXT NOT NULL,
    PRIMARY KEY(dataset_id,record_id)
);
CREATE TABLE IF NOT EXISTS crux_history (
    record_id TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    target TEXT NOT NULL,
    target_scope TEXT NOT NULL,
    form_factor TEXT,
    metric TEXT NOT NULL,
    period_start TEXT,
    period_end TEXT,
    p75 REAL,
    good_density REAL,
    needs_improvement_density REAL,
    poor_density REAL,
    metadata TEXT NOT NULL,
    PRIMARY KEY(dataset_id,record_id)
);
CREATE INDEX IF NOT EXISTS idx_obs_search_dataset ON search_performance(dataset_id,source,url,query_text);
CREATE INDEX IF NOT EXISTS idx_obs_search_grain ON search_performance(source,observed_date,query_text,url,device,country,surface);
CREATE INDEX IF NOT EXISTS idx_obs_index_dataset ON index_observations(dataset_id,source,url);
CREATE INDEX IF NOT EXISTS idx_obs_crux_dataset ON crux_history(dataset_id,target,form_factor,metric,period_end);
"""