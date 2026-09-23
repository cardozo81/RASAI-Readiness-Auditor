"""Recurring Search Intelligence monitoring over the product control plane.

This module deliberately keeps operational monitoring out of immutable AUD workspaces.
Registered queries, longitudinal run summaries and change events live in the local
control-plane database today and behind a repository contract that can be implemented
by PostgreSQL for SaaS later. Raw SERP evidence is stored as immutable files under the
control-plane evidence root; provider credentials are never persisted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping, Protocol
from uuid import uuid4

from rasai.platform.store import default_platform_database

from .competitive_ai import CompetitiveAiState, build_competitive_ai_provider
from .competitive_ai_runtime import execute_competitive_ai
from .competitive_runtime import execute_competitive_intelligence
from .config import SerpRuntimeConfig
from .content import CompetitiveContentAnalysis, CompetitivePageFeatures, PublicWebFetcher
from .evidence import FilesystemSerpEvidenceSink
from .models import QueryOrigin, SearchIntelligenceResult, SerpQueryRequest
from .runtime import execute_search


MONITORING_CONTRACT = "SEARCH-MONITOR-001"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex.upper()}"


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _bool(value: Any) -> bool:
    return bool(int(value)) if isinstance(value, (int, str)) else bool(value)


def _ratio(part: Iterable[str], whole: Iterable[str]) -> float | None:
    denominator = set(whole)
    if not denominator:
        return None
    return len(set(part)) / len(denominator)


@dataclass(frozen=True, slots=True)
class SearchMonitorQuery:
    query_id: str
    project_id: str
    property_id: str
    environment_id: str
    query: str
    domain_of_interest: str
    engine: str = "google"
    country: str = "BR"
    region: str | None = None
    language: str = "pt-BR"
    device: str = "desktop"
    requested_depth: int = 20
    mode: str = "live"
    provider: str = "serpapi"
    competitive: bool = True
    compare_content: bool = False
    max_content_pages: int = 3
    ai_competitive: bool = False
    ai_provider: str = "none"
    ai_model: str | None = None
    ymyl_mode: str = "AUTO"
    enabled: bool = True
    schedule_id: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def validate(self) -> "SearchMonitorQuery":
        if not self.query.strip():
            raise ValueError("monitor query must not be empty")
        if not self.domain_of_interest.strip():
            raise ValueError("monitor domain_of_interest must not be empty")
        if self.requested_depth <= 0:
            raise ValueError("monitor requested_depth must be greater than zero")
        if self.device not in {"mobile", "desktop"}:
            raise ValueError("monitor device must be mobile or desktop")
        if self.mode not in {"disabled", "live", "fixture"}:
            raise ValueError("monitor mode must be disabled, live or fixture")
        if self.max_content_pages < 0:
            raise ValueError("monitor max_content_pages must be >= 0")
        if self.ai_competitive and not self.compare_content:
            raise ValueError("Competitive AI monitoring requires compare_content")
        if self.ai_provider not in {"none", "openai", "fixture"}:
            raise ValueError("monitor AI provider must be none, openai or fixture")
        if self.ymyl_mode not in {"AUTO", "ON", "OFF"}:
            raise ValueError("monitor YMYL mode must be AUTO, ON or OFF")
        return self


@dataclass(frozen=True, slots=True)
class SearchMonitorSnapshot:
    observation_id: str | None
    collected_at: str | None
    provider: str
    data_mode: str | None
    observation_status: str | None
    domain_status: str
    customer_position: int | None
    result_count: int
    competitor_domains_ahead: tuple[str, ...]
    raw_evidence_ref: str | None
    raw_evidence_sha256: str | None
    comparison_status: str | None
    gap_codes: tuple[str, ...]
    query_body_coverage: float | None
    query_title_coverage: float | None
    query_heading_coverage: float | None
    word_count: int | None
    jsonld_types: tuple[str, ...]
    ai_state: str | None
    ai_provider: str | None
    ai_model: str | None
    ai_opportunity_count: int


@dataclass(frozen=True, slots=True)
class SearchMonitorChange:
    status: str
    label: str
    before: Any
    after: Any
    delta: float | None = None
    unit: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class SearchMonitorRun:
    monitor_run_id: str
    query_id: str
    started_at: str
    completed_at: str
    status: str
    snapshot: SearchMonitorSnapshot
    changes: tuple[SearchMonitorChange, ...]
    comparable_to_previous: bool | None
    comparison_note: str | None
    serp_http_requests: int
    content_http_requests: int
    ai_provider_calls: int
    manifest_ref: str | None
    manifest_sha256: str | None
    error_code: str | None = None
    error_message: str | None = None


class SearchMonitoringRepository(Protocol):
    def register_query(self, item: SearchMonitorQuery) -> SearchMonitorQuery: ...
    def get_query(self, query_id: str) -> SearchMonitorQuery | None: ...
    def list_queries(self, *, enabled_only: bool = False) -> tuple[SearchMonitorQuery, ...]: ...
    def set_query_enabled(self, query_id: str, enabled: bool) -> None: ...
    def attach_schedule(self, query_id: str, schedule_id: str | None) -> None: ...
    def latest_run(self, query_id: str) -> SearchMonitorRun | None: ...
    def list_runs(self, query_id: str, *, limit: int = 20) -> tuple[SearchMonitorRun, ...]: ...
    def record_run(self, run: SearchMonitorRun) -> None: ...


class SQLiteSearchMonitoringRepository:
    """SQLite implementation colocated with the product control plane.

    SQL is intentionally contained here so a PostgreSQL implementation can satisfy the
    same repository contract without leaking SQLite assumptions into monitoring runtime.
    """

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        if not self.database.is_file():
            raise FileNotFoundError(
                f"platform database not found: {self.database}; run rasai platform index first"
            )
        self.connection = sqlite3.connect(self.database, timeout=10.0)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self._initialize()

    @classmethod
    def open(cls, audits_root: str | Path = "audits", *, database: str | Path | None = None) -> "SQLiteSearchMonitoringRepository":
        return cls(database or default_platform_database(audits_root))

    def __enter__(self) -> "SQLiteSearchMonitoringRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        required = {"projects", "properties", "environments", "schedules"}
        existing = {
            str(row[0])
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = sorted(required - existing)
        if missing:
            raise RuntimeError("platform.db is missing required control-plane tables: " + ", ".join(missing))
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS search_monitor_queries (
                    query_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                    property_id TEXT NOT NULL REFERENCES properties(property_id) ON DELETE CASCADE,
                    environment_id TEXT NOT NULL REFERENCES environments(environment_id) ON DELETE CASCADE,
                    query TEXT NOT NULL,
                    domain_of_interest TEXT NOT NULL,
                    engine TEXT NOT NULL,
                    country TEXT NOT NULL,
                    region TEXT,
                    language TEXT NOT NULL,
                    device TEXT NOT NULL,
                    requested_depth INTEGER NOT NULL,
                    mode TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    competitive INTEGER NOT NULL DEFAULT 1,
                    compare_content INTEGER NOT NULL DEFAULT 0,
                    max_content_pages INTEGER NOT NULL DEFAULT 3,
                    ai_competitive INTEGER NOT NULL DEFAULT 0,
                    ai_provider TEXT NOT NULL DEFAULT 'none',
                    ai_model TEXT,
                    ymyl_mode TEXT NOT NULL DEFAULT 'AUTO',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    schedule_id TEXT REFERENCES schedules(schedule_id) ON DELETE SET NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_search_monitor_query_scope
                    ON search_monitor_queries(property_id,environment_id,enabled,query);

                CREATE TABLE IF NOT EXISTS search_monitor_runs (
                    monitor_run_id TEXT PRIMARY KEY,
                    query_id TEXT NOT NULL REFERENCES search_monitor_queries(query_id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    observation_id TEXT,
                    collected_at TEXT,
                    provider TEXT NOT NULL,
                    data_mode TEXT,
                    observation_status TEXT,
                    domain_status TEXT NOT NULL,
                    customer_position INTEGER,
                    result_count INTEGER NOT NULL,
                    competitor_domains_ahead_json TEXT NOT NULL,
                    raw_evidence_ref TEXT,
                    raw_evidence_sha256 TEXT,
                    comparison_status TEXT,
                    gap_codes_json TEXT NOT NULL,
                    query_body_coverage REAL,
                    query_title_coverage REAL,
                    query_heading_coverage REAL,
                    word_count INTEGER,
                    jsonld_types_json TEXT NOT NULL,
                    ai_state TEXT,
                    ai_provider TEXT,
                    ai_model TEXT,
                    ai_opportunity_count INTEGER NOT NULL DEFAULT 0,
                    changes_json TEXT NOT NULL,
                    comparable_to_previous INTEGER,
                    comparison_note TEXT,
                    serp_http_requests INTEGER NOT NULL DEFAULT 0,
                    content_http_requests INTEGER NOT NULL DEFAULT 0,
                    ai_provider_calls INTEGER NOT NULL DEFAULT 0,
                    manifest_ref TEXT,
                    manifest_sha256 TEXT,
                    error_code TEXT,
                    error_message TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_search_monitor_runs_query_time
                    ON search_monitor_runs(query_id,completed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_search_monitor_runs_observation
                    ON search_monitor_runs(observation_id);
                """
            )
            if "platform_extension_meta" in existing:
                self.connection.execute(
                    """INSERT INTO platform_extension_meta(key,value)
                       VALUES('search_monitor_schema','1')
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
                )

    def _validate_scope(self, item: SearchMonitorQuery) -> None:
        row = self.connection.execute(
            """SELECT p.project_id,e.property_id
               FROM properties p JOIN environments e ON e.property_id=p.property_id
               WHERE p.property_id=? AND e.environment_id=?""",
            (item.property_id, item.environment_id),
        ).fetchone()
        if row is None:
            raise ValueError("Search monitor property/environment scope does not exist")
        if str(row["project_id"]) != item.project_id:
            raise ValueError("Search monitor property does not belong to project")
        if str(row["property_id"]) != item.property_id:
            raise ValueError("Search monitor environment does not belong to property")

    def _query(self, row: sqlite3.Row) -> SearchMonitorQuery:
        return SearchMonitorQuery(
            query_id=str(row["query_id"]),
            project_id=str(row["project_id"]),
            property_id=str(row["property_id"]),
            environment_id=str(row["environment_id"]),
            query=str(row["query"]),
            domain_of_interest=str(row["domain_of_interest"]),
            engine=str(row["engine"]),
            country=str(row["country"]),
            region=str(row["region"]) if row["region"] is not None else None,
            language=str(row["language"]),
            device=str(row["device"]),
            requested_depth=int(row["requested_depth"]),
            mode=str(row["mode"]),
            provider=str(row["provider"]),
            competitive=_bool(row["competitive"]),
            compare_content=_bool(row["compare_content"]),
            max_content_pages=int(row["max_content_pages"]),
            ai_competitive=_bool(row["ai_competitive"]),
            ai_provider=str(row["ai_provider"]),
            ai_model=str(row["ai_model"]) if row["ai_model"] is not None else None,
            ymyl_mode=str(row["ymyl_mode"]),
            enabled=_bool(row["enabled"]),
            schedule_id=str(row["schedule_id"]) if row["schedule_id"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def register_query(self, item: SearchMonitorQuery) -> SearchMonitorQuery:
        item.validate()
        self._validate_scope(item)
        duplicate = self.connection.execute(
            """SELECT query_id FROM search_monitor_queries
               WHERE project_id=? AND property_id=? AND environment_id=?
                 AND query=? AND engine=? AND country=? AND region IS ?
                 AND language=? AND device=? AND requested_depth=? AND domain_of_interest=?""",
            (
                item.project_id, item.property_id, item.environment_id, item.query,
                item.engine, item.country, item.region, item.language, item.device,
                item.requested_depth, item.domain_of_interest,
            ),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(f"identical Search monitor query already registered: {duplicate[0]}")
        created = item.created_at or _now()
        stored = replace(item, created_at=created, updated_at=item.updated_at or created)
        with self.connection:
            self.connection.execute(
                """INSERT INTO search_monitor_queries(
                    query_id,project_id,property_id,environment_id,query,domain_of_interest,
                    engine,country,region,language,device,requested_depth,mode,provider,
                    competitive,compare_content,max_content_pages,ai_competitive,ai_provider,
                    ai_model,ymyl_mode,enabled,schedule_id,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    stored.query_id, stored.project_id, stored.property_id, stored.environment_id,
                    stored.query, stored.domain_of_interest, stored.engine, stored.country,
                    stored.region, stored.language, stored.device, stored.requested_depth,
                    stored.mode, stored.provider, int(stored.competitive), int(stored.compare_content),
                    stored.max_content_pages, int(stored.ai_competitive), stored.ai_provider,
                    stored.ai_model, stored.ymyl_mode, int(stored.enabled), stored.schedule_id,
                    stored.created_at, stored.updated_at,
                ),
            )
        return stored

    def get_query(self, query_id: str) -> SearchMonitorQuery | None:
        row = self.connection.execute(
            "SELECT * FROM search_monitor_queries WHERE query_id=?", (query_id,)
        ).fetchone()
        return self._query(row) if row is not None else None

    def list_queries(self, *, enabled_only: bool = False) -> tuple[SearchMonitorQuery, ...]:
        sql = "SELECT * FROM search_monitor_queries"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY project_id,property_id,query,device"
        return tuple(self._query(row) for row in self.connection.execute(sql))

    def set_query_enabled(self, query_id: str, enabled: bool) -> None:
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE search_monitor_queries SET enabled=?,updated_at=? WHERE query_id=?",
                (int(enabled), _now(), query_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"Search monitor query not found: {query_id}")

    def attach_schedule(self, query_id: str, schedule_id: str | None) -> None:
        if schedule_id is not None:
            exists = self.connection.execute(
                "SELECT 1 FROM schedules WHERE schedule_id=?", (schedule_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(f"schedule not found: {schedule_id}")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE search_monitor_queries SET schedule_id=?,updated_at=? WHERE query_id=?",
                (schedule_id, _now(), query_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(f"Search monitor query not found: {query_id}")

    def _run(self, row: sqlite3.Row) -> SearchMonitorRun:
        snapshot = SearchMonitorSnapshot(
            observation_id=str(row["observation_id"]) if row["observation_id"] is not None else None,
            collected_at=str(row["collected_at"]) if row["collected_at"] is not None else None,
            provider=str(row["provider"]),
            data_mode=str(row["data_mode"]) if row["data_mode"] is not None else None,
            observation_status=str(row["observation_status"]) if row["observation_status"] is not None else None,
            domain_status=str(row["domain_status"]),
            customer_position=int(row["customer_position"]) if row["customer_position"] is not None else None,
            result_count=int(row["result_count"]),
            competitor_domains_ahead=tuple(str(item) for item in _load(row["competitor_domains_ahead_json"], [])),
            raw_evidence_ref=str(row["raw_evidence_ref"]) if row["raw_evidence_ref"] is not None else None,
            raw_evidence_sha256=str(row["raw_evidence_sha256"]) if row["raw_evidence_sha256"] is not None else None,
            comparison_status=str(row["comparison_status"]) if row["comparison_status"] is not None else None,
            gap_codes=tuple(str(item) for item in _load(row["gap_codes_json"], [])),
            query_body_coverage=float(row["query_body_coverage"]) if row["query_body_coverage"] is not None else None,
            query_title_coverage=float(row["query_title_coverage"]) if row["query_title_coverage"] is not None else None,
            query_heading_coverage=float(row["query_heading_coverage"]) if row["query_heading_coverage"] is not None else None,
            word_count=int(row["word_count"]) if row["word_count"] is not None else None,
            jsonld_types=tuple(str(item) for item in _load(row["jsonld_types_json"], [])),
            ai_state=str(row["ai_state"]) if row["ai_state"] is not None else None,
            ai_provider=str(row["ai_provider"]) if row["ai_provider"] is not None else None,
            ai_model=str(row["ai_model"]) if row["ai_model"] is not None else None,
            ai_opportunity_count=int(row["ai_opportunity_count"]),
        )
        changes_raw = _load(row["changes_json"], [])
        changes = tuple(
            SearchMonitorChange(
                status=str(item.get("status") or "CHANGED"),
                label=str(item.get("label") or "Change"),
                before=item.get("before"),
                after=item.get("after"),
                delta=float(item["delta"]) if item.get("delta") is not None else None,
                unit=str(item["unit"]) if item.get("unit") is not None else None,
                note=str(item["note"]) if item.get("note") is not None else None,
            )
            for item in changes_raw
            if isinstance(item, dict)
        )
        comparable = row["comparable_to_previous"]
        return SearchMonitorRun(
            monitor_run_id=str(row["monitor_run_id"]),
            query_id=str(row["query_id"]),
            started_at=str(row["started_at"]),
            completed_at=str(row["completed_at"]),
            status=str(row["status"]),
            snapshot=snapshot,
            changes=changes,
            comparable_to_previous=(bool(int(comparable)) if comparable is not None else None),
            comparison_note=str(row["comparison_note"]) if row["comparison_note"] is not None else None,
            serp_http_requests=int(row["serp_http_requests"]),
            content_http_requests=int(row["content_http_requests"]),
            ai_provider_calls=int(row["ai_provider_calls"]),
            manifest_ref=str(row["manifest_ref"]) if row["manifest_ref"] is not None else None,
            manifest_sha256=str(row["manifest_sha256"]) if row["manifest_sha256"] is not None else None,
            error_code=str(row["error_code"]) if row["error_code"] is not None else None,
            error_message=str(row["error_message"]) if row["error_message"] is not None else None,
        )

    def latest_run(self, query_id: str) -> SearchMonitorRun | None:
        row = self.connection.execute(
            """SELECT * FROM search_monitor_runs WHERE query_id=?
               ORDER BY completed_at DESC, monitor_run_id DESC LIMIT 1""",
            (query_id,),
        ).fetchone()
        return self._run(row) if row is not None else None

    def list_runs(self, query_id: str, *, limit: int = 20) -> tuple[SearchMonitorRun, ...]:
        if limit < 1:
            return ()
        rows = self.connection.execute(
            """SELECT * FROM search_monitor_runs WHERE query_id=?
               ORDER BY completed_at DESC, monitor_run_id DESC LIMIT ?""",
            (query_id, limit),
        ).fetchall()
        return tuple(self._run(row) for row in rows)

    def record_run(self, run: SearchMonitorRun) -> None:
        snapshot = run.snapshot
        with self.connection:
            self.connection.execute(
                """INSERT INTO search_monitor_runs(
                    monitor_run_id,query_id,started_at,completed_at,status,observation_id,collected_at,
                    provider,data_mode,observation_status,domain_status,customer_position,result_count,
                    competitor_domains_ahead_json,raw_evidence_ref,raw_evidence_sha256,comparison_status,
                    gap_codes_json,query_body_coverage,query_title_coverage,query_heading_coverage,word_count,
                    jsonld_types_json,ai_state,ai_provider,ai_model,ai_opportunity_count,changes_json,
                    comparable_to_previous,comparison_note,serp_http_requests,content_http_requests,
                    ai_provider_calls,manifest_ref,manifest_sha256,error_code,error_message
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run.monitor_run_id, run.query_id, run.started_at, run.completed_at, run.status,
                    snapshot.observation_id, snapshot.collected_at, snapshot.provider, snapshot.data_mode,
                    snapshot.observation_status, snapshot.domain_status, snapshot.customer_position,
                    snapshot.result_count, _dump(snapshot.competitor_domains_ahead), snapshot.raw_evidence_ref,
                    snapshot.raw_evidence_sha256, snapshot.comparison_status, _dump(snapshot.gap_codes),
                    snapshot.query_body_coverage, snapshot.query_title_coverage,
                    snapshot.query_heading_coverage, snapshot.word_count, _dump(snapshot.jsonld_types),
                    snapshot.ai_state, snapshot.ai_provider, snapshot.ai_model,
                    snapshot.ai_opportunity_count, _dump([asdict(item) for item in run.changes]),
                    (int(run.comparable_to_previous) if run.comparable_to_previous is not None else None),
                    run.comparison_note, run.serp_http_requests, run.content_http_requests,
                    run.ai_provider_calls, run.manifest_ref, run.manifest_sha256,
                    run.error_code, run.error_message,
                ),
            )

    def scope_rows(self, property_id: str, environment_id: str, *, run_limit: int = 12) -> tuple[dict[str, Any], ...]:
        rows: list[dict[str, Any]] = []
        query_rows = self.connection.execute(
            """SELECT * FROM search_monitor_queries
               WHERE property_id=? AND environment_id=? ORDER BY query,device""",
            (property_id, environment_id),
        ).fetchall()
        for query_row in query_rows:
            query = self._query(query_row)
            runs = self.list_runs(query.query_id, limit=run_limit)
            rows.append({"query": query, "runs": runs})
        return tuple(rows)

    def scope_for_audit(self, audit_id: str) -> tuple[str, str] | None:
        tables = {
            str(row[0])
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "audit_scope_links" in tables:
            row = self.connection.execute(
                """SELECT property_id,environment_id FROM audit_scope_links
                   WHERE audit_id=? ORDER BY is_primary DESC LIMIT 1""",
                (audit_id,),
            ).fetchone()
            if row is not None:
                return str(row[0]), str(row[1])
        row = self.connection.execute(
            "SELECT property_id,environment_id FROM audit_index WHERE audit_id=?",
            (audit_id,),
        ).fetchone()
        return (str(row[0]), str(row[1])) if row is not None else None


def _page_snapshot(page: CompetitivePageFeatures | None) -> tuple[float | None, float | None, float | None, int | None, tuple[str, ...]]:
    if page is None or page.status.value != "OBSERVED":
        return None, None, None, None, ()
    return (
        page.query_body_coverage,
        _ratio(page.query_terms_in_title, page.query_terms),
        _ratio(page.query_terms_in_headings, page.query_terms),
        page.word_count,
        tuple(sorted(set(page.jsonld_types))),
    )


def build_snapshot(
    search_result: SearchIntelligenceResult,
    analysis: CompetitiveContentAnalysis | None,
    ai_result: Any | None,
    *,
    provider_name: str,
) -> SearchMonitorSnapshot:
    observation = search_result.observation
    page = analysis.customer_page if analysis is not None else None
    body, title, headings, words, jsonld = _page_snapshot(page)
    assessment = getattr(ai_result, "assessment", None) if ai_result is not None else None
    return SearchMonitorSnapshot(
        observation_id=observation.observation_id if observation is not None else None,
        collected_at=observation.collected_at.isoformat() if observation is not None else None,
        provider=observation.provider if observation is not None else provider_name,
        data_mode=observation.data_mode.value if observation is not None else None,
        observation_status=observation.status.value if observation is not None else None,
        domain_status=search_result.domain_status.value,
        customer_position=search_result.customer_position,
        result_count=observation.result_count if observation is not None else 0,
        competitor_domains_ahead=tuple(search_result.competitor_domains_ahead),
        raw_evidence_ref=observation.raw_evidence_ref if observation is not None else None,
        raw_evidence_sha256=observation.raw_evidence_sha256 if observation is not None else None,
        comparison_status=analysis.comparison_status if analysis is not None else None,
        gap_codes=tuple(sorted(gap.code for gap in analysis.gaps)) if analysis is not None else (),
        query_body_coverage=body,
        query_title_coverage=title,
        query_heading_coverage=headings,
        word_count=words,
        jsonld_types=jsonld,
        ai_state=(ai_result.state.value if ai_result is not None else None),
        ai_provider=(assessment.provider if assessment is not None else None),
        ai_model=(assessment.model if assessment is not None else None),
        ai_opportunity_count=(len(assessment.opportunities) if assessment is not None else 0),
    )


def detect_changes(previous: SearchMonitorRun | None, current: SearchMonitorSnapshot) -> tuple[tuple[SearchMonitorChange, ...], bool | None, str | None]:
    if previous is None:
        return (
            (SearchMonitorChange("BASELINE_ESTABLISHED", "Monitoring baseline", None, current.domain_status,
                                 note="First persisted monitoring run; no delta is computed."),),
            None,
            "No previous monitoring run exists for this registered query.",
        )
    before = previous.snapshot
    if before.observation_status != "OBSERVED" or current.observation_status != "OBSERVED":
        return (
            (SearchMonitorChange("NOT_COMPARABLE", "Observation availability", before.observation_status, current.observation_status,
                                 note="Both runs must contain observed provider evidence before numeric changes are compared."),),
            False,
            "At least one monitoring run is not an OBSERVED provider observation.",
        )
    if before.provider != current.provider or before.data_mode != current.data_mode:
        return (
            (SearchMonitorChange(
                "NOT_COMPARABLE", "Search provenance",
                {"provider": before.provider, "data_mode": before.data_mode},
                {"provider": current.provider, "data_mode": current.data_mode},
                note="Provider/data-mode changes are not silently normalized.",
            ),),
            False,
            "Provider or data mode changed between monitoring runs.",
        )

    changes: list[SearchMonitorChange] = []
    before_found = before.domain_status == "FOUND" and before.customer_position is not None
    after_found = current.domain_status == "FOUND" and current.customer_position is not None
    if before_found and after_found:
        delta = int(current.customer_position) - int(before.customer_position)
        status = "POSITION_IMPROVED" if delta < 0 else "POSITION_REGRESSED" if delta > 0 else "POSITION_UNCHANGED"
        changes.append(SearchMonitorChange(
            status, "Observed customer position", before.customer_position, current.customer_position,
            delta=float(delta), unit="positions",
            note="Lower position number is better only within this identical registered Search context.",
        ))
    elif not before_found and after_found:
        changes.append(SearchMonitorChange(
            "ENTERED_OBSERVED_DEPTH", "Customer presence within requested depth",
            before.domain_status, current.customer_position,
            note="Previous absolute rank remains unknown outside the observed depth.",
        ))
    elif before_found and not after_found:
        changes.append(SearchMonitorChange(
            "LEFT_OBSERVED_DEPTH", "Customer presence within requested depth",
            before.customer_position, current.domain_status,
            note="Not observed within depth does not mean the domain does not rank beyond that depth.",
        ))
    elif before.domain_status != current.domain_status:
        changes.append(SearchMonitorChange("DOMAIN_STATUS_CHANGED", "Search domain status", before.domain_status, current.domain_status))
    else:
        changes.append(SearchMonitorChange("OBSERVED_DEPTH_STATE_UNCHANGED", "Search domain status", before.domain_status, current.domain_status))

    before_domains = set(before.competitor_domains_ahead)
    after_domains = set(current.competitor_domains_ahead)
    for domain in sorted(after_domains - before_domains):
        changes.append(SearchMonitorChange("COMPETITOR_AHEAD_ADDED", "Observed domain ahead", False, domain,
                                           note="Observed Search-set change; not a commercial-competitor assertion."))
    for domain in sorted(before_domains - after_domains):
        changes.append(SearchMonitorChange("COMPETITOR_AHEAD_REMOVED", "Observed domain ahead", domain, False,
                                           note="Observed Search-set change; the domain may still rank elsewhere."))

    if before.comparison_status == "CONSOLIDATED" and current.comparison_status == "CONSOLIDATED":
        for field, label in (
            ("query_body_coverage", "Query coverage in body"),
            ("query_title_coverage", "Query coverage in title"),
            ("query_heading_coverage", "Query coverage in headings"),
        ):
            b = getattr(before, field)
            a = getattr(current, field)
            if b is not None and a is not None and b != a:
                changes.append(SearchMonitorChange(
                    "CONTENT_SIGNAL_CHANGED", label, b, a, delta=float(a) - float(b), unit="ratio",
                    note="Deterministic content signal; no ranking-causality claim.",
                ))
        if before.word_count is not None and current.word_count is not None and before.word_count != current.word_count:
            changes.append(SearchMonitorChange(
                "CONTENT_VOLUME_CHANGED", "Observed customer page word count",
                before.word_count, current.word_count,
                delta=float(current.word_count - before.word_count), unit="words",
                note="Content volume has no automatic quality interpretation.",
            ))
        if before.jsonld_types != current.jsonld_types:
            changes.append(SearchMonitorChange(
                "STRUCTURED_DATA_CHANGED", "Observed JSON-LD types", before.jsonld_types, current.jsonld_types,
                note="Markup differences are informational, not automatic recommendations.",
            ))
        before_gaps = set(before.gap_codes)
        after_gaps = set(current.gap_codes)
        for code in sorted(after_gaps - before_gaps):
            changes.append(SearchMonitorChange("DETERMINISTIC_GAP_ADDED", code, False, True,
                                               note="New correlational gap against the current observed leader reference set."))
        for code in sorted(before_gaps - after_gaps):
            changes.append(SearchMonitorChange("DETERMINISTIC_GAP_RESOLVED", code, True, False,
                                               note="Previously observed correlational gap is no longer present."))
    return tuple(changes), True, None


def _write_manifest(root: Path, query: SearchMonitorQuery, run: SearchMonitorRun) -> tuple[str, str]:
    directory = root / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run.monitor_run_id}.json"
    payload = {
        "contract": MONITORING_CONTRACT,
        "query": asdict(query),
        "run": {
            **asdict(run),
            "manifest_ref": None,
            "manifest_sha256": None,
        },
        "interpretation_policy": (
            "Monitoring changes are chronological observations in a fixed query context. "
            "Temporal association does not establish ranking causality."
        ),
    }
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    return path.relative_to(root).as_posix(), digest


def execute_registered_query(
    repository: SearchMonitoringRepository,
    query: SearchMonitorQuery,
    *,
    audits_root: str | Path = "audits",
    environment: Mapping[str, str] | None = None,
    fixture_path: Path | None = None,
    ai_fixture_path: Path | None = None,
    content_fetcher: PublicWebFetcher | None = None,
) -> SearchMonitorRun:
    """Execute one registered query without mutating historical AUD evidence."""
    query.validate()
    if not query.enabled:
        raise ValueError(f"Search monitor query is disabled: {query.query_id}")
    started = _now()
    monitor_run_id = _id("SMON")
    evidence_root = Path(audits_root) / ".rasai" / "search-monitoring"
    evidence_sink = FilesystemSerpEvidenceSink(evidence_root, evidence_root / "artifacts")

    config = SerpRuntimeConfig.from_environment(validate=False)
    config = replace(config, mode=query.mode, provider=query.provider)
    if fixture_path is not None:
        config = replace(config, fixture_path=fixture_path)
    config = config.validate()
    request = SerpQueryRequest(
        query=query.query,
        engine=query.engine,
        country=query.country,
        region=query.region,
        language=query.language,
        device=query.device,
        depth=query.requested_depth,
        domain_of_interest=query.domain_of_interest,
        run_id=monitor_run_id,
        query_origin=QueryOrigin.EXTERNAL,
        config_metadata={
            "surface": "search-monitor",
            "monitor_contract": MONITORING_CONTRACT,
            "query_id": query.query_id,
        },
    )

    try:
        search_execution = execute_search(
            (request,),
            config=config,
            environment=environment,
            fixture_path=fixture_path,
            evidence_sink=evidence_sink,
        )
        competitive_execution = execute_competitive_intelligence(
            search_execution,
            content_enabled=query.compare_content,
            max_competitor_pages=query.max_content_pages,
            fetcher=content_fetcher,
        ) if query.competitive or query.compare_content or query.ai_competitive else None

        ai_execution = None
        ai_result = None
        if query.ai_competitive:
            if competitive_execution is None:
                raise RuntimeError("Competitive AI requires deterministic competitive execution")
            provider = build_competitive_ai_provider(
                query.ai_provider,
                fixture_path=ai_fixture_path,
                model=query.ai_model,
            )
            ai_execution = execute_competitive_ai(
                search_execution,
                competitive_execution,
                provider=provider,
                market=query.country,
                language=query.language,
                ymyl_mode=query.ymyl_mode,
            )
            ai_result = ai_execution.results[0]

        search_result = search_execution.results[0]
        analysis = competitive_execution.analyses[0] if competitive_execution is not None else None
        snapshot = build_snapshot(search_result, analysis, ai_result, provider_name=search_execution.provider)
        previous = repository.latest_run(query.query_id)
        changes, comparable, comparison_note = detect_changes(previous, snapshot)
        status = "SUCCESS" if snapshot.observation_status == "OBSERVED" else "PARTIAL"
        completed = _now()
        provisional = SearchMonitorRun(
            monitor_run_id=monitor_run_id,
            query_id=query.query_id,
            started_at=started,
            completed_at=completed,
            status=status,
            snapshot=snapshot,
            changes=changes,
            comparable_to_previous=comparable,
            comparison_note=comparison_note,
            serp_http_requests=search_execution.actual_http_requests,
            content_http_requests=(competitive_execution.content_http_requests if competitive_execution is not None else 0),
            ai_provider_calls=(ai_execution.provider_calls if ai_execution is not None else 0),
            manifest_ref=None,
            manifest_sha256=None,
            error_code=search_result.error_code,
            error_message=search_result.error_message,
        )
        manifest_ref, manifest_sha = _write_manifest(evidence_root, query, provisional)
        run = replace(provisional, manifest_ref=manifest_ref, manifest_sha256=manifest_sha)
        repository.record_run(run)
        return run
    except Exception as exc:
        completed = _now()
        snapshot = SearchMonitorSnapshot(
            observation_id=None,
            collected_at=None,
            provider=query.provider,
            data_mode=None,
            observation_status=None,
            domain_status="ERROR",
            customer_position=None,
            result_count=0,
            competitor_domains_ahead=(),
            raw_evidence_ref=None,
            raw_evidence_sha256=None,
            comparison_status=None,
            gap_codes=(),
            query_body_coverage=None,
            query_title_coverage=None,
            query_heading_coverage=None,
            word_count=None,
            jsonld_types=(),
            ai_state=None,
            ai_provider=None,
            ai_model=None,
            ai_opportunity_count=0,
        )
        previous = repository.latest_run(query.query_id)
        changes, comparable, comparison_note = detect_changes(previous, snapshot)
        provisional = SearchMonitorRun(
            monitor_run_id=monitor_run_id,
            query_id=query.query_id,
            started_at=started,
            completed_at=completed,
            status="FAILED",
            snapshot=snapshot,
            changes=changes,
            comparable_to_previous=comparable,
            comparison_note=comparison_note,
            serp_http_requests=0,
            content_http_requests=0,
            ai_provider_calls=0,
            manifest_ref=None,
            manifest_sha256=None,
            error_code=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        manifest_ref, manifest_sha = _write_manifest(evidence_root, query, provisional)
        run = replace(provisional, manifest_ref=manifest_ref, manifest_sha256=manifest_sha)
        repository.record_run(run)
        return run


def new_query(**kwargs: Any) -> SearchMonitorQuery:
    now = _now()
    return SearchMonitorQuery(query_id=_id("SQRY"), created_at=now, updated_at=now, **kwargs).validate()
