"""Persistência aditiva do M26 — Observed Generative Visibility.

O M26 armazena outcomes observados/importados em tabelas próprias. Nenhuma
tabela de scoring, RuleExecution, Finding ou Recommendation é escrita aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Any

from searchgeo.persistence import AuditWorkspace


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True, slots=True)
class VisibilityImport:
    import_id: str
    audit_id: str
    format_version: str
    source_type: str
    source_label: str
    period_start: str
    period_end: str
    market: str | None
    language: str | None
    source_total_citations: int | None
    source_average_cited_pages: float | None
    artifact_path: str
    artifact_sha256: str
    metadata: dict[str, Any]
    imported_at: str


@dataclass(frozen=True, slots=True)
class PageCitation:
    observation_id: str
    import_id: str
    audit_id: str
    url: str
    citations: int
    observed_date: str | None


@dataclass(frozen=True, slots=True)
class GroundingQuery:
    observation_id: str
    import_id: str
    audit_id: str
    query_text: str
    citations: int | None
    url: str | None
    observed_date: str | None


@dataclass(frozen=True, slots=True)
class TrendPoint:
    observation_id: str
    import_id: str
    audit_id: str
    observed_date: str
    citations: int


@dataclass(frozen=True, slots=True)
class QueryRun:
    query_run_id: str
    import_id: str
    audit_id: str
    engine: str
    surface: str | None
    query_text: str
    observed_at: str
    market: str | None
    language: str | None
    status: str
    cited: bool | None
    cited_urls: tuple[str, ...]
    source_rank: int | None
    ranking_semantics: str | None
    notes: str | None


class M26Persistence:
    def __init__(self, workspace: AuditWorkspace) -> None:
        self.connection = sqlite3.connect(workspace.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "M26Persistence":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS generative_visibility_imports (
                    import_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    format_version TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_label TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    market TEXT,
                    language TEXT,
                    source_total_citations INTEGER,
                    source_average_cited_pages REAL,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    UNIQUE(audit_id,artifact_sha256)
                );

                CREATE TABLE IF NOT EXISTS generative_visibility_page_citations (
                    observation_id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL REFERENCES generative_visibility_imports(import_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    citations INTEGER NOT NULL,
                    observed_date TEXT
                );

                CREATE TABLE IF NOT EXISTS generative_visibility_grounding_queries (
                    observation_id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL REFERENCES generative_visibility_imports(import_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    query_text TEXT NOT NULL,
                    citations INTEGER,
                    url TEXT,
                    observed_date TEXT
                );

                CREATE TABLE IF NOT EXISTS generative_visibility_trend (
                    observation_id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL REFERENCES generative_visibility_imports(import_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    observed_date TEXT NOT NULL,
                    citations INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS generative_visibility_query_runs (
                    query_run_id TEXT PRIMARY KEY,
                    import_id TEXT NOT NULL REFERENCES generative_visibility_imports(import_id) ON DELETE CASCADE,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    engine TEXT NOT NULL,
                    surface TEXT,
                    query_text TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    market TEXT,
                    language TEXT,
                    status TEXT NOT NULL,
                    cited INTEGER,
                    cited_urls TEXT NOT NULL,
                    source_rank INTEGER,
                    ranking_semantics TEXT,
                    notes TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_generative_visibility_imports_audit
                    ON generative_visibility_imports(audit_id,period_end,imported_at);
                CREATE INDEX IF NOT EXISTS idx_generative_visibility_pages_import
                    ON generative_visibility_page_citations(import_id,citations,url);
                CREATE INDEX IF NOT EXISTS idx_generative_visibility_queries_import
                    ON generative_visibility_grounding_queries(import_id,query_text);
                CREATE INDEX IF NOT EXISTS idx_generative_visibility_trend_import
                    ON generative_visibility_trend(import_id,observed_date);
                CREATE INDEX IF NOT EXISTS idx_generative_visibility_runs_import
                    ON generative_visibility_query_runs(import_id,status,engine,observed_at);
                """
            )

    def replace_import(
        self,
        item: VisibilityImport,
        *,
        pages: tuple[PageCitation, ...],
        queries: tuple[GroundingQuery, ...],
        trend: tuple[TrendPoint, ...],
        query_runs: tuple[QueryRun, ...],
    ) -> None:
        with self.connection:
            existing = self.connection.execute(
                "SELECT import_id FROM generative_visibility_imports WHERE audit_id=? AND artifact_sha256=?",
                (item.audit_id, item.artifact_sha256),
            ).fetchone()
            if existing is not None:
                self.connection.execute(
                    "DELETE FROM generative_visibility_imports WHERE import_id=?",
                    (str(existing["import_id"]),),
                )
            self.connection.execute(
                """
                INSERT INTO generative_visibility_imports (
                    import_id,audit_id,format_version,source_type,source_label,period_start,period_end,
                    market,language,source_total_citations,source_average_cited_pages,artifact_path,
                    artifact_sha256,metadata,imported_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.import_id, item.audit_id, item.format_version, item.source_type,
                    item.source_label, item.period_start, item.period_end, item.market, item.language,
                    item.source_total_citations, item.source_average_cited_pages, item.artifact_path,
                    item.artifact_sha256, _dump(item.metadata), item.imported_at,
                ),
            )
            self.connection.executemany(
                """INSERT INTO generative_visibility_page_citations
                   (observation_id,import_id,audit_id,url,citations,observed_date)
                   VALUES (?,?,?,?,?,?)""",
                [(p.observation_id,p.import_id,p.audit_id,p.url,p.citations,p.observed_date) for p in pages],
            )
            self.connection.executemany(
                """INSERT INTO generative_visibility_grounding_queries
                   (observation_id,import_id,audit_id,query_text,citations,url,observed_date)
                   VALUES (?,?,?,?,?,?,?)""",
                [(q.observation_id,q.import_id,q.audit_id,q.query_text,q.citations,q.url,q.observed_date) for q in queries],
            )
            self.connection.executemany(
                """INSERT INTO generative_visibility_trend
                   (observation_id,import_id,audit_id,observed_date,citations)
                   VALUES (?,?,?,?,?)""",
                [(t.observation_id,t.import_id,t.audit_id,t.observed_date,t.citations) for t in trend],
            )
            self.connection.executemany(
                """INSERT INTO generative_visibility_query_runs (
                    query_run_id,import_id,audit_id,engine,surface,query_text,observed_at,market,
                    language,status,cited,cited_urls,source_rank,ranking_semantics,notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r.query_run_id,r.import_id,r.audit_id,r.engine,r.surface,r.query_text,
                        r.observed_at,r.market,r.language,r.status,
                        None if r.cited is None else int(r.cited),_dump(r.cited_urls),
                        r.source_rank,r.ranking_semantics,r.notes,
                    )
                    for r in query_runs
                ],
            )
