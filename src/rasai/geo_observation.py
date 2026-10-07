"""Additive, idempotent GEO observation snapshots from persisted search evidence.

No provider, crawler, orchestration or scoring is invoked. Historical records
remain immutable: each distinct input fingerprint receives a distinct run ID.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3


VERSION = "RASAI-GEO-OBSERVATION-1"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _records(con: sqlite3.Connection, sql: str, args: tuple) -> list[dict]:
    return [dict(row) for row in con.execute(sql, args).fetchall()]


def materialize_geo_observation(database: Path, audit_id: str) -> str | None:
    """Freeze a deterministic advisory snapshot after an explicitly requested search.

    Optional external search must already be persisted by its canonical owner.
    This adapter never searches, retries, charges or changes existing evidence.
    """
    with sqlite3.connect(str(database)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        tables = {
            row["name"] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('perplexity_search_runs','perplexity_search_sources',"
                "'serp_observations','serp_results')"
            )
        }
        if not {"perplexity_search_runs", "perplexity_search_sources"}.issubset(tables):
            return None
        runs = _records(
            con, "SELECT run_id, query_json, search_type, status, started_at "
            "FROM perplexity_search_runs WHERE audit_id=? "
            "ORDER BY started_at DESC, run_id DESC LIMIT 1", (audit_id,)
        )
        if not runs:
            return None
        run = runs[0]
        sources = _records(
            con, "SELECT position, url, title, snippet, source_date, last_updated "
            "FROM perplexity_search_sources WHERE run_id=? ORDER BY position, url",
            (run["run_id"],)
        )
        comparable = []
        try:
            query_set = json.loads(run["query_json"])
        except (ValueError, TypeError):
            query_set = []
        serp_id = None
        if ("serp_observations" in tables and "serp_results" in tables
                and isinstance(query_set, list) and len(query_set) == 1
                and isinstance(query_set[0], str)):
            observations = _records(
                con, "SELECT observation_id, query, collected_at "
                "FROM serp_observations WHERE audit_id=? "
                "AND data_mode='OBSERVED_API' AND observation_status='OBSERVED' "
                "ORDER BY collected_at DESC, observation_id DESC", (audit_id,)
            )
            match = next(
                (x for x in observations
                 if str(x["query"]).strip().casefold() ==
                 str(query_set[0]).strip().casefold()), None
            )
            if match:
                serp_id = match["observation_id"]
                comparable = _records(
                    con, "SELECT position, url FROM serp_results "
                    "WHERE observation_id=? ORDER BY position, url", (serp_id,)
                )
        source_urls = {x["url"].strip() for x in sources}
        serp_urls = {x["url"].strip() for x in comparable}
        projection = {
            "contract_version": VERSION,
            "audit_id": audit_id,
            "perplexity_run_id": run["run_id"],
            "search_type": run["search_type"],
            "search_status": run["status"],
            "queries": query_set,
            "source_count": len(sources),
            "serp_observation_id": serp_id,
            "serp_url_count": len(serp_urls) if serp_id else None,
            "perplexity_url_count": len(source_urls),
            "url_overlap_count": len(source_urls & serp_urls) if serp_id else None,
            "limitation": (
                "A busca externa nao equivale a resposta/citacao generativa; "
                "nao ha atribuicao de fontes a consultas individuais em multi-query. "
                "Sobreposicao nao demonstra causalidade ou representatividade."
            ),
        }
        inputs = {"run": run, "sources": sources, "serp": comparable,
                  "serp_observation_id": serp_id}
        fingerprint = hashlib.sha256(_canonical_json(inputs).encode("utf-8")).hexdigest()
        analysis_id = "GEO-" + hashlib.sha256(
            (audit_id + ":" + VERSION + ":" + fingerprint).encode("utf-8")
        ).hexdigest()[:32].upper()
        con.executescript("""
            CREATE TABLE IF NOT EXISTS geo_observation_runs (
                analysis_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                perplexity_run_id TEXT NOT NULL
                    REFERENCES perplexity_search_runs(run_id) ON DELETE CASCADE,
                serp_observation_id TEXT,
                contract_version TEXT NOT NULL,
                input_sha256 TEXT NOT NULL,
                projection_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_geo_observation_audit
                ON geo_observation_runs(audit_id, created_at);
        """)
        con.execute(
            "INSERT OR IGNORE INTO geo_observation_runs("
            "analysis_id,audit_id,perplexity_run_id,serp_observation_id,"
            "contract_version,input_sha256,projection_json,created_at)"
            "VALUES (?,?,?,?,?,?,?,?)",
            (analysis_id, audit_id, run["run_id"], serp_id, VERSION,
             fingerprint, _canonical_json(projection),
             datetime.now(timezone.utc).isoformat())
        )
    return analysis_id
