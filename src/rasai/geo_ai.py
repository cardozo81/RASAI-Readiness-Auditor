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

from rasai.geo_temporal_provenance import _last_temporally_verified, _UNVERIFIABLE
from rasai.geo_observation import _canonical_url

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
    selected = ("run_id", "query_json", "status")
    latest = _last_temporally_verified(
        con, table="perplexity_search_runs", audit_id=audit_id,
        columns=selected, time_column="started_at",
    )
    if latest is None or latest is _UNVERIFIABLE or latest[2] != "SUCCESS":
        return None
    row = dict(zip(selected, latest))
    try:
        queries = json.loads(row["query_json"])
    except (TypeError, ValueError):
        return None
    if not isinstance(queries, list) or len(queries) != 1 or not isinstance(queries[0], str):
        return None
    sources = [dict(x) for x in con.execute(
        "SELECT position, url, title, snippet FROM perplexity_search_sources "
        # Read a bounded candidate window, then select up to 12 VALID
        # sources. A poisoned leading result must not consume an evidence
        # slot or suppress a real source further down the provider response.
        "WHERE run_id=? ORDER BY position, url LIMIT 256", (row["run_id"],)
    )]
    # Source metadata is untrusted provider input. An invalid/userinfo/
    # javascript URL must not become an evidence reference or prompt context
    # solely because a row was persisted. Do not fetch/rewrite the sources.
    sources = [
        x for x in sources
        if isinstance(x.get("url"), str)
        and len(x["url"]) <= 2048
        and bool(_canonical_url(x["url"]))
    ][:12]
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
                "url": x["url"], "title": str(x["title"] or "")[:240],
                "snippet": str(x["snippet"] or "")[:900],
                "limitation": "Snippet metadata only; no full competitor page inspection.",
            },
        )
        for x in sources
    )
    audit_columns = {x[1] for x in con.execute("PRAGMA table_info(audits)")}
    audit_context = (
        con.execute(
            "SELECT market, primary_language FROM audits WHERE audit_id=?", (audit_id,)
        ).fetchone()
        if {"market", "primary_language"}.issubset(audit_columns)
        else None
    )
    market = str(audit_context["market"] or "BR") if audit_context else "BR"
    language = (
        str(audit_context["primary_language"] or "pt-BR")
        if audit_context else "pt-BR"
    )
    obj = CompetitiveAiInput(
        observation_id=row["run_id"],
        query=queries[0],
        market=market,
        language=language,
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
    # No eligible persisted AUD must never turn a typo/nonexistent path into
    # an empty SQLite database merely because optional AI was requested.
    database = Path(database)
    if not database.is_file() or database.is_symlink():
        return "NOT_ELIGIBLE"
    with closing(sqlite3.connect(
        database.resolve().as_uri() + "?mode=rw", uri=True
    )) as con, con:
        con.execute("PRAGMA foreign_keys=ON")
        # An explicit AI request is not equivalent to having eligible source
        # evidence. Probe only the canonical persisted Perplexity rows first:
        # a no-search/failed/multi-query AUD must not acquire even an empty
        # AI table just because the operator toggled an optional feature.
        prepared = _prepare(con, audit_id)
        if prepared is None:
            return "NOT_ELIGIBLE"
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
        run_id, competitive_input, input_hash = prepared
        result_id = "GEOAI-" + sha256(
            f"{audit_id}|{run_id}|{selection}|{VERSION}|{input_hash}".encode("utf-8")
        ).hexdigest()[:32].upper()
        existing = con.execute(
            "SELECT state FROM geo_ai_interpretations WHERE result_id=?", (result_id,)
        ).fetchone()
        if existing is not None:
            return str(existing[0])
        injected_test_factory = provider_factory is not None
        if provider_factory is None:
            from rasai.search_intelligence import competitive_ai
            if not hasattr(competitive_ai, "OrchestratedCompetitiveAiProvider"):
                return "CANONICAL_AI_NOT_INSTALLED"
            provider_factory = competitive_ai.build_competitive_ai_provider
        # Never infer injection from __module__: the real canonical builder
        # lives in search_intelligence, not ai_orchestration_unification.
        # Only an explicit factory argument is eligible as a test adapter.
        try:
            provider = provider_factory(selection)
        except Exception:
            # The selected canonical consumer cannot be initialized; never
            # substitute a private provider or retry through another model.
            return "CANONICAL_AI_UNAVAILABLE"
        if not injected_test_factory and provider.__class__.__name__ != "OrchestratedCompetitiveAiProvider":
            return "CANONICAL_AI_NOT_INSTALLED"
        # Reserve the fingerprint BEFORE the first potentially chargeable AI
        # request. A process crash or forced shutdown during analyze() must
        # not turn the next operator click into a second billable attempt.
        # Commit the reservation independently of the provider execution.
        reservation = con.execute(
            "INSERT OR IGNORE INTO geo_ai_interpretations("
            "result_id,audit_id,perplexity_run_id,contract_version,input_sha256,"
            "selection,state,opportunities_json,error_reason,created_at)"
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (result_id, audit_id, run_id, VERSION, input_hash, selection,
             "PENDING_UNCERTAIN", "[]", "GEO_AI_OUTCOME_NOT_YET_PERSISTED",
             datetime.now(timezone.utc).isoformat()),
        )
        reserved_by_this_execution = reservation.rowcount == 1
        con.commit()
        if not reserved_by_this_execution:
            # Another process has already reserved or finished this intent.
            # No provider execution is allowed until explicitly reconciled.
            saved = con.execute(
                "SELECT state FROM geo_ai_interpretations WHERE result_id=?",
                (result_id,),
            ).fetchone()
            return str(saved[0]) if saved else "PENDING_UNCERTAIN"
        try:
            output = provider.analyze(competitive_input)
            assessment = output.assessment
            state = str(getattr(output.state, "value", output.state))
            error_reason = output.reason
        except Exception:
            # A request may already have been submitted or charged. Persist the
            # terminal ambiguity under the input fingerprint: no automatic
            # retry during report materialization or a repeated operator click.
            assessment = None
            state = "UNAVAILABLE"
            error_reason = "GEO_AI_CANONICAL_EXECUTION_ERROR"
        if state == "AVAILABLE" and assessment is None:
            state = "UNAVAILABLE"
            error_reason = "GEO_AI_EMPTY_CANONICAL_ASSESSMENT"
        elif state != "AVAILABLE":
            # Do not publish misleading summaries attached to failed provider output.
            assessment = None
        if assessment is not None and any(
            not opportunity.evidence_ids
            or not set(opportunity.evidence_ids).issubset(competitive_input.allowed_evidence_ids)
            for opportunity in assessment.opportunities
        ):
            # Defense in depth: never publish an otherwise valid-looking summary
            # if a consumer bypasses the canonical evidence-ID validator.
            assessment = None
            state = "UNAVAILABLE"
            error_reason = "GEO_AI_INVALID_EVIDENCE_REFERENCES"
        if assessment is not None:
            opportunities = [
                {
                    "category": str(getattr(o.category, "value", o.category)),
                    "priority": str(getattr(o.priority, "value", o.priority)),
                    "title": o.title,
                    "recommendation": o.recommendation,
                    "rationale": o.rationale,
                    "causality_note": o.causality_note,
                    "confidence": o.confidence,
                    "evidence_ids": list(o.evidence_ids),
                }
                for o in assessment.opportunities
                if o.evidence_ids and set(o.evidence_ids).issubset(competitive_input.allowed_evidence_ids)
            ]
        else:
            opportunities = []
        con.execute(
            "UPDATE geo_ai_interpretations "
            "SET state=?,provider=?,model=?,prompt_id=?,prompt_version=?,"
            "provider_request_id=?,summary=?,opportunities_json=?,error_reason=? "
            "WHERE result_id=? AND state='PENDING_UNCERTAIN'",
            (
                state,
                assessment.provider if assessment is not None else None,
                assessment.model if assessment is not None else None,
                assessment.prompt_id if assessment is not None else None,
                assessment.prompt_version if assessment is not None else None,
                assessment.provider_request_id if assessment is not None else None,
                assessment.summary if assessment is not None else None,
                _json(opportunities), error_reason, result_id,
            ),
        )
        return state
