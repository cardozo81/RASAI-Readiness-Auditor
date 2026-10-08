"""Optional GEO competitive interpretation via the existing canonical AI consumer.

No AI transport, retry, provider registry, billing or scoring implementation lives here.
The operator must explicitly request GEO AI for the current AUD. Reprocessing and
HTML rematerialization never invoke this module's execution entrypoint.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from rasai.search_intelligence.competitive_ai import (
    CompetitiveAiEvidence, CompetitiveAiInput, CompetitiveAiState,
)


VERSION = "RASAI-GEO-COMPETITIVE-AI-1"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _prepare(con: sqlite3.Connection, audit_id: str) -> tuple[str, CompetitiveAiInput, str] | None:
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name IN ('perplexity_search_runs', 'perplexity_search_sources')"
    )}
    if len(tables) != 2:
        return None
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT run_id, query_json, status FROM perplexity_search_runs "
        "WHERE audit_id=? ORDER BY started_at DESC, run_id DESC LIMIT 1", (audit_id,)
    ).fetchone()
    if row is None or row["status"] != "SUCCESS":
        return None
    try:
        queries = json.loads(row["query_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(queries, list) or len(queries) != 1 or not isinstance(queries[0], str):
        return None
    sources = [dict(x) for x in con.execute(
        "SELECT position, url, title, snippet FROM perplexity_search_sources "
        "WHERE run_id=? ORDER BY position, url LIMIT 12", (row["run_id"],)
    )]
    if not sources:
        return None
    evidence = tuple(
        CompetitiveAiEvidence(
            evidence_id=(
                f"PX:{row['run_id']}:{x['position']}:"
                f"{sha256(str(x['url']).encode('utf-8')).hexdigest()[:10]}"
            ),
            evidence_type="EXTERNAL_SEARCH_RESULT_METADATA",
            source="PERPLEXITY_SEARCH_API",
            observed_value={
                "url": x["url"], "title": x["title"],
                "snippet": str(x["snippet"] or "")[:900],
                "limitation": "Snippet metadata only; no full competitor page inspection.",
            },
        )
        for x in sources
    )
    obj = CompetitiveAiInput(
        observation_id=row["run_id"],
        query=queries[0],
        market="BR",
        language="pt-BR",
        ymyl_mode="AUTO",
        evidence=evidence,
    )
    payload_hash = sha256(_json(obj.provider_payload()).encode("utf-8")).hexdigest()
    return str(row["run_id"]), obj, payload_hash


def execute_geo_ai(
    database: Path, audit_id: str, *,
    provider_selection: str,
    provider_factory: Callable[..., Any] | None = None,
) -> str:
    """Opt-in only. Reuse one persisted inference for identical input/provider.

    In production, the factory must be the already installed canonical competitive
    consumer. No fallback provider/transport is constructed by this module.
    """
    selection = provider_selection.strip().casefold()
    if selection in {"", "none", "fixture"}:
        return "NOT_CONFIGURED"
    with closing(sqlite3.connect(str(database))) as con, con:
        con.execute("PRAGMA foreign_keys=ON")
        con.executescript("""
            CREATE TABLE IF NOT EXISTS geo_ai_interpretations (
                result_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                perplexity_run_id TEXT NOT NULL
                    REFERENCES perplexity_search_runs(run_id) ON DELETE CASCADE,
                contract_version TEXT NOT NULL,
                input_sha256 TEXT NOT NULL,
                selection TEXT NOT NULL,
                state TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                prompt_id TEXT,
                prompt_version TEXT,
                provider_request_id TEXT,
                summary TEXT,
                opportunities_json TEXT NOT NULL,
                error_reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_geo_ai_audit
                ON geo_ai_interpretations(audit_id, created_at);
        """)
        prepared = _prepare(con, audit_id)
        if prepared is None:
            return "NOT_ELIGIBLE"
        run_id, competitive_input, input_hash = prepared
        result_id = "GEOAI-" + sha256(
            f"{audit_id}|{run_id}|{selection}|{VERSION}|{input_hash}".encode("utf-8")
        ).hexdigest()[:32].upper()
        existing = con.execute(
            "SELECT state FROM geo_ai_interpretations WHERE result_id=?", (result_id,)
        ).fetchone()
        if existing is not None:
            return str(existing[0])
        if provider_factory is None:
            from rasai.search_intelligence import competitive_ai
            if not hasattr(competitive_ai, "OrchestratedCompetitiveAiProvider"):
                return "CANONICAL_AI_NOT_INSTALLED"
            provider_factory = competitive_ai.build_competitive_ai_provider
        injected_test_factory = provider_factory is not None and getattr(provider_factory, "__module__", "") != "rasai.ai_orchestration_unification"
        provider = provider_factory(selection)
        if not injected_test_factory and provider.__class__.__name__ != "OrchestratedCompetitiveAiProvider":
            return "CANONICAL_AI_NOT_INSTALLED"
        output = provider.analyze(competitive_input)
        assessment = output.assessment
        state = str(getattr(output.state, "value", output.state))
        if assessment is not None:
            opportunities = [
                {
                    "category": str(getattr(o.category, "value", o.category)),
                    "priority": str(getattr(o.priority, "value", o.priority)),
                    "title": o.title,
                    "recommendation": o.recommendation,
                    "rationale": o.rationale,
                    "confidence": o.confidence,
                    "evidence_ids": list(o.evidence_ids),
                }
                for o in assessment.opportunities
                if o.evidence_ids and set(o.evidence_ids).issubset(competitive_input.allowed_evidence_ids)
            ]
        else:
            opportunities = []
        con.execute(
            "INSERT OR IGNORE INTO geo_ai_interpretations("
            "result_id,audit_id,perplexity_run_id,contract_version,input_sha256,"
            "selection,state,provider,model,prompt_id,prompt_version,provider_request_id,"
            "summary,opportunities_json,error_reason,created_at)"
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                result_id, audit_id, run_id, VERSION, input_hash, selection, state,
                assessment.provider if assessment is not None else None,
                assessment.model if assessment is not None else None,
                assessment.prompt_id if assessment is not None else None,
                assessment.prompt_version if assessment is not None else None,
                assessment.provider_request_id if assessment is not None else None,
                assessment.summary if assessment is not None else None,
                _json(opportunities), output.reason,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return state
