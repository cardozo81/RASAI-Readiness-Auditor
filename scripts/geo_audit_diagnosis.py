"""Read-only structural GEO diagnosis for one physical AUD; no provider requests.

Run from the repository root on Windows after git pull --ff-only:
    .venv\\Scripts\\python.exe scripts\\geo_audit_diagnosis.py audits\\AUD-...
Query strings, result URLs, snippets, request headers and secrets are never printed.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3


_TABLES = frozenset({
    "audits", "perplexity_search_runs", "perplexity_search_sources",
    "serp_observations", "serp_results", "geo_observation_runs",
    "audit_fulfillment_contracts", "audit_fulfillment_work_items",
})


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    if table not in _TABLES:
        raise ValueError("Unrecognized table")
    return {str(row[1]) for row in con.execute("PRAGMA table_info(" + table + ")")}


def _rows(con: sqlite3.Connection, table: str, fields: tuple[str, ...],
          audit_id: str, limit: int = 100) -> list[dict]:
    columns = _columns(con, table)
    if "audit_id" not in columns:
        return []
    selected = ", ".join(
        col if col in columns else "NULL AS " + col for col in fields
    )
    return [
        dict(row) for row in con.execute(
            "SELECT " + selected + " FROM " + table
            + " WHERE audit_id=? LIMIT ?", (audit_id, limit),
        )
    ]


def _query_fingerprint(text: object) -> dict | None:
    if not isinstance(text, str):
        return None
    raw = text.encode("utf-8")
    return {"sha256_utf8": sha256(raw).hexdigest(), "utf8_bytes": len(raw)}


def diagnose(audit_dir: Path) -> dict:
    root = Path(audit_dir)
    if not root.is_dir() or root.is_symlink() or not root.name.startswith("AUD-"):
        raise ValueError("Expected a physical AUD directory")
    db = root / "audit.db"
    if not db.is_file() or db.is_symlink():
        raise ValueError("Expected an existing regular audit.db")
    before = _hash(db)
    result = {
        "audit_id": root.name, "source_db_sha256": before,
        "audit_writes": 0, "provider_requests": 0,
        "query_and_url_payloads": "REDACTED",
    }
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        audit = _rows(con, "audits", ("audit_id", "status", "completion_status"),
                      root.name, limit=2)
        result["audit"] = audit
        runs = _rows(
            con, "perplexity_search_runs",
            ("run_id", "query_json", "search_type", "status", "started_at", "http_status"),
            root.name, limit=50,
        )
        seen_queries: set[str] = set()
        result["perplexity_runs"] = []
        for run in runs:
            try:
                queries = json.loads(run["query_json"])
                if not isinstance(queries, list) or not all(
                    isinstance(item, str) for item in queries
                ):
                    queries = []
            except (ValueError, TypeError):
                queries = []
            seen_queries.update(queries)
            source_count = None
            if "run_id" in _columns(con, "perplexity_search_sources"):
                source_count = con.execute(
                    "SELECT count(*) FROM perplexity_search_sources WHERE run_id=?",
                    (run["run_id"],),
                ).fetchone()[0]
            result["perplexity_runs"].append({
                "run_id": run["run_id"], "status": run["status"],
                "search_type": run["search_type"],
                "started_at": run["started_at"], "http_status": run["http_status"],
                "query_fingerprints": [_query_fingerprint(q) for q in queries],
                "sources": source_count,
            })
        serp = _rows(
            con, "serp_observations",
            ("observation_id", "query", "data_mode", "observation_status",
             "collected_at", "engine", "country", "region", "language", "device"),
            root.name,
        )
        result["serp_observations"] = []
        for row in serp:
            count = None
            if "observation_id" in _columns(con, "serp_results"):
                count = con.execute(
                    "SELECT count(*) FROM serp_results WHERE observation_id=?",
                    (row["observation_id"],),
                ).fetchone()[0]
            query = row.pop("query")
            row["query_fingerprint"] = _query_fingerprint(query)
            row["exact_query_in_external_run"] = query in seen_queries
            row["casefold_query_in_external_run"] = (
                isinstance(query, str)
                and any(query.strip().casefold() == q.strip().casefold()
                        for q in seen_queries)
            )
            row["results"] = count
            result["serp_observations"].append(row)
        result["geo_snapshots"] = []
        for snapshot in _rows(
            con, "geo_observation_runs",
            ("analysis_id", "perplexity_run_id", "serp_observation_id",
             "contract_version", "created_at", "projection_json"), root.name,
        ):
            try:
                p = json.loads(snapshot.pop("projection_json"))
                if not isinstance(p, dict):
                    p = {}
            except (TypeError, ValueError):
                p = {}
            rates = p.get("descriptive_overlap")
            target = p.get("target_observation")
            snapshot["projection_run_id"] = p.get("perplexity_run_id")
            snapshot["overlap_status"] = (
                rates.get("status") if isinstance(rates, dict) else None
            )
            snapshot["overlap_reason"] = (
                rates.get("reason") if isinstance(rates, dict) else None
            )
            snapshot["target_status"] = (
                target.get("status") if isinstance(target, dict) else None
            )
            result["geo_snapshots"].append(snapshot)
        result["fulfillment"] = _rows(
            con, "audit_fulfillment_contracts",
            ("processing_status", "required_items", "successful_items",
             "pending_items", "blocked_items"), root.name, limit=2,
        )
        result["work_items"] = _rows(
            con, "audit_fulfillment_work_items",
            ("component", "status", "required", "temporal_mode"), root.name,
        )
    result["source_db_unchanged"] = before == _hash(db)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_dir", type=Path)
    args = parser.parse_args()
    try:
        outcome = diagnose(args.audit_dir)
    except (OSError, sqlite3.Error, ValueError) as error:
        # An error message can contain local filesystem paths, never include
        # arbitrary SQLite details in user-shared diagnostics.
        outcome = {"status": "DIAGNOSIS_UNAVAILABLE",
                   "error_class": type(error).__name__,
                   "audit_writes": 0, "provider_requests": 0}
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if outcome.get("source_db_unchanged") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
