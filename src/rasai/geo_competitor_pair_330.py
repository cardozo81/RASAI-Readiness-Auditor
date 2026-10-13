"""#330: offline, source-sealed static customer/competitor evidence pairing.

A pair only describes observed HTTP metadata. Without hydrated content and
matched locale/device/session, no deep-content or causal comparison is valid.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from rasai.geo_competitor_capture_bundle_330 import _physical_digest
from rasai.geo_observation import _canonical_url


_CUSTOMER_VERSION = "RASAI-COMPETITOR-CAPTURE-SIDECAR-330-002"
_COMPETITOR_VERSION = "RASAI-COMPETITOR-CAPTURE-SIDECAR-330-001"
_MAX_MANIFEST_BYTES = 128 * 1024
_MAX_WINDOW_SECONDS = 24 * 60 * 60
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SCOPE = ("engine", "country", "region", "language", "device")


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def _reject_duplicate_manifest_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    """Refuse ambiguous COBS JSON even when its raw bytes are rehashed."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate COBS manifest JSON key")
        result[key] = value
    return result


def _reject_non_json_cobs_constant(token: str) -> None:
    """Do not attest manifests containing Python's nonstandard NaN/Infinity."""
    raise ValueError("non-JSON numeric constant in COBS manifest")


def _read_manifest(path: Path) -> Mapping[str, Any]:
    if path.name != "manifest.json" or path.is_symlink() or not path.is_file():
        raise ValueError("physical COBS manifest file required")
    if path.parent.is_symlink() or path.parent.parent.is_symlink():
        raise ValueError("linked COBS package not accepted")
    if path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("COBS manifest exceeds bounded input budget")
    raw = path.read_bytes()
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise ValueError("COBS manifest changed beyond input budget")
    package_id = "COBS-" + sha256(raw).hexdigest()[:32].upper()
    if path.parent.name != package_id:
        raise ValueError("COBS package ID does not match manifest bytes")
    try:
        payload = json.loads(
            raw, object_pairs_hook=_reject_duplicate_manifest_keys,
            parse_constant=_reject_non_json_cobs_constant,
        )
    except (UnicodeError, ValueError, TypeError):
        raise ValueError("COBS manifest JSON invalid") from None
    if not isinstance(payload, dict):
        raise ValueError("COBS manifest must be an object")
    return payload


def _validate_capture(manifest: Mapping[str, Any], expected_role: str) -> None:
    version = _CUSTOMER_VERSION if expected_role == "CUSTOMER" else _COMPETITOR_VERSION
    if manifest.get("contract_version") != version:
        raise ValueError("source COBS capture version does not match role")
    capture = manifest.get("capture")
    if not isinstance(capture, Mapping):
        raise ValueError("source HTML capture provenance missing")
    url = manifest.get("requested_url")
    if (not isinstance(url, str) or len(url) > 1024
            or _canonical_url(url) != url):
        raise ValueError("source URL is not a safe exact URL")
    if (capture.get("role") != expected_role
            or capture.get("requested_url") != url
            or capture.get("final_url") != url
            or capture.get("robots_fetch_status") != "ALLOWED"
            or capture.get("http_status") != 200
            or capture.get("html_rendering") != "STATIC_HTTP_ONLY_NO_JS"
            or capture.get("status") != "STATIC_HTML_FEATURES_OBSERVED"):
        raise ValueError("HTML content not observed under same authorized scope")
    digest = capture.get("content_sha256")
    if (not isinstance(digest, str) or not _SHA.fullmatch(digest)
            or manifest.get("content_sha256") != digest):
        raise ValueError("source content SHA-256 provenance missing")
    if any(manifest.get(flag) is not False for flag in (
        "content_comparison_eligible", "primary_content_proven",
        "locale_equivalence_proven", "device_equivalence_proven",
        "temporal_equivalence_proven", "raw_html_persisted",
    )):
        raise ValueError("COBS provenance cannot claim non-observed equivalence")
    if (not isinstance(manifest.get("source_serp_scope"), Mapping)
            or any(
                not isinstance(manifest["source_serp_scope"].get(k), str)
                or not manifest["source_serp_scope"][k].strip()
                for k in _SCOPE
            )
            or not isinstance(manifest.get("source_serp_query"), str)
            or not manifest["source_serp_query"].strip()
            or _time(manifest.get("source_serp_collected_at")) is None
            or _time(capture.get("html_fetch_timestamp")) is None):
        raise ValueError("COBS observation/collection clock or context missing")
    if expected_role == "CUSTOMER":
        if (manifest.get("source_role") != "CUSTOMER"
                or manifest.get("source_target_exact_url") != url
                or type(manifest.get("source_serp_result_membership_proven")) is not bool):
            raise ValueError("CUSTOMER role lacks exact AUD target attestation")


def _verify_physical_serp_pair(
    db: Path, audit_id: str, customer: Mapping[str, Any],
    competitor: Mapping[str, Any],
) -> None:
    """Rebind untrusted COBS manifest claims to the sealed AUD, without writes."""
    observation_id = customer["source_serp_observation_id"]
    try:
        with closing(sqlite3.connect(
            db.resolve().as_uri() + "?mode=ro&immutable=1", uri=True, timeout=2,
        )) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            observations = con.execute(
                "SELECT audit_id,query,collected_at,observation_status,data_mode,"
                "engine,country,region,language,device FROM serp_observations "
                "WHERE observation_id=? LIMIT 2", (observation_id,),
            ).fetchall()
            if len(observations) != 1:
                raise ValueError("COBS physical SERP observation not unique")
            obs = observations[0]
            if (obs["audit_id"] != audit_id
                    or obs["observation_status"] != "OBSERVED"
                    or obs["data_mode"] != "OBSERVED_API"
                    or obs["query"] != customer["source_serp_query"]
                    or _time(obs["collected_at"]) is None
                    or _time(obs["collected_at"]) != _time(customer["source_serp_collected_at"])
                    or any(obs[k] != customer["source_serp_scope"][k] for k in _SCOPE)):
                raise ValueError("COBS manifest SERP scope differs from physical AUD")
            targets = con.execute(
                "SELECT input_url FROM audit_targets WHERE audit_id=? LIMIT 2",
                (audit_id,),
            ).fetchall()
            if (len(targets) != 1
                    or _canonical_url(targets[0][0]) != customer["requested_url"]):
                raise ValueError("COBS customer URL is not the physical AUD target")
            returned = con.execute(
                "SELECT url FROM serp_results WHERE observation_id=? LIMIT 501",
                (observation_id,),
            ).fetchall()
            if (len(returned) > 500
                    or _canonical_url(competitor["requested_url"]) not in {
                        _canonical_url(row[0]) for row in returned
                    }):
                raise ValueError("COBS competitor URL not in physical SERP results")
    except sqlite3.Error:
        raise ValueError("COBS physical SERP/AUD source unreadable") from None


def _facts(manifest: Mapping[str, Any]) -> dict[str, Any]:
    capture = manifest["capture"]
    count = capture.get("word_count")
    if type(count) is not int or not 0 < count <= 1_000_000:
        raise ValueError("unbounded/invalid static HTML word count")
    title = capture.get("title")
    if not isinstance(title, str) or len(title) > 500:
        raise ValueError("invalid observed HTML title")
    features = {}
    for field in ("headings", "jsonld_types", "query_body_terms"):
        items = capture.get(field)
        if (not isinstance(items, list) or len(items) > 100
                or any(not isinstance(t, str) or len(t) > 500 for t in items)):
            raise ValueError("invalid observed HTML features")
        features[field] = sorted(set(items))
    return {
        "url": manifest["requested_url"],
        "title": title,
        "word_count_observed_static": count,
        "content_sha256": capture["content_sha256"],
        "html_fetch_timestamp": capture["html_fetch_timestamp"],
        **features,
    }


def compare_cobs_static_pair(
    audit_dir: Path, customer_manifest: Path, competitor_manifest: Path,
) -> dict[str, Any]:
    """Inspect both sealed sidecars without fetching content or modifying AUD."""
    root = Path(audit_dir)
    db = root / "audit.db"
    if (not root.name.startswith("AUD-") or not root.is_dir()
            or root.is_symlink() or db.is_symlink() or not db.is_file()
            or any(Path(str(db) + x).exists()
                   for x in ("-wal", "-shm", "-journal"))):
        raise ValueError("stable physical AUD source required")
    before = _physical_digest(db)
    customer = _read_manifest(Path(customer_manifest))
    competitor = _read_manifest(Path(competitor_manifest))
    _validate_capture(customer, "CUSTOMER")
    _validate_capture(competitor, "COMPETITOR_CANDIDATE")
    common = (
        "source_audit_id", "source_audit_db_sha256",
        "source_serp_observation_id", "source_serp_query",
        "source_serp_collected_at", "source_serp_scope",
    )
    if (any(customer.get(field) != competitor.get(field) for field in common)
            or customer.get("source_audit_id") != root.name
            or customer.get("source_audit_db_sha256") != before
            or not isinstance(customer.get("source_serp_observation_id"), str)
            or not customer["source_serp_observation_id"].strip()):
        raise ValueError("COBS pair refers to different physical AUD/SERP evidence")
    customer_url = customer["requested_url"]
    competitor_url = competitor["requested_url"]
    if customer_url == competitor_url or (
        urlsplit(customer_url).hostname == urlsplit(competitor_url).hostname
    ):
        raise ValueError("pair must contain target and distinct competitor host")
    _verify_physical_serp_pair(db, root.name, customer, competitor)
    customer_time = _time(customer["capture"]["html_fetch_timestamp"])
    competitor_time = _time(competitor["capture"]["html_fetch_timestamp"])
    assert customer_time is not None and competitor_time is not None
    gap = abs((customer_time - competitor_time).total_seconds())
    if gap > _MAX_WINDOW_SECONDS:
        raise ValueError("static HTML captures are outside permitted 24h window")
    customer_facts = _facts(customer)
    competitor_facts = _facts(competitor)
    # Never coerce missing or synthetic primary content into editorial
    # differences. The only cross-source observations here are metadata sets.
    customer_types = set(customer_facts["jsonld_types"])
    competitor_types = set(competitor_facts["jsonld_types"])
    result = {
        "contract_version": "RASAI-COBS-STATIC-METADATA-PAIR-330-001",
        "status": "DESCRIPTIVE_STATIC_HTML_ONLY",
        "source_audit_id": root.name,
        "source_audit_db_sha256": before,
        "source_serp_observation_id": customer["source_serp_observation_id"],
        "source_serp_query": customer["source_serp_query"],
        "source_serp_scope": customer["source_serp_scope"],
        "html_capture_gap_seconds": gap,
        "customer": customer_facts,
        "competitor": competitor_facts,
        "title_exact_text_equal": customer_facts["title"] == competitor_facts["title"],
        "observed_jsonld_types_both": sorted(customer_types & competitor_types),
        "observed_jsonld_types_customer_only": sorted(customer_types - competitor_types),
        "observed_jsonld_types_competitor_only": sorted(competitor_types - customer_types),
        "primary_content_comparison_eligible": False,
        "localisation_equivalence_proven": False,
        "device_equivalence_proven": False,
        "intent_equivalence_proven": False,
        "same_browser_sample_proven": False,
        "generative_citation_proven": False,
        "editorial_gap_claim_eligible": False,
        "word_count_delta_eligible": False,
        "provider_requests": 0, "audit_writes": 0,
        "limitations": (
            "These are two authorized static HTTP feature inventories, not "
            "rendered/primary text, equal locale or device, generative citations, "
            "same intent or comparable commercial completeness. Metadata "
            "differences are observations only, not deficits or priorities."
        ),
    }
    if (any(Path(str(db) + x).exists() for x in ("-wal", "-shm", "-journal"))
            or db.is_symlink() or _physical_digest(db) != before):
        raise ValueError("physical AUD changed during COBS pair inspection")
    # Source sidecars are physical inputs too. A package may be swapped,
    # relinked or rewritten while the SQLite evidence is being verified.
    # Recheck both content-addressed manifests before returning derived
    # metadata, rather than attesting only the AUD's stable bytes.
    if (_read_manifest(Path(customer_manifest)) != customer
            or _read_manifest(Path(competitor_manifest)) != competitor):
        raise ValueError("COBS source manifests changed during pair inspection")
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline customer/competitor static HTML facts, never GEO scoring."
    )
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--customer-manifest", type=Path, required=True)
    parser.add_argument("--competitor-manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_cobs_static_pair(
            args.audit_dir, args.customer_manifest, args.competitor_manifest,
        )
    except (ValueError, OSError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
