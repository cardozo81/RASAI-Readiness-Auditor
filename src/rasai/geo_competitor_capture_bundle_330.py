"""#330: consented public competitor HTML -> provenance-bound sidecar, not AUD.

No raw HTML persisted, no score, provider AI, collector, or AUD mutations.
Only explicitly authorized, SERP-observed competitor URLs are admissible.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Sequence

from rasai.geo_competitor_fetch_330 import inspect_consented_public_html
from rasai.geo_observation import _canonical_url
from rasai.search_intelligence.content import PublicWebFetcher

_MAX_SOURCE_DB_BYTES = 256 * 1024 * 1024


def _physical_digest(source: Path) -> str:
    if source.stat().st_size > _MAX_SOURCE_DB_BYTES:
        raise ValueError("AUD source exceeds bounded verification size")
    hash_ = sha256()
    consumed = 0
    with source.open("rb") as handle:
        for segment in iter(lambda: handle.read(1024 * 1024), b""):
            consumed += len(segment)
            if consumed > _MAX_SOURCE_DB_BYTES:
                raise ValueError("AUD source grew beyond bounded verification size")
            hash_.update(segment)
    # A stat alone cannot attest a stable file: detect growth or truncation
    # during either SHA-256 pass, not only a mismatch between the two passes.
    if consumed != source.stat().st_size:
        raise ValueError("AUD source changed size during digest")
    return hash_.hexdigest()


def _assert_aud_still_sealed(source: Path, digest: str) -> None:
    """Fail closed on a changed source or newly appearing SQLite journals.

    A status-only NOT_CAPTURED outcome must never hide an AUD source race.
    Recheck also immediately before atomic sidecar publication or reuse.
    """
    if (
        source.is_symlink() or not source.is_file()
        or source.parent.is_symlink()
        or any(Path(str(source) + ending).exists()
               for ending in ("-wal", "-shm", "-journal"))
    ):
        raise ValueError("physical AUD source no longer sealed during capture")
    if _physical_digest(source) != digest:
        raise ValueError("physical AUD changed during capture")


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})")}


def _payload(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2,
                   allow_nan=False) + "\n"
    ).encode("utf-8")


def capture_competitor_sidecar(
    audit_dir: Path, observation_id: str, candidate_url: str, *,
    output_root: Path, consented_hostnames: Sequence[str],
    fetcher: PublicWebFetcher | None = None,
) -> dict[str, Any]:
    """Produce immutable offline-review evidence from authorized public HTML.

    The source AUD is read-only, and must already contain the matching
    SERP result and exact observation. An in-flight AUD change invalidates
    provenance, including when the fetch itself is otherwise successful.
    """
    audit_dir = Path(audit_dir)
    db = audit_dir / "audit.db"
    if (not audit_dir.name.startswith("AUD-") or not audit_dir.is_dir()
            or audit_dir.is_symlink() or not db.is_file() or db.is_symlink()
            or any(Path(str(db) + suffix).exists()
                   for suffix in ("-wal", "-shm", "-journal"))):
        raise ValueError("completed physical AUD with stable SQLite source required")
    candidate = _canonical_url(candidate_url)
    if not candidate or candidate != candidate_url:
        raise ValueError("exact, unambiguous candidate URL required")
    if (not isinstance(observation_id, str) or not observation_id.strip()
            or len(observation_id) > 128):
        raise ValueError("SERP observation ID required")
    destroot = Path(output_root)
    # Even if writable, output must not materialize in an AUD package.
    resolved_source = audit_dir.resolve()
    resolved_root = destroot.resolve()
    if resolved_root == resolved_source or resolved_source in resolved_root.parents:
        raise ValueError("companion evidence must be stored outside the AUD")
    # All AUD, CONS and RPR packages are immutable inputs, not destinations.
    # Restrict the caller-supplied output path across *other* packages too:
    # previously it was possible to save COBS files inside a different AUD.
    # Resolved ancestor checks also catch relative paths and symlink parents.
    if any(
        part.name.startswith(("AUD-", "CONS-", "RPR-"))
        for part in (resolved_root, *resolved_root.parents)
    ):
        raise ValueError(
            "companion evidence destination must be outside every AUD/CONS/RPR package"
        )
    if destroot.is_symlink() or (destroot.exists() and not destroot.is_dir()):
        raise ValueError("unsafe competitor evidence destination")
    if db.stat().st_size > _MAX_SOURCE_DB_BYTES:
        raise ValueError("AUD source too large for bounded verification")
    digest_before = _physical_digest(db)
    try:
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2,
        )) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            if not {"audit_id", "status", "completion_status"} <= _columns(con, "audits"):
                raise ValueError("AUD metadata schema not proven")
            rows = con.execute(
                "SELECT audit_id,status,completion_status FROM audits LIMIT 2"
            ).fetchall()
            if (len(rows) != 1 or rows[0]["audit_id"] != audit_dir.name
                    or str(rows[0]["status"]).upper() != "COMPLETED"
                    or str(rows[0]["completion_status"]).upper() != "COMPLETE"):
                raise ValueError("AUD identity or completion not proven")
            required = {"observation_id", "audit_id", "query",
                        "collected_at", "observation_status", "data_mode",
                        "engine", "country", "region", "language", "device"}
            if not required <= _columns(con, "serp_observations"):
                raise ValueError("SERP scope schema not proven")
            if not {"observation_id", "url"} <= _columns(con, "serp_results"):
                raise ValueError("SERP source URL schema not proven")
            obs = con.execute(
                "SELECT observation_id,audit_id,query,collected_at,"
                "observation_status,data_mode,engine,country,region,"
                "language,device FROM serp_observations "
                "WHERE observation_id=? LIMIT 2", (observation_id,),
            ).fetchall()
            if (len(obs) != 1 or obs[0]["audit_id"] != audit_dir.name
                    or obs[0]["data_mode"] != "OBSERVED_API"
                    or obs[0]["observation_status"] != "OBSERVED"):
                raise ValueError("unverified/foreign SERP observation")
            record = obs[0]
            if (not isinstance(record["query"], str) or not record["query"].strip()
                    or len(record["query"]) > 300
                    or any(not isinstance(record[key], str)
                           or not record[key].strip()
                           for key in ("collected_at", "engine", "country",
                                      "region", "language", "device"))):
                raise ValueError("SERP query and region context not proven")
            # A filled-in timestamp is not a physical UTC observation.
            # Date-only, offset-free, malformed or impossible clocks do not
            # supply provenance for a consented competitor capture.
            try:
                observed_at = datetime.fromisoformat(
                    record["collected_at"].replace("Z", "+00:00")
                )
                if observed_at.tzinfo is None:
                    raise ValueError("SERP observation clock has no timezone")
                normalized_collected_at = observed_at.astimezone(timezone.utc).isoformat()
            except (ValueError, OverflowError, TypeError):
                raise ValueError("SERP observation UTC clock not proven") from None
            urls = con.execute(
                "SELECT url FROM serp_results WHERE observation_id=? LIMIT 501",
                (observation_id,),
            ).fetchall()
            if len(urls) > 500 or not any(
                _canonical_url(row["url"]) == candidate for row in urls
            ):
                raise ValueError("candidate URL is not in persisted SERP evidence")
            original_query = record["query"]
            scope = {
                key: record[key] for key in
                ("engine", "country", "region", "language", "device")
            }
            collected_at = normalized_collected_at
    except sqlite3.Error:
        raise ValueError("AUD/SERP source cannot be verified") from None

    capture = inspect_consented_public_html(
        candidate_url, query=original_query, role="COMPETITOR_CANDIDATE",
        consented_hostnames=consented_hostnames, fetcher=fetcher,
    )
    # This check MUST run even if robots/HTTP returned an unobserved
    # status: otherwise an intervening AUD write is hidden as NOT_CAPTURED.
    _assert_aud_still_sealed(db, digest_before)
    if capture.get("status") not in {
        "STATIC_HTML_FEATURES_OBSERVED",
        "STATIC_HTML_WITHOUT_QUERY_BODY_EVIDENCE",
    }:
        return {
            "status": "NOT_CAPTURED", "reason": capture.get("status"),
            "audit_id": audit_dir.name, "serp_observation_id": observation_id,
            "audit_writes": 0, "companion_files_written": 0,
            "provider_requests": capture.get("provider_requests", 0),
            "content_comparison_eligible": False,
        }
    if capture.get("final_url") != candidate:
        raise ValueError("final fetched URL disagrees with authorized source")
    manifest = {
        "contract_version": "RASAI-COMPETITOR-CAPTURE-SIDECAR-330-001",
        "source_audit_id": audit_dir.name,
        "source_audit_db_sha256": digest_before,
        "source_serp_observation_id": observation_id,
        "source_serp_query": original_query,
        "source_serp_collected_at": collected_at,
        "source_serp_scope": scope,
        "requested_url": candidate_url,
        "capture": capture,
        "content_sha256": capture["content_sha256"],
        "content_comparison_eligible": False,
        "primary_content_proven": False,
        "locale_equivalence_proven": False,
        "device_equivalence_proven": False,
        "temporal_equivalence_proven": False,
        "raw_html_persisted": False,
        "audit_writes": 0,
        "limitations": (
            "Separate opt-in static HTML inventory; does not authenticate "
            "provider ranking, hydrated SPA content, locale/device, "
            "business intent or authoritative GEO citation."
        ),
    }
    raw = _payload(manifest)
    package_id = "COBS-" + sha256(raw).hexdigest()[:32].upper()
    dest = destroot / package_id
    if dest.is_symlink():
        raise ValueError("unsafe existing evidence output")
    if dest.exists():
        _assert_aud_still_sealed(db, digest_before)
        if (not dest.is_dir() or (dest / "manifest.json").is_symlink()
                or (dest / "manifest.json").read_bytes() != raw):
            raise ValueError("existing evidence differs; refusing overwrite")
        return {
            "status": "IDEMPOTENT_EXISTING",
            "package_id": package_id, "manifest_path": str(dest / "manifest.json"),
            "audit_writes": 0, "companion_files_written": 0,
            "provider_requests": capture.get("provider_requests", 0),
            "content_comparison_eligible": False,
        }
    destroot.mkdir(parents=True, exist_ok=True)
    if destroot.is_symlink():
        raise ValueError("evidence output root changed to a link")
    temp = Path(tempfile.mkdtemp(prefix=".cobs-staging-", dir=destroot))
    try:
        (temp / "manifest.json").write_bytes(raw)
        if dest.exists() or dest.is_symlink():
            raise ValueError("evidence destination exists; no overwrite")
        _assert_aud_still_sealed(db, digest_before)
        os.rename(temp, dest)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return {
        "status": "MATERIALIZED",
        "package_id": package_id,
        "manifest_path": str(dest / "manifest.json"),
        "audit_writes": 0, "companion_files_written": 1,
        "provider_requests": capture.get("provider_requests", 0),
        "content_comparison_eligible": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Opt-in public competitor HTML evidence outside AUD (#330)."
    )
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--serp-observation-id", required=True)
    parser.add_argument("--candidate-url", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--consent-host", action="append", required=True)
    parser.add_argument("--allow-public-html-requests", action="store_true")
    args = parser.parse_args(argv)
    if not args.allow_public_html_requests:
        parser.error("explicit --allow-public-html-requests is required")
    try:
        result = capture_competitor_sidecar(
            args.audit_dir, args.serp_observation_id, args.candidate_url,
            output_root=args.output_root, consented_hostnames=args.consent_host,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
