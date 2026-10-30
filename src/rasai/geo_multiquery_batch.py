"""Bounded, opt-in GEO Search batch provenance (issues #681/#682).

Only the initial explicitly authorised AUD flow writes this additive table.
Readers are offline; no source association is inferred from aggregated searches.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

CONTRACT = "RASAI-GEO-MULTIQUERY-BATCH-1"
_MAX_ROWS = 5


def request_fingerprint(queries: tuple[str, ...], search_type: str, *,
                        search_options: Mapping[str, Any] | None = None,
                        target: str = "") -> str:
    """Bind consent to terms, effective provider filters and target scope."""
    mode = str(search_type).strip().casefold()
    from rasai.search_intelligence.perplexity_request_policy import validate_request_options
    normalized = validate_request_options(search_options or {}, search_type=mode)
    value = {
        "contract": CONTRACT,
        "queries": list(queries),
        "search_type": mode,
        "search_options": normalized,
        "target": str(target or "").strip(),
    }
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")).hexdigest()


def estimated_search_cost_usd(query_count: int, search_type: str) -> float | None:
    """Read the canonical request-price catalog; unknown pricing stays N/D."""
    if not 1 <= query_count <= _MAX_ROWS or search_type.lower() not in {"web", "fast"}:
        raise ValueError("invalid GEO Search batch")
    from rasai.ai_economic_telemetry import price_native_usage
    from rasai.ai_native_usage import NativeUsageComponent, PERPLEXITY_SEARCH_REQUEST
    from math import isfinite
    now = datetime.now(timezone.utc)
    quote = price_native_usage(
        "PERPLEXITY", "SEARCH_API",
        (NativeUsageComponent(
            unit=PERPLEXITY_SEARCH_REQUEST, quantity=float(query_count),
            source_metric="perplexity.search.request", component_type="REQUEST",
            billable=True, observed_at=now,
        ),), now,
        runtime_conditions={"search_type": search_type.upper(), "operation_mode": "REALTIME"},
    )
    cost = quote.estimated_cost
    return float(cost) if cost is not None and isfinite(float(cost)) and cost >= 0 else None


def _database(path: Path) -> Path:
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("GEO batch requires an existing, regular audit.db")
    return path.resolve()


def reserve_batch(database: Path, audit_id: str, queries: tuple[str, ...],
                  search_type: str, *, search_options: Mapping[str, Any] | None = None,
                  target: str = "") -> str:
    """Persist all intended requests BEFORE sending any potentially billable call."""
    if not 2 <= len(queries) <= _MAX_ROWS or any(not isinstance(q, str) or not q.strip() for q in queries):
        raise ValueError("multiquery batch requires 2..5 nonempty queries")
    if len(set(queries)) != len(queries):
        raise ValueError("duplicate queries not allowed")
    fingerprint = request_fingerprint(queries, search_type,
                                     search_options=search_options, target=target)
    created_at = datetime.now(timezone.utc).isoformat()
    batch_id = "GQB-" + uuid4().hex.upper()
    items = [
        {"position": pos, "query": query, "run_id": None,
         "search_state": "PENDING_UNCERTAIN", "geo_ai_state": "NOT_EXECUTED",
         "reason": "PROVIDER_OUTCOME_NOT_YET_PERSISTED"}
        for pos, query in enumerate(queries)
    ]
    with sqlite3.connect(_database(database).as_uri() + "?mode=rw", uri=True) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("""
            CREATE TABLE IF NOT EXISTS geo_search_batches (
                batch_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                contract_version TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,
                query_json TEXT NOT NULL,
                search_type TEXT NOT NULL,
                items_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # Unique DB constraint closes the cross-process TOCTOU window before
        # any billable request. Do not rely on SELECT alone for concurrency.
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_geo_batch_intent "
                    "ON geo_search_batches(audit_id, request_fingerprint)")
        # Fail closed on repeat activation of the same paid intent. A new
        # physical observation requires a separately authorised supplement/AUD;
        # neither a crash nor repeated console dispatch may re-send the batch.
        if con.execute(
            "SELECT 1 FROM geo_search_batches WHERE audit_id=? "
            "AND request_fingerprint=? LIMIT 1",
            (audit_id, fingerprint),
        ).fetchone():
            raise ValueError("GEO batch already reserved: no automatic resend")
        try:
            con.execute(
                "INSERT INTO geo_search_batches VALUES (?,?,?,?,?,?,?,?)",
                (batch_id, audit_id, CONTRACT, fingerprint,
                 json.dumps(queries, ensure_ascii=False), search_type.lower(),
                 json.dumps(items, ensure_ascii=False), created_at),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("GEO batch already reserved or invalid audit identity") from exc
    return batch_id


def record_item(database: Path, audit_id: str, batch_id: str, position: int, *,
                run_id: str | None, search_state: str, geo_ai_state: str,
                reason: str | None = None) -> None:
    """Update only one item, preserving other successes and ambiguous failures."""
    with sqlite3.connect(_database(database).as_uri() + "?mode=rw", uri=True) as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT items_json FROM geo_search_batches WHERE audit_id=? AND batch_id=?",
            (audit_id, batch_id),
        ).fetchone()
        if row is None:
            raise ValueError("GEO batch does not belong to this audit")
        items = json.loads(row[0])
        if not isinstance(position, int) or not 0 <= position < len(items):
            raise ValueError("GEO batch item out of range")
        item = items[position]
        if item["search_state"] != "PENDING_UNCERTAIN":
            raise ValueError("GEO batch item already terminal; automatic retry denied")
        item.update(
            run_id=run_id, search_state=str(search_state),
            geo_ai_state=str(geo_ai_state), reason=(str(reason)[:200] if reason else None),
        )
        con.execute(
            "UPDATE geo_search_batches SET items_json=? WHERE batch_id=? AND audit_id=?",
            (json.dumps(items, ensure_ascii=False), batch_id, audit_id),
        )


def latest_batch(database: Path, audit_id: str) -> dict | None:
    """Read-only report projection, including partial and uncertain outcomes."""
    try:
        target = _database(database)
        with sqlite3.connect(target.as_uri() + "?mode=ro", uri=True) as con:
            if not con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='geo_search_batches'"
            ).fetchone():
                return None
            rows = con.execute(
                "SELECT batch_id,contract_version,query_json,search_type,items_json,"
                "created_at FROM geo_search_batches WHERE audit_id=?",
                (audit_id,),
            ).fetchall()
            if not rows:
                return None
            def stamp(row: tuple) -> datetime:
                parsed = datetime.fromisoformat(str(row[5]).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    raise ValueError("unverifiable GEO batch clock")
                return parsed.astimezone(timezone.utc)
            ranked = sorted(((stamp(row), row) for row in rows),
                            key=lambda pair: pair[0], reverse=True)
            if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
                return None
            _, row = ranked[0]
            if row[1] != CONTRACT:
                return None
            queries = json.loads(row[2])
            items = json.loads(row[4])
            if (not isinstance(queries, list) or not 2 <= len(queries) <= _MAX_ROWS
                    or not isinstance(items, list) or len(items) != len(queries)
                    or any(not isinstance(item, dict)
                           or item.get("query") != queries[i]
                           or item.get("position") != i
                           for i, item in enumerate(items))):
                return None
            return {
                "batch_id": row[0], "queries": queries, "search_type": row[3],
                "items": items, "created_at": row[5], "contract_version": row[1],
            }
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, OverflowError):
        return None
