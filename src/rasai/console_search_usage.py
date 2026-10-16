"""Read-only Perplexity Search API telemetry for console cost separation (#319).

The Search API writes an M18 attempt envelope for operational provenance, but
it is NOT a generative inference. This projection never changes those ledgers.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3

_CONTRACT = "RASAI-PERPLEXITY-SEARCH-1"
_NATIVE_REQUEST = "PERPLEXITY_SEARCH_REQUEST"
_MAX_RUNS = 5000
_MAX_QUERY_JSON = 32768


@dataclass(frozen=True, slots=True)
class SearchUsage:
    runs: int
    requests: float
    queries: int | None
    sources: int | None
    envelope_attempts: int | None
    envelope_successes: int | None
    estimated_costs: tuple[tuple[str, float], ...]
    unpriced_runs: int


def _exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def read_perplexity_search_usage(workspace: Path | None, audit_id: str) -> SearchUsage | None:
    """Return only physically persisted Search API evidence for this AUD.

    Missing or incompatible schemas are not converted to fabricated zeros. An invalid
    query payload marks its count unavailable, without suppressing the run.
    """
    if workspace is None or not str(audit_id).strip():
        return None
    database = Path(workspace) / "audit.db"
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.5)) as con:
            con.execute("PRAGMA query_only=ON")
            if not _exists(con, "perplexity_search_runs"):
                return None
            rows = con.execute(
                """
                SELECT run_id,query_json,native_usage_unit,native_usage_quantity,
                       estimated_cost,cost_currency
                FROM perplexity_search_runs
                WHERE audit_id=?
                ORDER BY started_at,run_id
                LIMIT ?
                """,
                (audit_id, _MAX_RUNS + 1),
            ).fetchall()
            if not rows or len(rows) > _MAX_RUNS:
                return None
            count_queries: int | None = 0
            requests = 0.0
            amounts: dict[str, float] = {}
            unpriced = 0
            for _run_id, raw_query, unit, quantity, cost, currency in rows:
                if count_queries is not None:
                    try:
                        if len(str(raw_query)) > _MAX_QUERY_JSON:
                            raise ValueError("query evidence exceeds safe limit")
                        parsed = json.loads(str(raw_query))
                        if not isinstance(parsed, list) or not all(
                            isinstance(item, str) for item in parsed
                        ):
                            raise ValueError("invalid query list")
                        count_queries += len(parsed)
                    except (ValueError, TypeError):
                        count_queries = None
                if unit == _NATIVE_REQUEST and quantity is not None:
                    number = float(quantity)
                    if math.isfinite(number) and number >= 0:
                        requests += number
                if cost is None or not str(currency or "").strip():
                    unpriced += 1
                else:
                    amount = float(cost)
                    if math.isfinite(amount) and amount >= 0:
                        code = str(currency).upper()
                        amounts[code] = amounts.get(code, 0.0) + amount
                    else:
                        unpriced += 1

            if _exists(con, "perplexity_search_sources"):
                sources = int(con.execute(
                    """
                    SELECT COUNT(*) FROM perplexity_search_sources s
                    JOIN perplexity_search_runs r ON r.run_id=s.run_id
                    WHERE r.audit_id=?
                    """,
                    (audit_id,),
                ).fetchone()[0] or 0)
            else:
                sources = None

            envelopes = successes = None
            if _exists(con, "ai_provider_attempts"):
                columns = {
                    item[1] for item in con.execute("PRAGMA table_info(ai_provider_attempts)")
                }
                if {"audit_id", "operation", "semantic_contract_version", "status"} <= columns:
                    row = con.execute(
                        """
                        SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END),0)
                        FROM ai_provider_attempts
                        WHERE audit_id=? AND operation='SEARCH_INTELLIGENCE'
                          AND semantic_contract_version=?
                        """,
                        (audit_id, _CONTRACT),
                    ).fetchone()
                    envelopes, successes = int(row[0]), int(row[1])
    except (sqlite3.Error, OSError, ValueError, OverflowError):
        return None
    return SearchUsage(
        runs=len(rows),
        requests=requests,
        queries=count_queries,
        sources=sources,
        envelope_attempts=envelopes,
        envelope_successes=successes,
        estimated_costs=tuple(sorted((code, round(value, 10)) for code, value in amounts.items())),
        unpriced_runs=unpriced,
    )
