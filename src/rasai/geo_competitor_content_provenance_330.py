"""#330: read-only deep competitor content facts from *already collected* SERP pages.

Never fetch new URLs, infer Perplexity snippets as HTML, score the audited
page, or update the sealed AUD. A SERP observation timestamp is NOT a
physical timestamp of competitive HTML acquisition.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlsplit
from typing import Any, Sequence

from rasai.geo_observation import _canonical_url
from rasai.geo_competitor_capture_bundle_330 import _physical_digest
from rasai.search_intelligence.content import query_terms

_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_MAX_ROWS = 40
_REQUIRED_OBS = {"observation_id", "audit_id", "query", "collected_at",
                 "observation_status", "data_mode"}
_REQUIRED_CONTENT = {"observation_id", "role", "requested_url", "final_url",
                     "fetch_status", "http_status", "content_type", "content_sha256",
                     "bytes_read", "word_count", "title", "headings_json",
                     "query_terms_json", "query_terms_body_json"}
# These columns are present in the current canonical collector, but missing
# from some legacy test AUDs. An absent column must yield N/D, not invented
# zero matches or a backfill into historic SQLite packages.
_OPTIONAL_CONTENT = ("meta_description", "query_terms_title_json",
                     "query_terms_description_json", "query_terms_headings_json",
                     "jsonld_types_json")


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute("PRAGMA table_info(" + table + ")")}


def _strict_headings(value: object) -> list[str] | None:
    """A missing, invalid, or truncated heading ledger is NOT an empty one.

    Use the physically persisted list as supplied by the existing collector.
    If the observed source cannot be fully parsed within a bounded budget,
    do not publish a guessed zero or shortened headings count.
    """
    if not isinstance(value, str) or len(value.encode("utf-8")) > 128 * 1024:
        return None
    try:
        values = json.loads(value)
    except (TypeError, ValueError):
        return None
    if (not isinstance(values, list) or len(values) > 100
            or any(not isinstance(item, str) or not item.strip()
                   or len(item) > 500 for item in values)):
        return None
    return values


def _strict_query_terms(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, str):
        return ()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return ()
    if (not isinstance(parsed, list) or not 1 <= len(parsed) <= 20
            or any(not isinstance(term, str) or not term.strip()
                   for term in parsed)):
        return ()
    return tuple(parsed)


def _optional_jsonld_types(raw: object) -> list[str] | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if (not isinstance(parsed, list) or len(parsed) > 20
            or any(not isinstance(value, str) or not value.strip()
                   for value in parsed)):
        return None
    return [value[:120] for value in parsed]


def _optional_terms(raw: object, expected: tuple[str, ...]) -> list[str] | None:
    """Validate a bounded lexical projection against its original query.

    Empty list is an observed zero; absent or corrupted JSON is N/D.
    """
    if raw is None or not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if (not isinstance(parsed, list) or len(parsed) > 20
            or any(not isinstance(value, str) or not value.strip()
                   for value in parsed)):
        return None
    if (len(set(parsed)) != len(parsed)
            or not set(parsed).issubset(set(expected))):
        return None
    return parsed


def _parse_context_clock(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.tzinfo is not None and value.utcoffset() is not None
    except (TypeError, ValueError, OverflowError):
        return False


def _same_observed_http_origin(first: object, second: object) -> bool:
    """Same scheme, canonical host and effective port; paths may redirect.

    A shared DNS hostname on HTTP versus HTTPS or on an alternate TCP
    port is not proof that both URLs refer to the same web application.
    """
    a = _canonical_url(first)
    b = _canonical_url(second)
    if not a or not b:
        return False
    lhs, rhs = urlsplit(a), urlsplit(b)
    return (lhs.scheme, lhs.netloc) == (rhs.scheme, rhs.netloc)


def _page(row: sqlite3.Row, expected_terms: tuple[str, ...]) -> dict[str, Any]:
    requested = row["requested_url"]
    final = row["final_url"]
    requested_url = _canonical_url(requested)
    # Observed HTML must carry the concrete destination fetched. A NULL
    # final_url cannot be promoted into evidence of the requested SERP URL:
    # the transport may have redirected to a different page.
    final_url = _canonical_url(final)
    indexed_terms = _strict_query_terms(row["query_terms_json"])
    body_terms = _strict_query_terms(row["query_terms_body_json"])
    lexical_body_matches = (
        bool(expected_terms) and indexed_terms == expected_terms
        and bool(body_terms) and set(body_terms).issubset(indexed_terms)
    )
    headings = _strict_headings(row["headings_json"])
    title = row["title"] if isinstance(row["title"], str) else ""
    raw_type = row["content_type"]
    media_type = (
        raw_type.split(";", 1)[0].strip().casefold()
        if isinstance(raw_type, str) else ""
    )
    valid_content = (
        media_type in {"text/html", "application/xhtml+xml"}
        and lexical_body_matches
        and str(row["fetch_status"]).upper() == "OBSERVED"
        and type(row["http_status"]) is int and 200 <= row["http_status"] < 300
        and isinstance(row["content_sha256"], str)
        and bool(_SHA256.fullmatch(row["content_sha256"]))
        and type(row["bytes_read"]) is int and row["bytes_read"] > 0
        and type(row["word_count"]) is int and row["word_count"] > 0
        and bool(requested_url and final_url)
        and headings is not None
        and bool(title.strip() or headings)
    )
    title_terms = _optional_terms(row["query_terms_title_json"], expected_terms)
    description_terms = _optional_terms(row["query_terms_description_json"], expected_terms)
    heading_terms = _optional_terms(row["query_terms_headings_json"], expected_terms)
    jsonld_types = _optional_jsonld_types(row["jsonld_types_json"])
    return {
        "role": row["role"],
        "requested_url": requested if requested_url else None,
        "final_url": final if final_url else None,
        "content_evidence_status": (
            "PERSISTED_HTML_FEATURES" if valid_content else "NOT_COMPARABLE"
        ),
        "http_status": row["http_status"],
        "verified_html_media_type": media_type if valid_content else None,
        "content_sha256": row["content_sha256"] if valid_content else None,
        "word_count": row["word_count"] if valid_content else None,
        "title_present": bool(title.strip()) if valid_content else None,
        "headings_count": len(headings) if valid_content else None,
        "query_body_terms": list(body_terms) if valid_content else [],
        "query_title_terms": title_terms if valid_content else None,
        "query_description_terms": description_terms if valid_content else None,
        "query_heading_terms": heading_terms if valid_content else None,
        "meta_description_present": (
            bool(row["meta_description"].strip())
            if valid_content and isinstance(row["meta_description"], str) else None
        ),
        "jsonld_types": jsonld_types if valid_content else None,
        "primary_content_proven": False,
    }


def inspect_geo_competitor_content(
    database: Path, audit_id: str, observation_id: str,
) -> dict[str, Any]:
    """Inspect only SERP-context-matched, persisted HTML features; no writes."""
    database = Path(database)
    if not database.is_file() or database.is_symlink():
        raise ValueError("existing non-symlink audit.db required")
    if any(Path(str(database) + suffix).exists()
           for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("source AUD has pending SQLite sidecars")
    if not isinstance(audit_id, str) or not audit_id.startswith("AUD-"):
        raise ValueError("audit identity required")
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise ValueError("SERP observation identity required")
    base = {
        "contract_version": "RASAI-GEO-DEEP-COMPETITOR-READONLY-001",
        "audit_id": audit_id, "serp_observation_id": observation_id,
        "provider_requests": 0, "audit_writes": 0,
        "score_changed": False, "new_collection": False,
        "perplexity_content_observed": False,
        "limitations": (
            "Somente atributos de HTML previamente coletado pela SERP com opt-in. "
            "Nenhum snippet Perplexity prova conteúdo integral; contexto SERP "
            "não comprova instante da coleta HTML, equivalência entre fornecedores "
            "ou causa de ranking. Diferenças de volume não provam qualidade. "
            "Mesmo cobertura lexical no corpo da resposta não comprova "
            "conteúdo primário: shells SPA e menus podem conter os termos."
        ),
    }
    def abstain(status: str) -> dict[str, Any]:
        return {**base, "status": status, "context": None,
                "customer": None, "competitors": [], "comparisons": []}

    source_digest = _physical_digest(database)
    with sqlite3.connect(
        database.resolve().as_uri() + "?mode=ro&immutable=1", uri=True,
    ) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        if not _REQUIRED_OBS <= _columns(con, "serp_observations"):
            return abstain("SERP_OBSERVATION_SCHEMA_ND")
        if not _REQUIRED_CONTENT <= _columns(con, "serp_competitive_pages"):
            return abstain("CONTENT_EVIDENCE_SCHEMA_ND")
        if not {"observation_id", "url"} <= _columns(con, "serp_results"):
            # The persisted content table alone cannot prove that the
            # competitor URL was actually returned by this SERP observation.
            return abstain("SERP_RESULT_URL_PROVENANCE_ND")
        # The content ledger may have only observation_id, not audit_id.
        # Treat the observation ID as a *global* source key or fail closed:
        # a duplicate under a foreign AUD could otherwise inject its HTML.
        observed_ids = con.execute(
            "SELECT audit_id FROM serp_observations WHERE observation_id=? LIMIT 2",
            (observation_id,),
        ).fetchall()
        if len(observed_ids) > 1:
            return abstain("SERP_OBSERVATION_ID_AMBIGUOUS_OR_FOREIGN")
        if len(observed_ids) != 1 or observed_ids[0]["audit_id"] != audit_id:
            return abstain("SERP_OBSERVATION_NOT_VERIFIED")
        optional = ("country", "region", "language", "device", "engine")
        known = _columns(con, "serp_observations")
        fields = ", ".join(name if name in known else "NULL AS " + name
                           for name in optional)
        context = con.execute(
            "SELECT query, collected_at, observation_status, data_mode, " +
            fields + " FROM serp_observations "
            "WHERE audit_id=? AND observation_id=? LIMIT 2",
            (audit_id, observation_id),
        ).fetchall()
        if len(context) != 1:
            return abstain("SERP_OBSERVATION_NOT_VERIFIED")
        observed = context[0]
        if (observed["data_mode"] != "OBSERVED_API"
                or observed["observation_status"] != "OBSERVED"
                or not isinstance(observed["query"], str)
                or not observed["query"].strip()
                or not _parse_context_clock(observed["collected_at"])):
            return abstain("SERP_CONTEXT_NOT_PROVEN")
        serp_result_rows = con.execute(
            "SELECT url FROM serp_results WHERE observation_id=? LIMIT ?",
            (observation_id, _MAX_ROWS * 20 + 1),
        ).fetchall()
        if len(serp_result_rows) > _MAX_ROWS * 20:
            return abstain("SERP_RESULT_URL_VOLUME_EXCEEDED")
        observed_serp_urls = {
            _canonical_url(row[0]) for row in serp_result_rows
        }
        observed_serp_urls.discard("")
        if not observed_serp_urls:
            return abstain("SERP_RESULT_URL_PROVENANCE_ND")
        # A 'CUSTOMER' role in the HTML feature ledger is a label, not
        # a binding to the AUD target. Require the unique physical input URL
        # in this AUD before its content may participate in a comparison.
        if not {"audit_id", "input_url"} <= _columns(con, "audit_targets"):
            return abstain("AUD_TARGET_URL_PROVENANCE_ND")
        targets = con.execute(
            "SELECT input_url FROM audit_targets WHERE audit_id=? LIMIT 2",
            (audit_id,),
        ).fetchall()
        target_url = (
            _canonical_url(targets[0]["input_url"])
            if len(targets) == 1 else ""
        )
        if not target_url:
            return abstain("AUD_TARGET_URL_PROVENANCE_ND")
        content_columns = _columns(con, "serp_competitive_pages")
        optional_fields = ", ".join(
            name if name in content_columns else "NULL AS " + name
            for name in _OPTIONAL_CONTENT
        )
        # If a schema version has per-content audit scope, reject foreign
        # rows rather than silently folding them into the current page pair.
        if "audit_id" in content_columns:
            foreign = con.execute(
                "SELECT 1 FROM serp_competitive_pages "
                "WHERE observation_id=? AND (audit_id IS NULL OR audit_id!=?) LIMIT 1",
                (observation_id, audit_id),
            ).fetchone()
            if foreign:
                return abstain("CROSS_AUD_CONTENT_PROVENANCE_UNVERIFIABLE")
        rows = con.execute(
            "SELECT role, requested_url, final_url, fetch_status, "
            "http_status, content_type, content_sha256, bytes_read, word_count, "
            "title, headings_json, query_terms_json, query_terms_body_json, "
            + optional_fields + " FROM serp_competitive_pages "
            "WHERE observation_id=? ORDER BY role, requested_url LIMIT ?",
            (observation_id, _MAX_ROWS + 1),
        ).fetchall()
    if (any(Path(str(database) + suffix).exists()
            for suffix in ("-wal", "-shm", "-journal"))
            or _physical_digest(database) != source_digest):
        return abstain("AUD_SOURCE_CHANGED_DURING_READ")
    if len(rows) > _MAX_ROWS:
        return abstain("CONTENT_EVIDENCE_LIMIT_EXCEEDED")
    customer_rows = [row for row in rows if row["role"] == "CUSTOMER"]
    if len(customer_rows) != 1:
        return abstain("CUSTOMER_HTML_EVIDENCE_ND")
    # Two physical HTML rows for the same observed candidate URL can
    # disagree on content SHA or lexical statistics. Picking the first
    # SQL row silently makes the reported comparison order-dependent.
    # Different SERP aliases with a common final URL are *not* identical
    # requested URLs and still use downstream destination deduplication.
    candidate_keys: set[str] = set()
    for item in rows:
        if item["role"] != "COMPETITOR_CANDIDATE":
            continue
        identity = _canonical_url(item["requested_url"])
        if identity and identity in candidate_keys:
            return abstain("COMPETITOR_HTML_REQUESTED_URL_AMBIGUOUS")
        if identity:
            candidate_keys.add(identity)
    expected = query_terms(observed["query"])
    customer = _page(customer_rows[0], expected)
    customer["aud_target_exact_url_proven"] = (
        isinstance(customer["requested_url"], str)
        and _canonical_url(customer["requested_url"]) == target_url
    )
    competitors = [_page(row, expected) for row in rows
                   if row["role"] == "COMPETITOR_CANDIDATE"]
    for candidate in competitors:
        candidate["serp_result_membership_proven"] = (
            isinstance(candidate["requested_url"], str)
            and _canonical_url(candidate["requested_url"]) in observed_serp_urls
        )
    context = {key: observed[key] for key in
               ("query", "collected_at", "country", "region",
                "language", "device", "engine")}
    context["html_fetch_timestamp"] = None  # not in persisted schema
    comparisons = []
    if (
        customer["content_evidence_status"] == "PERSISTED_HTML_FEATURES"
        and customer["aud_target_exact_url_proven"] is True
        # Distinct HTTP origins (including scheme/port) may serve different
        # applications even if the DNS hostname happens to be identical.
        and _same_observed_http_origin(
            customer["requested_url"], customer["final_url"]
        )
    ):
        # The persisted content belongs to the final fetched URL, not
        # necessarily to the candidate SERP URL. Redirects to the audited
        # page are not independent competitor evidence; aliases landing on
        # one destination must not inflate a comparison cohort.
        customer_urls = {
            _canonical_url(customer["requested_url"]),
            _canonical_url(customer["final_url"]),
        }
        seen_destinations = set()
        for candidate in competitors:
            if (candidate["content_evidence_status"] != "PERSISTED_HTML_FEATURES"
                    or candidate["serp_result_membership_proven"] is not True):
                continue
            requested = _canonical_url(candidate["requested_url"])
            destination = _canonical_url(candidate["final_url"])
            if (not requested or not destination
                    # Cross-origin HTML cannot be assigned to the original
                    # SERP candidate, including same-host port/scheme changes.
                    or not _same_observed_http_origin(requested, destination)
                    or requested in customer_urls or destination in customer_urls
                    or destination in seen_destinations):
                continue
            seen_destinations.add(destination)
            comparisons.append({
                "competitor_url": candidate["requested_url"],
                "customer_content_sha256": customer["content_sha256"],
                "competitor_content_sha256": candidate["content_sha256"],
                "observed_word_count_difference":
                    candidate["word_count"] - customer["word_count"],
                "observed_lexical_differences": {
                    label: (
                        len(candidate[field]) - len(customer[field])
                        if candidate[field] is not None and customer[field] is not None
                        else None
                    )
                    for label, field in (
                        ("query_terms_in_title", "query_title_terms"),
                        ("query_terms_in_description", "query_description_terms"),
                        ("query_terms_in_headings", "query_heading_terms"),
                        ("query_terms_in_body", "query_body_terms"),
                    )
                },
                "meaning": "DESCRIPTIVE_CONTENT_ONLY_NO_CAUSAL_CLAIM",
            })
    if (any(Path(str(database) + suffix).exists()
            for suffix in ("-wal", "-shm", "-journal"))
            or _physical_digest(database) != source_digest):
        return abstain("AUD_SOURCE_CHANGED_DURING_READ")
    return {
        **base,
        "status": ("DESCRIPTIVE_PERSISTED_HTML_COMPARISON"
                   if comparisons else "CONTENT_EVIDENCE_NOT_COMPARABLE"),
        "context": context, "customer": customer,
        "competitors": competitors, "comparisons": comparisons,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only GEO competitor HTML evidence")
    parser.add_argument("database", type=Path)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--serp-observation-id", required=True)
    options = parser.parse_args(argv)
    output = inspect_geo_competitor_content(
        options.database, options.audit_id, options.serp_observation_id
    )
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
