"""#304: offline per-query GEO source-attribution ledger.

Consumes persisted Search API/SERP evidence only. No provider requests, score
changes, GEO snapshot backfills, or extrapolated query/intent attribution.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from rasai.geo_observation import _canonical_url, _temporal_gap_seconds
from rasai.geo_temporal_provenance import _last_temporally_verified, _UNVERIFIABLE

_MAX_QUERY_COUNT = 10
_MAX_SOURCES = 500
_MAX_SERP_ROWS = 200
_WINDOW = 86400
_SCOPE = ("engine", "country", "region", "language", "device")


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def _query_key(value: object) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _row(query: str, classification: str, reason: str) -> dict[str, Any]:
    return {
        "query": query,
        "declared_query_class": classification,
        "query_class_source": (
            "EXPLICIT_OPERATOR_DECLARATION" if classification != "UNCLASSIFIED"
            else "NOT_AVAILABLE"
        ),
        "status": "NOT_COMPARABLE", "reason": reason,
        "serp_observation_id": None,
        "serp_scope": None, "observation_gap_seconds": None,
        "perplexity_distinct_urls": None, "serp_distinct_urls": None,
        "common_urls": None, "serp_only_urls": None,
        "perplexity_only_urls": None,
        "serp_overlap_rate": None, "perplexity_overlap_rate": None,
        "jaccard_url_rate": None,
        "external_market_language_device_equivalence_proven": False,
        "intent_equivalence_proven": False,
        "ranking_or_generative_citation_proven": False,
    }


def inspect_geo_per_query(
    audit_dir: Path, *, declared_branded_queries: Sequence[str] = (),
) -> dict[str, Any]:
    """Return descriptive URL-set overlaps only with physical per-query linkage.

    The Search API collector presently does not persist a query on every
    source in multi-query runs; that case must abstain instead of assigning
    returned URLs to all requested queries.
    """
    root = Path(audit_dir)
    if (not root.name.startswith("AUD-") or root.is_symlink()
            or not root.is_dir()):
        raise ValueError("canonical physical AUD directory is required")
    db = root / "audit.db"
    if db.is_symlink() or not db.is_file() or any(
        (root / ("audit.db" + suffix)).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError("read-only AUD database without sidecars required")
    if isinstance(declared_branded_queries, (str, bytes)):
        raise ValueError("operator query classes must be a sequence")
    brands = [_query_key(s) for s in declared_branded_queries]
    if (len(brands) > _MAX_QUERY_COUNT or any(not x for x in brands)
            or len(brands) != len(set(brands))):
        raise ValueError("invalid explicit branded-query declaration")

    out: dict[str, Any] = {
        "contract_version": "RASAI-GEO-PER-QUERY-304-ADVISORY-001",
        "audit_id": root.name, "status": "NOT_COMPARABLE",
        "reason": None, "queries": [],
        "per_query_attribution_status": "NOT_VERIFIED",
        "external_market_language_device_equivalence_proven": False,
        "intent_equivalence_proven": False,
        "query_classes_from_operator_only": True,
        "provider_requests": 0, "audit_writes": 0,
        "score_changed": False, "source_package_freshness_verified": False,
        "limitations": (
            "Comparação descritiva de conjuntos de URLs persistidas, não "
            "participação em respostas gerativas, rank, causalidade, "
            "representatividade ou mesma intenção/mercado/dispositivo "
            "entre SERP e Perplexity. Classificação branded é declaração "
            "do operador, não inferência do provedor."
        ),
    }
    def abstain(reason: str) -> dict[str, Any]:
        out["reason"] = reason
        return out
    try:
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1",
            uri=True, timeout=2,
        )) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            if not {"audit_id", "status", "completion_status"} <= _columns(con, "audits"):
                return abstain("AUD_METADATA_UNVERIFIABLE")
            metadata = con.execute(
                "SELECT audit_id,status,completion_status FROM audits LIMIT 2"
            ).fetchall()
            if (len(metadata) != 1 or metadata[0]["audit_id"] != root.name
                    or str(metadata[0]["status"]).upper() != "COMPLETED"
                    or str(metadata[0]["completion_status"]).upper() != "COMPLETE"):
                return abstain("AUD_NOT_COMPLETE_OR_FOREIGN")
            if not {"run_id", "audit_id", "query_json", "search_type",
                    "status", "started_at"} <= _columns(con, "perplexity_search_runs"):
                return abstain("EXTERNAL_SEARCH_SCHEMA_UNVERIFIABLE")
            required_sources = {"run_id", "url"}
            source_columns = _columns(con, "perplexity_search_sources")
            if not required_sources <= source_columns:
                return abstain("EXTERNAL_SOURCES_SCHEMA_UNVERIFIABLE")
            if not {"observation_id", "audit_id", "query", "collected_at",
                    "data_mode", "observation_status", *_SCOPE} <= _columns(
                        con, "serp_observations"
                    ):
                return abstain("SERP_SCOPE_SCHEMA_UNVERIFIABLE")
            if not {"observation_id", "url"} <= _columns(con, "serp_results"):
                return abstain("SERP_RESULTS_SCHEMA_UNVERIFIABLE")
            selected = ("run_id", "query_json", "search_type", "status", "started_at")
            latest = _last_temporally_verified(
                con, table="perplexity_search_runs", audit_id=root.name,
                columns=selected, time_column="started_at",
            )
            if latest is _UNVERIFIABLE:
                return abstain("EXTERNAL_SEARCH_CHRONOLOGY_UNVERIFIABLE")
            if latest is None:
                return abstain("EXTERNAL_SEARCH_NOT_FOUND")
            run = dict(zip(selected, latest))
            if (run["status"] != "SUCCESS"
                    or str(run["search_type"]).lower() not in {"web", "fast"}
                    or _utc(run["started_at"]) is None):
                return abstain("EXTERNAL_SEARCH_NOT_SUCCESSFUL")
            # A run_id must be unique across all AUDs, not just within one.
            if con.execute(
                "SELECT count(*) FROM perplexity_search_runs WHERE run_id=?",
                (run["run_id"],),
            ).fetchone()[0] != 1:
                return abstain("EXTERNAL_RUN_ID_AMBIGUOUS")
            try:
                declared = json.loads(run["query_json"])
            except (ValueError, TypeError):
                return abstain("EXTERNAL_QUERY_JSON_INVALID")
            if (not isinstance(declared, list)
                    or not 1 <= len(declared) <= _MAX_QUERY_COUNT
                    or any(not isinstance(q, str) or not q.strip()
                           or len(q) > 300 for q in declared)
                    or len({_query_key(q) for q in declared}) != len(declared)):
                return abstain("EXTERNAL_QUERY_SET_AMBIGUOUS")
            if not set(brands) <= {_query_key(q) for q in declared}:
                raise ValueError("declared branded-query not in persisted run")
            sources = con.execute(
                "SELECT url, " + (
                    "query" if "query" in source_columns else "NULL AS query"
                ) + " FROM perplexity_search_sources WHERE run_id=? LIMIT ?",
                (run["run_id"], _MAX_SOURCES + 1),
            ).fetchall()
            if len(sources) > _MAX_SOURCES:
                return abstain("EXTERNAL_SOURCE_VOLUME_EXCEEDED")
            source_by_query: dict[str, set[str]] = {
                _query_key(q): set() for q in declared
            }
            # Missing per-source query is safe ONLY for a single-query run.
            attributable = len(declared) == 1 or (
                "query" in source_columns
                and all(_query_key(item["query"]) in source_by_query for item in sources)
            )
            if attributable:
                for item in sources:
                    key = _query_key(declared[0]) if len(declared) == 1 else _query_key(item["query"])
                    canonical = _canonical_url(item["url"])
                    if canonical:
                        source_by_query[key].add(canonical)
            serp = con.execute(
                "SELECT observation_id,query,collected_at,engine,country,region,"
                "language,device FROM serp_observations "
                "WHERE audit_id=? AND data_mode='OBSERVED_API' "
                "AND observation_status='OBSERVED' LIMIT ?",
                (root.name, _MAX_SERP_ROWS + 1),
            ).fetchall()
            if len(serp) > _MAX_SERP_ROWS:
                return abstain("SERP_OBSERVATION_VOLUME_EXCEEDED")
            for query in declared:
                qkey = _query_key(query)
                class_name = "BRANDED_DECLARED" if qkey in brands else "UNCLASSIFIED"
                row = _row(query, class_name, "PER_QUERY_SOURCE_ATTRIBUTION_UNPROVEN")
                if not attributable:
                    out["queries"].append(row)
                    continue
                if not source_by_query[qkey]:
                    row["reason"] = "NO_VALID_EXTERNAL_URL_DENOMINATOR"
                    out["queries"].append(row)
                    continue
                candidates: list[tuple[float, datetime, sqlite3.Row]] = []
                for obs in serp:
                    if _query_key(obs["query"]) != qkey:
                        continue
                    gap = _temporal_gap_seconds(run["started_at"], obs["collected_at"])
                    when = _utc(obs["collected_at"])
                    if gap is None or gap > _WINDOW or when is None:
                        continue
                    if not all(isinstance(obs[s], str) and obs[s].strip() for s in _SCOPE):
                        continue
                    candidates.append((gap, when, obs))
                if not candidates:
                    row["reason"] = "NO_COMPARABLE_OBSERVED_SERP_SCOPE_WITHIN_24H"
                    out["queries"].append(row)
                    continue
                candidates.sort(key=lambda x: (x[0], -x[1].timestamp(), str(x[2]["observation_id"])))
                # Equidistant and equal-time observations cannot be
                # resolved by an arbitrary opaque observation ID.
                if (len(candidates) > 1 and candidates[0][0] == candidates[1][0]
                        and candidates[0][1] == candidates[1][1]):
                    row["reason"] = "AMBIGUOUS_EQUIDISTANT_SERP_OBSERVATIONS"
                    out["queries"].append(row)
                    continue
                gap, _, match = candidates[0]
                sid = match["observation_id"]
                if con.execute(
                    "SELECT count(*) FROM serp_observations WHERE observation_id=?",
                    (sid,),
                ).fetchone()[0] != 1:
                    row["reason"] = "SERP_OBSERVATION_ID_AMBIGUOUS"
                    out["queries"].append(row)
                    continue
                rows = con.execute(
                    "SELECT url FROM serp_results WHERE observation_id=? LIMIT ?",
                    (sid, _MAX_SOURCES + 1),
                ).fetchall()
                if len(rows) > _MAX_SOURCES:
                    row["reason"] = "SERP_RESULTS_VOLUME_EXCEEDED"
                    out["queries"].append(row)
                    continue
                serp_urls = {_canonical_url(z[0]) for z in rows}
                serp_urls.discard("")
                if not serp_urls:
                    row["reason"] = "NO_VALID_SERP_URL_DENOMINATOR"
                    out["queries"].append(row)
                    continue
                px_urls = source_by_query[qkey]
                common = len(px_urls & serp_urls)
                union = len(px_urls | serp_urls)
                row.update(
                    status="DESCRIPTIVE_ONLY",
                    reason=None,
                    serp_observation_id=sid,
                    serp_scope={s: str(match[s]).strip() for s in _SCOPE},
                    observation_gap_seconds=gap,
                    perplexity_distinct_urls=len(px_urls),
                    serp_distinct_urls=len(serp_urls),
                    common_urls=common,
                    serp_only_urls=len(serp_urls - px_urls),
                    perplexity_only_urls=len(px_urls - serp_urls),
                    serp_overlap_rate=round(common / len(serp_urls), 4),
                    perplexity_overlap_rate=round(common / len(px_urls), 4),
                    jaccard_url_rate=round(common / union, 4),
                )
                out["queries"].append(row)
            out["per_query_attribution_status"] = (
                "PHYSICALLY_ATTRIBUTABLE" if attributable else
                "MULTI_QUERY_SOURCE_MAPPING_MISSING"
            )
            out["status"] = "DESCRIPTIVE_ONLY" if any(
                row["status"] == "DESCRIPTIVE_ONLY" for row in out["queries"]
            ) else "NOT_COMPARABLE"
            if out["status"] == "NOT_COMPARABLE":
                out["reason"] = "NO_QUERY_WITH_VERIFIED_SOURCE_DENOMINATORS"
            return out
    except (sqlite3.Error, OSError, ValueError, OverflowError) as exc:
        # The source may be an old/corrupt SQLite package. Never mutate it.
        if isinstance(exc, ValueError) and "declared branded-query" in str(exc):
            raise
        return abstain("SOURCE_SCHEMA_OR_READ_FAILURE")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline GEO SERP x external Search per-query inventory (#304)."
    )
    parser.add_argument("audit_dir", type=Path)
    parser.add_argument("--declared-branded-query", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        outcome = inspect_geo_per_query(
            args.audit_dir, declared_branded_queries=args.declared_branded_query,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
