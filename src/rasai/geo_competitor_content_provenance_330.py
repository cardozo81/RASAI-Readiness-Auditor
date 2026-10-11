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
from typing import Any, Sequence

from rasai.geo_observation import _canonical_url
from rasai.search_intelligence.content import query_terms

_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_MAX_ROWS = 40
_REQUIRED_OBS = {"observation_id", "audit_id", "query", "collected_at",
                 "observation_status", "data_mode"}
_REQUIRED_CONTENT = {"observation_id", "role", "requested_url", "final_url",
                     "fetch_status", "http_status", "content_sha256",
                     "bytes_read", "word_count", "title", "headings_json",
                     "query_terms_json", "query_terms_body_json"}


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute("PRAGMA table_info(" + table + ")")}


def _texts(value: object) -> list[str]:
    try:
        values = json.loads(value) if isinstance(value, str) else []
    except (ValueError, TypeError):
        return []
    if not isinstance(values, list):
        return []
    return [item[:120] for item in values[:20]
            if isinstance(item, str) and item.strip()]


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


def _parse_context_clock(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value.tzinfo is not None and value.utcoffset() is not None
    except (TypeError, ValueError, OverflowError):
        return False


def _page(row: sqlite3.Row, expected_terms: tuple[str, ...]) -> dict[str, Any]:
    requested = row["requested_url"]
    final = row["final_url"] or requested
    requested_url = _canonical_url(requested)
    final_url = _canonical_url(final)
    indexed_terms = _strict_query_terms(row["query_terms_json"])
    body_terms = _strict_query_terms(row["query_terms_body_json"])
    lexical_body_matches = (
        bool(expected_terms) and indexed_terms == expected_terms
        and bool(body_terms) and set(body_terms).issubset(indexed_terms)
    )
    valid_content = (
        lexical_body_matches
        str(row["fetch_status"]).upper() == "OBSERVED"
        and type(row["http_status"]) is int and 200 <= row["http_status"] < 300
        and isinstance(row["content_sha256"], str)
        and bool(_SHA256.fullmatch(row["content_sha256"]))
        and type(row["bytes_read"]) is int and row["bytes_read"] > 0
        and type(row["word_count"]) is int and row["word_count"] > 0
        and bool(requested_url and final_url)
        and bool((row["title"].strip() if isinstance(row["title"], str) else "")
                 or _texts(row["headings_json"]))
    )
    return {
        "role": row["role"],
        "requested_url": requested if requested_url else None,
        "final_url": final if final_url else None,
        "content_evidence_status": (
            "PERSISTED_HTML_FEATURES" if valid_content else "NOT_COMPARABLE"
        ),
        "http_status": row["http_status"],
        "content_sha256": row["content_sha256"] if valid_content else None,
        "word_count": row["word_count"] if valid_content else None,
        "title_present": bool((row["title"] or "").strip()) if valid_content else None,
        "headings_count": len(_texts(row["headings_json"])) if valid_content else None,
        "query_body_terms": list(body_terms) if valid_content else [],
        "primary_content_proven": False,
    }


def inspect_geo_competitor_content(
    database: Path, audit_id: str, observation_id: str,
) -> dict[str, Any]:
    """Inspect only SERP-context-matched, persisted HTML features; no writes."""
    database = Path(database)
    if not database.is_file() or database.is_symlink():
        raise ValueError("existing non-symlink audit.db required")
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

    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        if not _REQUIRED_OBS <= _columns(con, "serp_observations"):
            return abstain("SERP_OBSERVATION_SCHEMA_ND")
        if not _REQUIRED_CONTENT <= _columns(con, "serp_competitive_pages"):
            return abstain("CONTENT_EVIDENCE_SCHEMA_ND")
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
        rows = con.execute(
            "SELECT role, requested_url, final_url, fetch_status, "
            "http_status, content_sha256, bytes_read, word_count, "
            "title, headings_json, query_terms_json, query_terms_body_json "
            "FROM serp_competitive_pages "
            "WHERE observation_id=? ORDER BY role, requested_url LIMIT ?",
            (observation_id, _MAX_ROWS + 1),
        ).fetchall()
    if len(rows) > _MAX_ROWS:
        return abstain("CONTENT_EVIDENCE_LIMIT_EXCEEDED")
    customer_rows = [row for row in rows if row["role"] == "CUSTOMER"]
    if len(customer_rows) != 1:
        return abstain("CUSTOMER_HTML_EVIDENCE_ND")
    expected = query_terms(observed["query"])
    customer = _page(customer_rows[0], expected)
    competitors = [_page(row, expected) for row in rows
                   if row["role"] == "COMPETITOR_CANDIDATE"]
    context = {key: observed[key] for key in
               ("query", "collected_at", "country", "region",
                "language", "device", "engine")}
    context["html_fetch_timestamp"] = None  # not in persisted schema
    comparisons = []
    if customer["content_evidence_status"] == "PERSISTED_HTML_FEATURES":
        seen_urls = set()
        for candidate in competitors:
            if candidate["content_evidence_status"] != "PERSISTED_HTML_FEATURES":
                continue
            canonical = _canonical_url(candidate["requested_url"])
            if not canonical or canonical == _canonical_url(customer["requested_url"]):
                continue
            if canonical in seen_urls:
                continue
            seen_urls.add(canonical)
            comparisons.append({
                "competitor_url": candidate["requested_url"],
                "customer_content_sha256": customer["content_sha256"],
                "competitor_content_sha256": candidate["content_sha256"],
                "observed_word_count_difference":
                    candidate["word_count"] - customer["word_count"],
                "meaning": "DESCRIPTIVE_CONTENT_ONLY_NO_CAUSAL_CLAIM",
            })
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
