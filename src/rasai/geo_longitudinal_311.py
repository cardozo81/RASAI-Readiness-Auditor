"""#311: conservative read-only longitudinal GEO observation inventory.

This is deliberately NOT a CONS-* report integration or an AI-visibility
trend metric. It compares persisted v5 observation provenance only, never
executes Search API, SERP, AI, collectors, RPR or a report materializer.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import sqlite3
from typing import Any, Sequence

from rasai.geo_observation import _canonical_url

_CONTRACTS = frozenset({
    "RASAI-GEO-OBSERVATION-5", "RASAI-GEO-OBSERVATION-6",
})
_SCOPE_KEYS = ("engine", "country", "region", "language", "device")


def _aware(raw: object) -> datetime | None:
    try:
        if not isinstance(raw, str) or not raw.strip():
            return None
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (ValueError, OverflowError, TypeError):
        return None



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
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1,
        )) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            run = con.execute(
                "SELECT query_json, search_type, status, started_at "
                "FROM perplexity_search_runs WHERE run_id=? AND audit_id=?",
                (run_id, audit_id),
            ).fetchone()
            serp = con.execute(
                "SELECT query, collected_at, data_mode, observation_status, "
                "engine, country, region, language, device "
                "FROM serp_observations WHERE observation_id=? AND audit_id=?",
                (serp_id, audit_id),
            ).fetchone()
            if run is None or serp is None:
                return False
            px = projection.get("comparability", {}).get("perplexity_context")
            sc = projection.get("comparability", {}).get("serp_context")
            if not isinstance(px, dict) or not isinstance(sc, dict):
                return False
            queries = json.loads(str(run["query_json"]))
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
            return all(
                str(serp[key] or "").strip().casefold()
                == str(sc.get(key) or "").strip().casefold()
                for key in _SCOPE_KEYS
            )
    except (sqlite3.Error, ValueError, TypeError, OSError, IndexError):
        return False


def _one(root: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a complete AUD's latest immutable v5 record; fail closed."""
    root = Path(root)
    if not root.name.startswith("AUD-") or root.is_symlink():
        return None, "INVALID_AUD_DIRECTORY"
    db = root / "audit.db"
    if not db.is_file() or db.is_symlink():
        return None, "AUD_DATABASE_MISSING"
    try:
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)) as con:
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
            rows = con.execute(
                "SELECT analysis_id, contract_version, projection_json, created_at, "
                "perplexity_run_id, serp_observation_id, input_sha256 "
                "FROM geo_observation_runs WHERE audit_id=? "
                "ORDER BY created_at DESC, analysis_id DESC LIMIT 1", (root.name,),
            ).fetchall()
            if len(rows) != 1:
                return None, "GEO_SNAPSHOT_MISSING"
            stored = dict(rows[0])
    except (sqlite3.Error, OSError):
        return None, "AUD_SCHEMA_OR_READ_ERROR"
    if stored["contract_version"] not in _CONTRACTS:
        return None, "GEO_LEGACY_OR_UNSUPPORTED_VERSION"
    try:
        projection = json.loads(stored["projection_json"])
    except (TypeError, ValueError):
        return None, "GEO_PROJECTION_INVALID"
    if not isinstance(projection, dict):
        return None, "GEO_PROJECTION_INVALID"
    if not _source_provenance(root, root.name, stored, projection):
        return None, "GEO_SOURCE_PROVENANCE_UNVERIFIED"
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
    exact = _canonical_url(uri) if isinstance(uri, str) else ""
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


def build_geo_longitudinal_preview(audit_dirs: Sequence[Path]) -> dict[str, Any]:
    """Group matched observations; never manufacture rankings or time trends.

    Each AUD supplies at most one v5 snapshot; no query or locale is guessed.
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
    return {
        "contract_version": "RASAI-GEO-LONGITUDINAL-ADVISORY-001",
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
    parser.add_argument("audit_dirs", nargs="+", type=Path)
    args = parser.parse_args(argv)
    result = build_geo_longitudinal_preview(args.audit_dirs)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
