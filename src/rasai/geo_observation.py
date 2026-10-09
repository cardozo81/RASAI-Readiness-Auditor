"""Additive, idempotent GEO observation snapshots from persisted search evidence.

No provider, crawler, orchestration or scoring is invoked. Historical records
remain immutable: each distinct input fingerprint receives a distinct run ID.
"""
from __future__ import annotations

from contextlib import closing

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit


# Versioned immutable projection: v4 adds verifiable temporal eligibility.
# Legacy v1/v2/v3 observations remain persisted and immutable.
VERSION = "RASAI-GEO-OBSERVATION-4"
_MAX_OBSERVATION_GAP_SECONDS = 24 * 60 * 60


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _records(con: sqlite3.Connection, sql: str, args: tuple) -> list[dict]:
    return [dict(row) for row in con.execute(sql, args).fetchall()]



def _canonical_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return ""
        scheme = parsed.scheme.lower()
        authority = parsed.hostname.lower().removeprefix("www.")
        if ":" in authority:  # IPv6 canonical authority
            authority = "[" + authority + "]"
        port = parsed.port  # invalid/out-of-range port raises ValueError
        if port is not None and port != (443 if scheme == "https" else 80):
            authority += ":" + str(port)
        path = parsed.path.rstrip("/") or "/"
        # Never treat HTTP and HTTPS, or distinct ports, as the exact URL.
        # Retain the query string: parameters can select different content.
        return scheme + "://" + authority + path + ("?" + parsed.query if parsed.query else "")
    except ValueError:
        return ""


def _host(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            return ""
        return (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _temporal_gap_seconds(search_started: object, serp_collected: object) -> float | None:
    """Only offset-aware clocks establish a cross-source observation window."""
    try:
        a = datetime.fromisoformat(str(search_started).replace("Z", "+00:00"))
        b = datetime.fromisoformat(str(serp_collected).replace("Z", "+00:00"))
        if a.tzinfo is None or b.tzinfo is None:
            return None
        return abs((a.astimezone(timezone.utc) - b.astimezone(timezone.utc)).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return None


def _target_observation(
    con: sqlite3.Connection, audit_id: str, run: dict,
    queries: object, sources: list[dict]
) -> dict:
    targets_table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='audit_targets'"
    ).fetchone()
    targets = _records(con, "SELECT input_url FROM audit_targets WHERE audit_id=? "
                       "ORDER BY target_id", (audit_id,)) if targets_table else []
    if len(targets) != 1 or not isinstance(queries, list) or len(queries) != 1:
        return {
            "status": "NOT_COMPARABLE",
            "explanation": "Alvo unico ou atribuicao por consulta indisponivel.",
            "recommendation": None,
            "evidence_run_id": run["run_id"],
        }
    target = targets[0]["input_url"]
    desired = _canonical_url(target)
    domain = _host(target)
    if not desired or not domain or str(run["status"]).upper() != "SUCCESS":
        return {"status": "UNAVAILABLE", "explanation": "Observacao incompleta.",
                "recommendation": None, "evidence_run_id": run["run_id"]}
    source_urls = [str(item["url"]) for item in sources]
    exact = [url for url in source_urls if _canonical_url(url) == desired]
    alternatives = [url for url in source_urls
                    if _host(url) == domain and _canonical_url(url) != desired]
    competitors = [url for url in source_urls if _host(url) and _host(url) != domain]
    if exact:
        status = "EXACT_URL_OBSERVED"
        action = "Preservar fatos verificaveis e acompanhar a mesma consulta em novas observacoes."
    elif alternatives:
        status = "DOMAIN_ALTERNATIVE_OBSERVED"
        action = "Investigar a relacao entre a URL auditada e as URLs alternativas do dominio; nao presumir problema de canonical."
    else:
        status = "TARGET_NOT_IN_RETURNED_SOURCES"
        action = "Revisar cobertura da intencao, clareza da oferta e evidencias no CAT-03 antes de propor remediacao."
    return {
        "status": status,
        "target_url": target,
        "query": queries[0],
        "evidence_run_id": run["run_id"],
        "exact_sources": exact,
        "domain_alternatives": alternatives,
        "other_domain_sources": competitors,
        "recommendation": action,
        "causality": "Observacao pontual; nao prova inclusao em resposta gerativa nem causa de ausencia.",
    }



def _descriptive_overlap_metrics(
    perplexity_urls: set[str], serp_urls: set[str], *, serp_id: str | None,
    query_set: object, search_status: str, time_gap_seconds: float | None = None,
) -> dict:
    """Rates describe only URL-set membership, not equivalent provider coverage.

    No per-query mapping is inferred from aggregated multi-query Search API runs.
    Denominators are distinct, valid canonical URLs, never request counts.
    """
    metrics = {
        "status": "NOT_COMPARABLE",
        "reason": None,
        "serp_denominator": len(serp_urls) if serp_id else None,
        "perplexity_denominator": len(perplexity_urls),
        "common_urls": None,
        "serp_overlap_rate": None,
        "perplexity_overlap_rate": None,
        "jaccard_url_rate": None,
        "serp_only_count": None,
        "perplexity_only_count": None,
    }
    if search_status.upper() != "SUCCESS":
        metrics["reason"] = "EXTERNAL_SEARCH_NOT_SUCCESSFUL"
    elif not isinstance(query_set, list) or len(query_set) != 1 or not isinstance(query_set[0], str) or not query_set[0].strip():
        metrics["reason"] = "UNATTRIBUTABLE_QUERY_SET"
    elif not serp_id:
        metrics["reason"] = "NO_EQUIVALENT_OBSERVED_SERP_QUERY"
    elif time_gap_seconds is None:
        metrics["reason"] = "TIME_SCOPE_UNPROVEN"
    elif time_gap_seconds > _MAX_OBSERVATION_GAP_SECONDS:
        metrics["reason"] = "TIME_SCOPE_OUTSIDE_WINDOW"
    elif not serp_urls or not perplexity_urls:
        metrics["reason"] = "NO_VALID_URL_DENOMINATOR"
    else:
        both = len(serp_urls & perplexity_urls)
        union = len(serp_urls | perplexity_urls)
        metrics.update(
            status="DESCRIPTIVE_ONLY",
            common_urls=both,
            serp_overlap_rate=round(both / len(serp_urls), 4),
            perplexity_overlap_rate=round(both / len(perplexity_urls), 4),
            jaccard_url_rate=round(both / union, 4),
            serp_only_count=len(serp_urls - perplexity_urls),
            perplexity_only_count=len(perplexity_urls - serp_urls),
        )
    return metrics


def materialize_geo_observation(database: Path, audit_id: str) -> str | None:
    """Freeze a deterministic advisory snapshot after an explicitly requested search.

    Optional external search must already be persisted by its canonical owner.
    This adapter never searches, retries, charges or changes existing evidence.
    """
    with closing(sqlite3.connect(str(database))) as con, con:
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
        serp_scope = None
        time_gap_seconds = None
        if ("serp_observations" in tables and "serp_results" in tables
                and isinstance(query_set, list) and len(query_set) == 1
                and isinstance(query_set[0], str)):
            serp_columns = {
                str(row[1]) for row in con.execute("PRAGMA table_info(serp_observations)")
            }
            extra_scope = ("engine", "country", "region", "language", "device")
            scope_sql = ", ".join(
                name if name in serp_columns else "NULL AS " + name
                for name in extra_scope
            )
            observations = _records(
                con, "SELECT observation_id, query, collected_at, " + scope_sql + " "
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
                time_gap_seconds = _temporal_gap_seconds(run["started_at"], match["collected_at"])
                serp_scope = {
                    key: match.get(key)
                    for key in ("query", "collected_at", "engine", "country",
                                "region", "language", "device")
                }
                comparable = _records(
                    con, "SELECT position, url FROM serp_results "
                    "WHERE observation_id=? ORDER BY position, url", (serp_id,)
                )
        source_urls = {_canonical_url(x["url"]) for x in sources if _canonical_url(x["url"])}
        serp_urls = {_canonical_url(x["url"]) for x in comparable if _canonical_url(x["url"])}
        target_observation = _target_observation(con, audit_id, run, query_set, sources)
        overlap_metrics = _descriptive_overlap_metrics(
            source_urls, serp_urls, serp_id=serp_id, query_set=query_set,
            search_status=str(run["status"]), time_gap_seconds=time_gap_seconds,
        )
        projection = {
            "target_observation": target_observation,
            "contract_version": VERSION,
            "audit_id": audit_id,
            "perplexity_run_id": run["run_id"],
            "search_type": run["search_type"],
            "search_status": run["status"],
            "queries": query_set,
            "source_count": len(sources),
            "serp_observation_id": serp_id,
            "comparability": {
                "query_equivalent": serp_id is not None,
                "query_text_match_only": serp_id is not None,
                "intent_equivalence_proven": False,
                "time_gap_seconds": time_gap_seconds,
                "time_window_within_24h": (
                    time_gap_seconds <= _MAX_OBSERVATION_GAP_SECONDS
                    if time_gap_seconds is not None else None
                ),
                "geo_language_device_time_equivalence_proven": False,
                "serp_context": serp_scope,
                "perplexity_context": {
                    "search_type": run["search_type"],
                    "started_at": run["started_at"],
                    "geography_language_device": None,
                },
                "limitation": (
                    "Coincidencia textual da consulta nao comprova equivalencia "
                    "de mercado, intencao, idioma, dispositivo ou motor; janela temporal de 24h e so elegibilidade observacional."
                ),
            },
            "serp_url_count": len(serp_urls) if serp_id else None,
            "perplexity_url_count": len(source_urls),
            "url_overlap_count": len(source_urls & serp_urls) if serp_id else None,
            "descriptive_overlap": overlap_metrics,
            "limitation": (
                "A busca externa nao equivale a resposta/citacao generativa; "
                "nao ha atribuicao de fontes a consultas individuais em multi-query. "
                "Sobreposicao nao demonstra causalidade ou representatividade."
            ),
        }
        inputs = {"run": run, "sources": sources, "target": target_observation, "serp": comparable,
                  "serp_observation_id": serp_id, "serp_scope": serp_scope}
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
