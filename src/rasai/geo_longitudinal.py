"""#311: conservative read-only longitudinal GEO observation inventory.

This is deliberately NOT a CONS-* report integration or an AI-visibility
trend metric. It compares persisted v5 observation provenance only, never
executes Search API, SERP, AI, collectors, RPR or a report materializer.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from rasai.geo_observation import _canonical_url, _canonical_url_v7, _host
from rasai.geo_temporal_provenance import _last_temporally_verified, _UNVERIFIABLE

_CONTRACTS = frozenset({
    "RASAI-GEO-OBSERVATION-5", "RASAI-GEO-OBSERVATION-6",
    "RASAI-GEO-OBSERVATION-7", "RASAI-GEO-OBSERVATION-8",
})
_SCOPE_KEYS = ("engine", "country", "region", "language", "device")
_MAX_AUD_DB_HASH_BYTES = 256 * 1024 * 1024
_MAX_V8_SOURCE_URL_ROWS = 500
_MAX_V8_QUERY_JSON_BYTES = 16 * 1024
_MAX_V8_PROJECTION_JSON_BYTES = 4 * 1024 * 1024


def _unique_v8_projection_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Do not use last-key-wins for a physically attested GEO v8 snapshot."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate GEO v8 projection JSON key")
        result[key] = value
    return result


def _aware(raw: object) -> datetime | None:
    try:
        if not isinstance(raw, str) or not raw.strip():
            return None
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (ValueError, OverflowError, TypeError):
        return None



def _v8_source_counts_match(
    con: sqlite3.Connection, run_id: str, serp_id: str,
    projection: dict[str, Any], audit_id: str,
) -> bool:
    """Verify v8 rate denominators against the physically persisted URL sets.

    Historical v5-v7 are not reinterpreted with current v8 URL normalization.
    A count in a signed-looking snapshot is not proof that the physical
    Search/SERP rows still support that number.
    """
    # A valid v8 projection must not require an unbounded, attacker-sized
    # multi-table read. Reject an oversized physical population before
    # materializing URL sets, even if its JSON counters are internally valid.
    px_rows = con.execute(
        "SELECT url FROM perplexity_search_sources WHERE run_id=? LIMIT ?",
        (run_id, _MAX_V8_SOURCE_URL_ROWS + 1),
    ).fetchall()
    serp_rows = con.execute(
        "SELECT url FROM serp_results WHERE observation_id=? LIMIT ?",
        (serp_id, _MAX_V8_SOURCE_URL_ROWS + 1),
    ).fetchall()
    if (len(px_rows) > _MAX_V8_SOURCE_URL_ROWS
            or len(serp_rows) > _MAX_V8_SOURCE_URL_ROWS):
        return False
    px_normalized = [_canonical_url(row[0]) for row in px_rows]
    serp_normalized = [_canonical_url(row[0]) for row in serp_rows]
    # v8 physical evidence must support the ENTIRE reported sample. Silently
    # dropping malformed HTTP(S) identities creates fictitious denominators,
    # even when a projection is re-saved with internally matching counts.
    if "" in px_normalized or "" in serp_normalized:
        return False
    px = set(px_normalized)
    serp = set(serp_normalized)
    if not px or not serp:
        return False
    # A frozen v8 target label is not its own provenance. Confirm the
    # displayed target was the sole input URL of this AUD and that the
    # claimed exact/alternative/absent state is present in the physical
    # Search source rows, not just in self-consistent overlap counters.
    target = projection.get("target_observation")
    if not isinstance(target, dict):
        return False
    targets = con.execute(
        "SELECT input_url FROM audit_targets WHERE audit_id=? LIMIT 2",
        (audit_id,),
    ).fetchall()
    target_url = _canonical_url(target.get("target_url"))
    if (len(targets) != 1 or not target_url
            or _canonical_url(targets[0][0]) != target_url):
        return False
    if target_url in px:
        observed_state = "EXACT_URL_OBSERVED"
    elif any(_host(url) == _host(target_url) for url in px):
        observed_state = "DOMAIN_ALTERNATIVE_OBSERVED"
    else:
        observed_state = "TARGET_NOT_IN_RETURNED_SOURCES"
    if target.get("status") != observed_state:
        return False
    overlap = projection.get("descriptive_overlap")
    if not isinstance(overlap, dict) or overlap.get("status") != "DESCRIPTIVE_ONLY":
        return False
    common = len(px & serp)
    union = len(px | serp)
    expected_ints = {
        "serp_denominator": len(serp),
        "perplexity_denominator": len(px),
        "common_urls": common,
        "serp_only_count": len(serp - px),
        "perplexity_only_count": len(px - serp),
    }
    expected_rates = {
        "serp_overlap_rate": round(common / len(serp), 4),
        "perplexity_overlap_rate": round(common / len(px), 4),
        "jaccard_url_rate": round(common / union, 4),
    }
    return (
        type(projection.get("source_count")) is int
        and projection["source_count"] == len(px_rows)
        and all(
            type(overlap.get(key)) is int and overlap[key] == value
            for key, value in expected_ints.items()
        )
        and all(
            type(overlap.get(key)) in (int, float)
            and 0 <= overlap[key] <= 1
            and overlap[key] == value
            for key, value in expected_rates.items()
        )
        and type(projection.get("serp_url_count")) is int
        and projection["serp_url_count"] == len(serp)
        and type(projection.get("perplexity_url_count")) is int
        and projection["perplexity_url_count"] == len(px)
        and type(projection.get("url_overlap_count")) is int
        and projection["url_overlap_count"] == common
    )


def _source_provenance(
    root: Path, audit_id: str, stored: dict[str, Any], projection: dict[str, Any],
) -> bool:
    """Verify that frozen snapshot IDs refer to observed source rows of this AUD.

    This validates logical source linkage, not the authenticity of third-party
    rankings, raw HTTP responses, or the completeness of the original package.
    """
    run_id = projection.get("perplexity_run_id")
    serp_id = projection.get("serp_observation_id")
    if (
        not isinstance(run_id, str) or not run_id
        or not isinstance(serp_id, str) or not serp_id
        or stored.get("perplexity_run_id") != run_id
        or stored.get("serp_observation_id") != serp_id
        or not re.fullmatch(r"[a-fA-F0-9]{64}", str(stored.get("input_sha256") or ""))
    ):
        return False
    try:
        db = root / "audit.db"
        if any(Path(str(db) + suffix).exists()
               for suffix in ("-wal", "-shm", "-journal")):
            return False
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1,
        )) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            runs = con.execute(
                "SELECT query_json, search_type, status, started_at "
                "FROM perplexity_search_runs WHERE run_id=? AND audit_id=? LIMIT 2",
                (run_id, audit_id),
            ).fetchall()
            serps = con.execute(
                "SELECT query, collected_at, data_mode, observation_status, "
                "engine, country, region, language, device "
                "FROM serp_observations WHERE observation_id=? AND audit_id=? LIMIT 2",
                (serp_id, audit_id),
            ).fetchall()
            # Never choose a convenient first row when a corrupted/legacy
            # source table contains conflicting identities. One GEO snapshot
            # must map to exactly one persisted Search and SERP observation.
            if len(runs) != 1 or len(serps) != 1:
                return False
            # v8 URL sets are read by run_id/observation_id alone. Refuse
            # cross-AUD collisions before joining these physical source rows.
            # v5-v7 are immutable historical methods with a different
            # attribution contract: do not retroactively reinterpret them.
            if stored.get("contract_version") == "RASAI-GEO-OBSERVATION-8" and (
                con.execute(
                    "SELECT COUNT(*) FROM perplexity_search_runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()[0] != 1 or con.execute(
                    "SELECT COUNT(*) FROM serp_observations WHERE observation_id=?",
                    (serp_id,),
                ).fetchone()[0] != 1
            ):
                return False
            run, serp = runs[0], serps[0]
            comparison = projection.get("comparability")
            if not isinstance(comparison, dict):
                return False
            px = comparison.get("perplexity_context")
            sc = comparison.get("serp_context")
            if not isinstance(px, dict) or not isinstance(sc, dict):
                return False
            raw_query_json = run["query_json"]
            if stored.get("contract_version") == "RASAI-GEO-OBSERVATION-8" and (
                not isinstance(raw_query_json, str)
                or len(raw_query_json.encode("utf-8")) > _MAX_V8_QUERY_JSON_BYTES
            ):
                return False
            queries = json.loads(str(raw_query_json))
            if not isinstance(queries, list) or queries != projection.get("queries"):
                return False
            if (
                run["status"] != "SUCCESS"
                or str(run["search_type"]).lower() != str(projection.get("search_type")).lower()
                or str(run["search_type"]).lower() != str(px.get("search_type")).lower()
                or _aware(run["started_at"]) != _aware(px.get("started_at"))
                or serp["data_mode"] != "OBSERVED_API"
                or serp["observation_status"] != "OBSERVED"
                or str(serp["query"]).strip().casefold() != str(queries[0]).strip().casefold()
                or _aware(serp["collected_at"]) != _aware(sc.get("collected_at"))
            ):
                return False
            if not all(
                str(serp[key] or "").strip().casefold()
                == str(sc.get(key) or "").strip().casefold()
                for key in _SCOPE_KEYS
            ):
                return False
            if stored.get("contract_version") == "RASAI-GEO-OBSERVATION-8":
                return _v8_source_counts_match(con, run_id, serp_id, projection, audit_id)
            return True
    except (sqlite3.Error, ValueError, TypeError, OSError, IndexError):
        return False


def _one_unsealed(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a complete AUD's latest immutable GEO record; fail closed."""
    root = Path(root)
    if not root.name.startswith("AUD-") or root.is_symlink():
        return None, "INVALID_AUD_DIRECTORY"
    db = root / "audit.db"
    if not db.is_file() or db.is_symlink():
        return None, "AUD_DATABASE_MISSING"
    # A live sidecar means the bare audit.db cannot represent one sealed
    # source snapshot. Do not open it or derive GEO source trends from it.
    if any(Path(str(db) + suffix).exists()
           for suffix in ("-wal", "-shm", "-journal")):
        return None, "AUD_SQLITE_SNAPSHOT_UNVERIFIED"
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=1)) as con:
            con.execute("PRAGMA query_only=ON")
            con.row_factory = sqlite3.Row
            # Diagnostics are mutually exclusive and read-only. The previous
            # single "AUD_NOT_LOGICALLY_COMPLETE" bucket conflated lifecycle,
            # foreign identity, empty metadata and duplicates, while the
            # generic schema error also concealed absent historical GEO tables.
            audit_columns = {
                str(row[1]) for row in con.execute("PRAGMA table_info(audits)")
            }
            if not audit_columns:
                return None, "AUD_METADATA_TABLE_MISSING"
            if not {"audit_id", "status", "completion_status"}.issubset(audit_columns):
                return None, "AUD_METADATA_SCHEMA_UNSUPPORTED"
            metadata = con.execute(
                "SELECT audit_id, status, completion_status FROM audits LIMIT 2"
            ).fetchall()
            if not metadata:
                return None, "AUD_METADATA_ROW_MISSING"
            if len(metadata) > 1:
                return None, "AUD_MULTIPLE_METADATA_ROWS"
            if metadata[0]["audit_id"] != root.name:
                return None, "AUD_IDENTITY_MISMATCH"
            if str(metadata[0]["status"] or "").strip().upper() != "COMPLETED":
                return None, "AUD_LIFECYCLE_NOT_COMPLETED"
            if str(metadata[0]["completion_status"] or "").strip().upper() != "COMPLETE":
                return None, "AUD_COMPLETION_NOT_COMPLETE"
            geo_columns = {
                str(row[1])
                for row in con.execute("PRAGMA table_info(geo_observation_runs)")
            }
            if not geo_columns:
                return None, "GEO_SNAPSHOT_TABLE_MISSING"
            required_geo = {
                "audit_id", "analysis_id", "contract_version", "projection_json",
                "created_at", "perplexity_run_id", "serp_observation_id",
                "input_sha256",
            }
            if not required_geo.issubset(geo_columns):
                return None, "GEO_SNAPSHOT_SCHEMA_UNSUPPORTED"
            selected = (
                "analysis_id", "contract_version", "projection_json",
                "created_at", "perplexity_run_id", "serp_observation_id",
                "input_sha256",
            )
            latest = _last_temporally_verified(
                con, table="geo_observation_runs", audit_id=root.name,
                columns=selected, time_column="created_at",
            )
            if latest is _UNVERIFIABLE:
                return None, "GEO_SNAPSHOT_CHRONOLOGY_UNVERIFIABLE"
            if latest is None:
                return None, "GEO_SNAPSHOT_MISSING"
            stored = dict(zip(selected, latest))
            # #309/#311: a frozen snapshot is not CURRENT if a subsequent
            # Search API attempt failed (or ordering is ambiguous). This is
            # the same conservative policy as GEO CAT cross-references: never
            # promote earlier success merely because its report persisted.
            current_search = _last_temporally_verified(
                con, table="perplexity_search_runs", audit_id=root.name,
                columns=("run_id", "status"), time_column="started_at",
            )
    except (sqlite3.Error, OSError):
        return None, "AUD_SCHEMA_OR_READ_ERROR"
    if stored["contract_version"] not in _CONTRACTS:
        return None, "GEO_LEGACY_OR_UNSUPPORTED_VERSION"
    raw_projection = stored["projection_json"]
    if stored["contract_version"] == "RASAI-GEO-OBSERVATION-8" and (
        not isinstance(raw_projection, str)
        or len(raw_projection.encode("utf-8")) > _MAX_V8_PROJECTION_JSON_BYTES
    ):
        return None, "GEO_PROJECTION_INVALID"
    try:
        projection = (
            json.loads(
                raw_projection, object_pairs_hook=_unique_v8_projection_keys,
            )
            if stored["contract_version"] == "RASAI-GEO-OBSERVATION-8"
            else json.loads(raw_projection)
        )
    except (TypeError, ValueError):
        return None, "GEO_PROJECTION_INVALID"
    if not isinstance(projection, dict):
        return None, "GEO_PROJECTION_INVALID"
    if not _source_provenance(root, root.name, stored, projection):
        return None, "GEO_SOURCE_PROVENANCE_UNVERIFIED"
    if current_search is _UNVERIFIABLE:
        return None, "GEO_SEARCH_CHRONOLOGY_UNVERIFIABLE"
    if current_search is None:
        return None, "GEO_SEARCH_NOT_PERSISTED"
    if current_search[1] != "SUCCESS":
        return None, "GEO_LATEST_SEARCH_NOT_SUCCESSFUL"
    if current_search[0] != stored["perplexity_run_id"]:
        return None, "GEO_SNAPSHOT_NOT_FROM_LATEST_SEARCH"
    if (
        projection.get("contract_version") != stored["contract_version"]
        or projection.get("audit_id") != root.name
        or projection.get("search_status") != "SUCCESS"
    ):
        return None, "GEO_PROJECTION_UNSUPPORTED_OR_FAILED"
    queries = projection.get("queries")
    target = projection.get("target_observation")
    comparability = projection.get("comparability")
    if (
        not isinstance(queries, list)
        or len(queries) != 1
        or not isinstance(queries[0], str)
        or not queries[0].strip()
        or not isinstance(target, dict)
        or not isinstance(comparability, dict)
        or not isinstance(target.get("query"), str)
        or target["query"].strip().casefold() != queries[0].strip().casefold()
    ):
        return None, "GEO_QUERY_ATTRIBUTION_UNPROVEN"
    uri = target.get("target_url")
    # Version-specific normalization must not reinterpret an immutable
    # historical v5/v6/v7 cohort under the stricter v8 URL identity.
    identity = (
        _canonical_url if stored["contract_version"] == "RASAI-GEO-OBSERVATION-8"
        else _canonical_url_v7
    )
    exact = identity(uri) if isinstance(uri, str) else ""
    if (
        not exact
        or target.get("status") not in {
            "EXACT_URL_OBSERVED", "DOMAIN_ALTERNATIVE_OBSERVED",
            "TARGET_NOT_IN_RETURNED_SOURCES",
        }
        or target.get("evidence_run_id") != projection.get("perplexity_run_id")
    ):
        return None, "TARGET_EVIDENCE_NOT_ELIGIBLE"
    px = comparability.get("perplexity_context")
    serp = comparability.get("serp_context")
    if not isinstance(px, dict) or not isinstance(serp, dict):
        return None, "SOURCE_SCOPE_NOT_PROVEN"
    instant = _aware(px.get("started_at"))
    serp_instant = _aware(serp.get("collected_at"))
    if instant is None or serp_instant is None:
        return None, "SOURCE_TIME_NOT_PROVEN"
    if abs((instant - serp_instant).total_seconds()) > 86400:
        return None, "SOURCE_TIME_WINDOW_NOT_ELIGIBLE"
    scope = {}
    for key in _SCOPE_KEYS:
        raw = serp.get(key)
        if not isinstance(raw, str) or not raw.strip():
            return None, "SERP_SCOPE_INCOMPLETE"
        scope[key] = raw.strip().casefold()
    kind = px.get("search_type")
    if not isinstance(kind, str) or kind.lower() not in {"web", "fast"}:
        return None, "EXTERNAL_SEARCH_MODE_UNPROVEN"
    overlap = projection.get("descriptive_overlap")
    if not isinstance(overlap, dict) or overlap.get("status") != "DESCRIPTIVE_ONLY":
        return None, "URL_DENOMINATOR_OR_COMPARABILITY_UNPROVEN"
    for key in ("serp_denominator", "perplexity_denominator", "common_urls"):
        value = overlap.get(key)
        if type(value) is not int or value < 0:
            return None, "URL_DENOMINATOR_INVALID"
    if (
        overlap["serp_denominator"] == 0
        or overlap["perplexity_denominator"] == 0
        or overlap["common_urls"] > min(
            overlap["serp_denominator"], overlap["perplexity_denominator"]
        )
    ):
        return None, "URL_DENOMINATOR_INVALID"
    return {
        "audit_id": root.name,
        "observation_id": stored["analysis_id"],
        "method_version": stored["contract_version"],
        "observed_at": instant.isoformat(),
        "target_url": exact,
        "query": queries[0].strip(),
        "target_status": target["status"],
        "serp_scope": scope,
        "external_search_mode": kind.lower(),
        "url_intersection_observed": overlap["common_urls"],
        "serp_urls_observed": overlap["serp_denominator"],
        "external_urls_observed": overlap["perplexity_denominator"],
    }, None


def _physical_source_sha256(db: Path) -> tuple[str, int]:
    """Bounded fingerprint of bare SQLite bytes; not an AUD authenticity proof."""
    if db.is_symlink() or not db.is_file() or any(
        Path(str(db) + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError("unsealed GEO longitudinal source")
    length = db.stat().st_size
    if length > _MAX_AUD_DB_HASH_BYTES:
        raise ValueError("GEO longitudinal source exceeds byte budget")
    digest = sha256()
    read = 0
    with db.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            read += len(block)
            if read > _MAX_AUD_DB_HASH_BYTES:
                raise ValueError("GEO longitudinal source changed while hashing")
            digest.update(block)
    if read != length or db.stat().st_size != length or any(
        Path(str(db) + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise ValueError("GEO longitudinal source changed while hashing")
    return digest.hexdigest(), read


def _one(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Require physically unchanged SQLite across independent GEO reads."""
    root = Path(root)
    # Retain the pre-existing exclusion taxonomy for an invalid/missing AUD.
    if not root.name.startswith("AUD-") or root.is_symlink():
        return None, "INVALID_AUD_DIRECTORY"
    db = root / "audit.db"
    if db.is_symlink() or not db.is_file():
        return None, "AUD_DATABASE_MISSING"
    if any(Path(str(db) + ext).exists()
           for ext in ("-wal", "-shm", "-journal")):
        return None, "AUD_SQLITE_SNAPSHOT_UNVERIFIED"
    try:
        before = _physical_source_sha256(db)
    except (ValueError, OSError):
        return None, "AUD_SOURCE_BYTES_UNVERIFIABLE"
    row, reason = _one_unsealed(root)
    try:
        after = _physical_source_sha256(db)
    except (ValueError, OSError):
        return None, "AUD_SOURCE_CHANGED_DURING_READ"
    if before != after:
        return None, "AUD_SOURCE_CHANGED_DURING_READ"
    return row, reason


def build_geo_longitudinal_preview(audit_dirs: Sequence[Path]) -> dict[str, Any]:
    """Group matched observations; never manufacture rankings or time trends.

    Each AUD supplies at most one verified v5/v6/v7 snapshot; no query or locale is guessed.
    Results include the original source-observation timestamps and counts,
    but comparisons never imply provider market/device or intent equivalence.
    """
    if not 2 <= len(audit_dirs) <= 100:
        raise ValueError("expected 2..100 explicit AUD directories")
    if len({str(Path(root).resolve()) for root in audit_dirs}) != len(audit_dirs):
        raise ValueError("duplicate AUD directory")
    rejected: list[dict[str, str]] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for path in audit_dirs:
        row, reason = _one(Path(path))
        if row is None:
            rejected.append({"audit_id": Path(path).name, "reason": str(reason)})
            continue
        key = json.dumps(
            {
                "target_url": row["target_url"],
                "method_version": row["method_version"],
                "query": row["query"].casefold(),
                "serp_scope": row["serp_scope"],
                "external_search_mode": row["external_search_mode"],
            },
            sort_keys=True,
        )
        groups.setdefault(key, []).append(row)
    timelines = []
    for key in sorted(groups):
        rows = sorted(groups[key], key=lambda x: (x["observed_at"], x["audit_id"]))
        meta = json.loads(key)
        timelines.append({
            "target_url": meta["target_url"],
            "method_version": meta["method_version"],
            "query": meta["query"],
            "serp_scope": meta["serp_scope"],
            "external_search_mode": meta["external_search_mode"],
            "status": "OBSERVATIONAL_SEQUENCE_ONLY" if len(rows) >= 2 else "SINGLE_OBSERVATION",
            "observations": rows,
            "trend_rate": None,
            "trend_conclusion": "N/D",
            "limitation": (
                "Sample composition, Perplexity market/locale/device and "
                "intent equivalence are not verified across dates. Raw "
                "observations do not imply ranking, generative citations, "
                "market share, improvement or deterioration."
            ),
        })
    exclusion_reasons: dict[str, int] = {}
    for item in rejected:
        reason = item["reason"]
        exclusion_reasons[reason] = exclusion_reasons.get(reason, 0) + 1
    multiple = [
        group for group in timelines if len(group["observations"]) >= 2
    ]
    coverage = {
        "distinct_observed_scope_cohorts": len(timelines),
        "single_observation_cohorts": len(timelines) - len(multiple),
        "multi_observation_cohorts_unverified_trend": len(multiple),
        "eligible_auds_in_multi_observation_cohorts": sum(
            len(group["observations"]) for group in multiple
        ),
        "excluded_auds_by_reason": dict(sorted(exclusion_reasons.items())),
        "market_device_intent_sampling_equivalence_proven": False,
        "calibrated_geo_trend_cohorts": 0,
        "reason_counts_are_eligibility_only": True,
    }
    return {
        "contract_version": "RASAI-GEO-LONGITUDINAL-ADVISORY-001",
        "observation_coverage": coverage,
        "audits_requested": len(audit_dirs),
        "audits_eligible": sum(len(items) for items in groups.values()),
        "excluded": rejected,
        "timelines": timelines,
        "provider_requests": 0,
        "audit_writes": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only GEO observational inventory; no AI/Search API requests."
    )
    parser.add_argument(
        "--format", choices=("json", "html"), default="json",
        help="Standalone read-only output; HTML does not mutate CONS or AUDs.",
    )
    parser.add_argument("audit_dirs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    result = build_geo_longitudinal_preview(args.audit_dirs)
    if args.format == "html":
        from rasai.geo_longitudinal_html import render_geo_longitudinal_html
        print(render_geo_longitudinal_html(result))
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
