"""Versioned, non-secret request-scope provenance for future Perplexity Search runs.

Requested filters never establish the effective provider market, device, ranking
or a generative citation. This module only inspects already persisted SQLite.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import hmac
import json
import sqlite3
from typing import Any, Mapping

from rasai.search_intelligence.perplexity_request_policy import (
    VALID_OPTION_FIELDS, validate_request_options,
)

CONTRACT = "perplexity-request-scope-v1"
ORIGIN = "RASAI-PERPLEXITY-SEARCH-1"
MAX_SCOPE_BYTES = 8192
MAX_QUERY_BYTES = 16384
_STATES = frozenset({
    "PREPARED_NOT_SENT", "TRANSPORT_ATTEMPTED", "HTTP_RESPONSE_OBSERVED",
})


def _bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def build_request_scope(
    payload: Mapping[str, Any], *, request_payload_sha256: str,
    started_at_utc: str, request_attempt_state: str,
) -> dict[str, Any]:
    """Bind the final validated outbound body, never the current .env or headers."""
    if request_attempt_state not in _STATES:
        raise ValueError("invalid transport provenance")
    if not hmac.compare_digest(sha256(_bytes(payload)).hexdigest(),
                               request_payload_sha256):
        raise ValueError("request payload fingerprint mismatch")
    if "query" not in payload:
        raise ValueError("request query is required")
    options = {key: value for key, value in payload.items() if key != "query"}
    if options.get("search_type") not in {"web", "fast"}:
        raise ValueError("invalid request search type")
    validated = validate_request_options(
        {key: value for key, value in options.items() if key != "search_type"},
        search_type=options["search_type"],
    )
    if validated != {key: value for key, value in options.items()
                     if key != "search_type"}:
        raise ValueError("request options must be canonical")
    return {
        "contract_version": CONTRACT,
        "request_payload_sha256": request_payload_sha256,
        "query_binding_sha256": sha256(_bytes({"query": payload["query"]})).hexdigest(),
        "request_options": options,
        "request_attempt_state": request_attempt_state,
        "scope_evidence": {
            "country": "REQUESTED_ONLY" if options.get("country") else "NOT_REQUESTED",
            "language": "REQUESTED_ONLY" if options.get("search_language_filter")
                        else "NOT_REQUESTED",
            "region": "UNSUPPORTED",
            "device": "UNSUPPORTED",
            "intent": "N_D",
            "effective_provider_scope": "N_D",
        },
        "provider_scope_evidence_ref": None,
        "schema_origin": ORIGIN,
        "observed_at_utc": started_at_utc,
    }


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _out(status: str, reason: str) -> dict[str, Any]:
    return {
        "contract": CONTRACT, "status": status, "reason": reason,
        "request_attempt_state": "N/D",
        "country_filter_present": None, "language_filter_present": None,
        "country_requested_matches_serp": None,
        "language_requested_matches_serp": None,
        "device_equivalence_proven": False,
        "effective_provider_scope_proven": False,
        "intent_equivalence_proven": False,
        "generative_citation_proven": False,
        "provider_calls": 0, "audit_writes": 0,
    }


def inspect_request_scope(
    connection: sqlite3.Connection, *, audit_id: str, run_id: str,
    serp_scope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Read a bound future-run record. Never upgrade contextual comparability.

    Caller owns the read-only/immutable database and its byte-integrity gate.
    A missing table or row is ordinary historical legacy, not a failed request.
    """
    legacy = _out("LEGACY_SCOPE_NOT_PERSISTED", "HISTORICAL_REQUEST_SCOPE_N_D")
    try:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='perplexity_search_request_scopes'"
        ).fetchone():
            return legacy
        if not {"run_id", "scope_json"} <= {
            str(row[1]) for row in connection.execute(
                "PRAGMA table_info(perplexity_search_request_scopes)"
            )
        }:
            return _out("SCOPE_UNVERIFIABLE", "SCOPE_SCHEMA_INVALID")
        run_rows = connection.execute(
            "SELECT query_json, search_type, started_at, status, http_status, "
            "request_payload_hash FROM perplexity_search_runs "
            "WHERE run_id=? AND audit_id=? LIMIT 2",
            (run_id, audit_id),
        ).fetchall()
        if len(run_rows) != 1:
            return _out("SCOPE_UNVERIFIABLE", "REQUEST_RUN_IDENTITY_N_D")
        scope_rows = connection.execute(
            "SELECT scope_json FROM perplexity_search_request_scopes "
            "WHERE run_id=? LIMIT 2", (run_id,),
        ).fetchall()
        if not scope_rows:
            return legacy
        if len(scope_rows) != 1:
            return _out("SCOPE_UNVERIFIABLE", "REQUEST_SCOPE_AMBIGUOUS")
        raw = scope_rows[0][0]
        query_json, search_type, started_at, status, http_status, expected_hash = run_rows[0]
        if (not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_SCOPE_BYTES
                or not isinstance(query_json, str)
                or len(query_json.encode("utf-8")) > MAX_QUERY_BYTES):
            return _out("SCOPE_UNVERIFIABLE", "REQUEST_SCOPE_BYTES_N_D")
        parsed = json.loads(raw, object_pairs_hook=_strict_object)
        queries = json.loads(query_json, object_pairs_hook=_strict_object)
        if (not isinstance(parsed, dict) or not isinstance(queries, list)
                or not 1 <= len(queries) <= 5
                or any(not isinstance(q, str) or not q or len(q) > 300
                       for q in queries)
                or len({q.casefold() for q in queries}) != len(queries)
                or _utc(started_at) is None or _utc(parsed.get("observed_at_utc")) is None
                or parsed["observed_at_utc"] != started_at
                or not isinstance(expected_hash, str) or len(expected_hash) != 64):
            return _out("SCOPE_UNVERIFIABLE", "REQUEST_SCOPE_IDENTITY_N_D")
        options = parsed.get("request_options")
        if (not isinstance(options, dict) or "search_type" not in options
                or set(options) - {"search_type", *VALID_OPTION_FIELDS}
                or options["search_type"] != str(search_type).lower()):
            return _out("SCOPE_UNVERIFIABLE", "REQUEST_SCOPE_OPTIONS_N_D")
        payload = {
            "query": queries[0] if len(queries) == 1 else queries,
            **options,
        }
        state = ("PREPARED_NOT_SENT" if status == "NOT_CONFIGURED"
                 else "HTTP_RESPONSE_OBSERVED" if http_status is not None
                 else "TRANSPORT_ATTEMPTED")
        expected = build_request_scope(
            payload, request_payload_sha256=expected_hash,
            started_at_utc=started_at, request_attempt_state=state,
        )
        if parsed != expected:
            return _out("SCOPE_UNVERIFIABLE", "REQUEST_SCOPE_INTEGRITY_N_D")
        result = _out("REQUEST_SCOPE_OBSERVED", "EFFECTIVE_PROVIDER_SCOPE_N_D")
        result["request_attempt_state"] = state
        result["country_filter_present"] = bool(options.get("country"))
        languages = options.get("search_language_filter") or []
        result["language_filter_present"] = bool(languages)
        if serp_scope is None:
            return result
        country = serp_scope.get("country")
        language = serp_scope.get("language")
        if not isinstance(country, str) or not isinstance(language, str):
            result.update(status="SCOPE_UNVERIFIABLE", reason="SERP_SCOPE_N_D")
            return result
        if options.get("country"):
            result["country_requested_matches_serp"] = (
                options["country"].upper() == country.strip().upper()
            )
        if len(languages) == 1:
            # Language-family equality is advisory only: pt does not prove pt-BR
            # locale, and no provider-acknowledged language is inferred.
            result["language_requested_matches_serp"] = (
                languages[0].lower() == language.strip().split("-", 1)[0].lower()
            )
        elif languages and language.strip().split("-", 1)[0].lower() not in languages:
            result["language_requested_matches_serp"] = False
        if False in (
            result["country_requested_matches_serp"],
            result["language_requested_matches_serp"],
        ):
            result.update(status="REQUEST_SCOPE_DIVERGENT",
                          reason="REQUESTED_FILTERS_CONTRADICT_SERP")
        elif (result["country_requested_matches_serp"] is True
              and result["language_requested_matches_serp"] is True):
            result.update(status="REQUEST_FILTERS_MATCH_ONLY",
                          reason="DEVICE_AND_EFFECTIVE_PROVIDER_SCOPE_N_D")
        else:
            result.update(status="REQUEST_SCOPE_N_D",
                          reason="REQUEST_FILTERS_INCOMPLETE_OR_AMBIGUOUS")
        return result
    except (ValueError, TypeError, KeyError, sqlite3.Error,
            UnicodeError, OverflowError, AttributeError):
        return _out("SCOPE_UNVERIFIABLE", "REQUEST_SCOPE_INVALID")
