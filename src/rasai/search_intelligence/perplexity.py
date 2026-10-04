"""Perplexity Search API integration for external Search Intelligence.

This module intentionally stays outside the canonical evidence-bound AI provider registry.
Perplexity Search results are external research provenance: they never become deterministic
SERP observations, findings, scores, SARI inputs, CAT inputs or evidence-seal material.

Commercial usage reuses the native usage/pricing contract introduced by issue #8.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from rasai.ai_cost_policy import PricingApplication, resolve_native_usage_cost
from rasai.ai_native_usage import NativeUsageComponent, PERPLEXITY_SEARCH_REQUEST
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderUsage,
)
from rasai.m18_persistence import M18Persistence
from rasai.persistence import AuditWorkspace

PROVIDER = "PERPLEXITY"
SURFACE = "SEARCH_API"
API_KEY_ENV = "PERPLEXITY_API_KEY"
ENDPOINT = "https://api.perplexity.ai/search"
CONTRACT_VERSION = "RASAI-PERPLEXITY-SEARCH-1"
PROVENANCE_KIND = "EXTERNAL_SEARCH_INTELLIGENCE"
MAX_QUERIES_PER_REQUEST = 5
MAX_RESPONSE_BYTES = 2_000_000
SUPPORTED_SEARCH_TYPES = frozenset({"web", "fast"})


class PerplexityConfigurationError(ValueError):
    """Raised when an explicit Perplexity request is not configured safely."""


class PerplexityNetworkError(OSError):
    """Raised when no HTTP response was obtained."""


class PerplexityTimeoutError(TimeoutError):
    """Raised when the transport times out before a response is available."""


@dataclass(frozen=True, slots=True)
class PerplexityHttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class PerplexitySource:
    position: int
    url: str
    title: str
    snippet: str
    source_date: str | None = None
    last_updated: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PerplexitySearchRun:
    run_id: str
    audit_id: str
    queries: tuple[str, ...]
    purpose: str
    search_type: str
    started_at: datetime
    finished_at: datetime
    status: str
    provider_response_id: str | None
    http_status: int | None
    diagnostic: ProviderDiagnostic | None
    sources: tuple[PerplexitySource, ...]
    request_payload_hash: str
    native_usage: tuple[NativeUsageComponent, ...]
    pricing: PricingApplication
    attempt_id: str | None = None

    @property
    def citation_urls(self) -> tuple[str, ...]:
        return tuple(item.url for item in self.sources)


PerplexityTransport = Callable[
    [str, Mapping[str, str], bytes, float],
    PerplexityHttpResponse,
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex.upper()}"


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _payload_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _read_limited(stream: Any) -> bytes:
    data = stream.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Perplexity response exceeds the configured safety limit")
    return data


def _default_transport(
    endpoint: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout_seconds: float,
) -> PerplexityHttpResponse:
    request = Request(endpoint, data=body, headers=dict(headers), method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return PerplexityHttpResponse(
                status=int(response.status),
                headers={str(k): str(v) for k, v in response.headers.items()},
                body=_read_limited(response),
            )
    except HTTPError as exc:
        return PerplexityHttpResponse(
            status=int(exc.code),
            headers={str(k): str(v) for k, v in exc.headers.items()},
            body=_read_limited(exc),
        )
    except socket.timeout as exc:
        raise PerplexityTimeoutError("Perplexity Search API timed out") from exc
    except TimeoutError as exc:
        raise PerplexityTimeoutError("Perplexity Search API timed out") from exc
    except URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            raise PerplexityTimeoutError("Perplexity Search API timed out") from exc
        raise PerplexityNetworkError("Perplexity Search API network error") from exc


def _headers_get(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.casefold()
    for key, value in headers.items():
        if str(key).casefold() == wanted:
            return str(value)
    return None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    raw = _headers_get(headers, "Retry-After")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _http_error_class(status: int) -> ProviderErrorClass:
    if status == 401:
        return ProviderErrorClass.AUTH_ERROR
    if status == 403:
        return ProviderErrorClass.PERMISSION_ERROR
    if status == 429:
        return ProviderErrorClass.RATE_LIMIT_ERROR
    if status >= 500:
        return ProviderErrorClass.SERVER_ERROR
    return ProviderErrorClass.CONTRACT_ERROR


def _attempt_status(diagnostic: ProviderDiagnostic | None) -> AttemptStatus:
    if diagnostic is None or diagnostic.error_class is None:
        return AttemptStatus.SUCCESS
    if diagnostic.error_class in {
        ProviderErrorClass.AUTH_ERROR,
        ProviderErrorClass.PERMISSION_ERROR,
        ProviderErrorClass.QUOTA_ERROR,
        ProviderErrorClass.CREDIT_ERROR,
        ProviderErrorClass.RATE_LIMIT_ERROR,
    }:
        return AttemptStatus.BUSINESS_ERROR
    if diagnostic.error_class in {
        ProviderErrorClass.CONTRACT_ERROR,
        ProviderErrorClass.EMPTY_RESPONSE,
        ProviderErrorClass.INVALID_RESPONSE,
    }:
        return AttemptStatus.CONTRACT_ERROR
    return AttemptStatus.TECHNICAL_ERROR


def _extract_error_shape(body: bytes) -> tuple[str | None, str | None]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    if not isinstance(payload, Mapping):
        return None, None
    candidate = payload.get("error")
    if isinstance(candidate, Mapping):
        error_type = candidate.get("type") or candidate.get("error_type")
        error_code = candidate.get("code") or candidate.get("error_code")
    else:
        error_type = payload.get("type") or payload.get("error_type")
        error_code = payload.get("code") or payload.get("error_code")
    return (
        str(error_type)[:120] if error_type is not None else None,
        str(error_code)[:120] if error_code is not None else None,
    )


def _validate_queries(query: str | Sequence[str]) -> tuple[str, ...]:
    raw = (query,) if isinstance(query, str) else tuple(query)
    normalized = tuple(" ".join(str(item).split()) for item in raw if str(item).strip())
    if not normalized:
        raise ValueError("Perplexity Search API requires at least one query")
    if len(normalized) > MAX_QUERIES_PER_REQUEST:
        raise ValueError(
            f"Perplexity Search API accepts at most {MAX_QUERIES_PER_REQUEST} queries per request"
        )
    return normalized


def _validate_search_type(search_type: str) -> str:
    normalized = str(search_type or "web").strip().casefold()
    if normalized not in SUPPORTED_SEARCH_TYPES:
        raise ValueError("Perplexity search_type must be 'web' or 'fast'")
    return normalized


def _source_from_payload(position: int, raw: Mapping[str, Any]) -> PerplexitySource:
    url = str(raw.get("url") or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Perplexity result contains an invalid source URL")
    metadata = {
        str(key): value
        for key, value in raw.items()
        if key not in {"url", "title", "snippet", "date", "last_updated"}
    }
    return PerplexitySource(
        position=position,
        url=url,
        title=str(raw.get("title") or "").strip(),
        snippet=str(raw.get("snippet") or ""),
        source_date=(
            str(raw.get("date")).strip()
            if raw.get("date") is not None
            else None
        ),
        last_updated=(
            str(raw.get("last_updated")).strip()
            if raw.get("last_updated") is not None
            else None
        ),
        metadata=metadata,
    )


def _parse_success_payload(
    body: bytes,
) -> tuple[str | None, tuple[PerplexitySource, ...]]:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Perplexity returned malformed JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Perplexity response root must be an object")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("Perplexity response is missing results[]")
    sources: list[PerplexitySource] = []
    for index, item in enumerate(raw_results, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("Perplexity results[] must contain objects")
        sources.append(_source_from_payload(index, item))
    provider_response_id = payload.get("id")
    return (
        str(provider_response_id)[:200] if provider_response_id is not None else None,
        tuple(sources),
    )


def perplexity_configuration_status(
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    environment = os.environ if env is None else env
    configured = bool(str(environment.get(API_KEY_ENV) or "").strip())
    return {
        "provider": PROVIDER,
        "surface": SURFACE,
        "configured": configured,
        "secret_env": API_KEY_ENV,
        "search_types": ("WEB", "FAST"),
        "provenance": PROVENANCE_KIND,
    }


class PerplexitySearchRepository:
    """Persist external Perplexity provenance separately from deterministic SERP tables."""

    def __init__(self, database: Path, *, audit_id: str) -> None:
        self.database = Path(database)
        self.audit_id = audit_id
        self.connection = sqlite3.connect(self.database)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def __enter__(self) -> "PerplexitySearchRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS perplexity_search_runs (
                    run_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    attempt_id TEXT REFERENCES ai_provider_attempts(attempt_id) ON DELETE SET NULL,
                    provider TEXT NOT NULL,
                    surface TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    query_json TEXT NOT NULL,
                    search_type TEXT NOT NULL,
                    provenance_kind TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider_response_id TEXT,
                    http_status INTEGER,
                    error_class TEXT,
                    error_type TEXT,
                    error_code TEXT,
                    retry_after_seconds REAL,
                    request_payload_hash TEXT NOT NULL,
                    citation_urls_json TEXT NOT NULL,
                    native_usage_unit TEXT,
                    native_usage_quantity REAL,
                    billable INTEGER,
                    estimated_cost REAL,
                    cost_currency TEXT,
                    pricing_version TEXT,
                    pricing_context TEXT,
                    pricing_rule_id TEXT,
                    pricing_source_reference TEXT,
                    pricing_runtime_conditions TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS perplexity_search_sources (
                    run_id TEXT NOT NULL REFERENCES perplexity_search_runs(run_id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    source_date TEXT,
                    last_updated TEXT,
                    source_metadata_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(run_id, position, url)
                );

                CREATE INDEX IF NOT EXISTS idx_perplexity_search_runs_audit_time
                    ON perplexity_search_runs(audit_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_perplexity_search_sources_run_position
                    ON perplexity_search_sources(run_id, position);
                """
            )

    def save(self, run: PerplexitySearchRun) -> None:
        component = run.native_usage[0] if run.native_usage else None
        diagnostic = run.diagnostic
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO perplexity_search_runs (
                    run_id,audit_id,attempt_id,provider,surface,purpose,query_json,search_type,
                    provenance_kind,started_at,finished_at,status,provider_response_id,http_status,
                    error_class,error_type,error_code,retry_after_seconds,request_payload_hash,
                    citation_urls_json,native_usage_unit,native_usage_quantity,billable,
                    estimated_cost,cost_currency,pricing_version,pricing_context,pricing_rule_id,
                    pricing_source_reference,pricing_runtime_conditions,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run.run_id,
                    self.audit_id,
                    run.attempt_id,
                    PROVIDER,
                    SURFACE,
                    run.purpose,
                    json.dumps(run.queries, ensure_ascii=False),
                    run.search_type.upper(),
                    PROVENANCE_KIND,
                    run.started_at.isoformat(),
                    run.finished_at.isoformat(),
                    run.status,
                    run.provider_response_id,
                    run.http_status,
                    diagnostic.error_class.value if diagnostic and diagnostic.error_class else None,
                    diagnostic.error_type if diagnostic else None,
                    diagnostic.error_code if diagnostic else None,
                    diagnostic.retry_after_seconds if diagnostic else None,
                    run.request_payload_hash,
                    json.dumps(run.citation_urls, ensure_ascii=False),
                    component.unit if component else None,
                    component.quantity if component else None,
                    None if component is None or component.billable is None else int(component.billable),
                    run.pricing.estimated_cost,
                    run.pricing.currency,
                    run.pricing.pricing_version,
                    run.pricing.pricing_context,
                    run.pricing.pricing_rule_id,
                    run.pricing.pricing_source_reference,
                    json.dumps(dict(run.pricing.runtime_conditions), sort_keys=True),
                    _utc_now().isoformat(),
                ),
            )
            for source in run.sources:
                self.connection.execute(
                    """
                    INSERT INTO perplexity_search_sources (
                        run_id,position,url,title,snippet,source_date,last_updated,source_metadata_json
                    ) VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        run.run_id,
                        source.position,
                        source.url,
                        source.title,
                        source.snippet,
                        source.source_date,
                        source.last_updated,
                        json.dumps(source.metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )


def _persist_attempt(
    workspace: AuditWorkspace,
    run: PerplexitySearchRun,
) -> str | None:
    if not run.native_usage:
        return None
    attempt_id = _new_id("AIPX")
    attempt = ProviderAttempt(
        provider=PROVIDER,
        model=None,
        reasoning_profile="NONE",
        provider_rank=1,
        attempt_index=1,
        snapshot_id="",
        url="",
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_ms=max(
            int((run.finished_at - run.started_at).total_seconds() * 1000),
            0,
        ),
        status=_attempt_status(run.diagnostic),
        diagnostic=run.diagnostic,
        usage=ProviderUsage(native_usage=run.native_usage),
        estimated_cost=run.pricing.estimated_cost,
        cost_currency=run.pricing.currency,
        pricing_version=run.pricing.pricing_version,
        pricing_context=run.pricing.pricing_context,
        pricing_rule_id=run.pricing.pricing_rule_id,
        pricing_source_reference=run.pricing.pricing_source_reference,
        pricing_runtime_conditions=run.pricing.runtime_conditions,
        surface=SURFACE,
        pricing_model=run.pricing.pricing_model,
        request_message_summary=(
            f"Perplexity Search API {run.search_type.upper()} "
            f"query_count={len(run.queries)}"
        ),
        request_payload_hash=run.request_payload_hash,
        semantic_contract_version=CONTRACT_VERSION,
    )
    with M18Persistence(workspace) as store:
        store.add_attempt(
            attempt_id=attempt_id,
            audit_id=run.audit_id,
            page_id=None,
            snapshot_id=None,
            url="",
            device=None,
            attempt=attempt,
            operation="SEARCH_INTELLIGENCE",
        )
    return attempt_id


def execute_perplexity_search(
    workspace: AuditWorkspace,
    *,
    audit_id: str,
    query: str | Sequence[str],
    purpose: str = "SEARCH_INTELLIGENCE",
    search_type: str = "web",
    max_results: int = 10,
    country: str | None = None,
    search_language_filter: Sequence[str] = (),
    timeout_seconds: float = 15.0,
    env: Mapping[str, str] | None = None,
    transport: PerplexityTransport | None = None,
) -> PerplexitySearchRun:
    """Execute one external Perplexity Search API request and persist isolated provenance.

    Pricing uses one PERPLEXITY_SEARCH_REQUEST component per HTTP request. Query count is
    deliberately not used as the billing quantity because Perplexity bills successful
    POST /search requests while rate limiting counts query units separately.
    """

    queries = _validate_queries(query)
    normalized_type = _validate_search_type(search_type)
    if max_results <= 0:
        raise ValueError("Perplexity max_results must be > 0")
    if not timeout_seconds or float(timeout_seconds) <= 0:
        raise ValueError("Perplexity timeout_seconds must be > 0")

    environment = os.environ if env is None else env
    api_key = str(environment.get(API_KEY_ENV) or "").strip()

    payload: dict[str, Any] = {
        "query": queries[0] if len(queries) == 1 else list(queries),
        "max_results": int(max_results),
        "search_type": normalized_type,
    }
    if country:
        normalized_country = str(country).strip().upper()
        if len(normalized_country) != 2 or not normalized_country.isalpha():
            raise ValueError("Perplexity country must be ISO 3166-1 alpha-2")
        payload["country"] = normalized_country
    languages = tuple(
        str(item).strip().casefold()
        for item in search_language_filter
        if str(item).strip()
    )
    if languages:
        if any(len(item) != 2 or not item.isalpha() for item in languages):
            raise ValueError("Perplexity search_language_filter must use ISO 639-1 codes")
        payload["search_language_filter"] = list(languages)

    body = _json_bytes(payload)
    request_hash = _payload_hash(body)
    started_at = _utc_now()
    runtime_conditions = {
        "search_type": normalized_type.upper(),
        "operation_mode": "REALTIME",
    }

    if not api_key:
        finished_at = _utc_now()
        run = PerplexitySearchRun(
            run_id=_new_id("PXSR"),
            audit_id=audit_id,
            queries=queries,
            purpose=str(purpose or "SEARCH_INTELLIGENCE"),
            search_type=normalized_type,
            started_at=started_at,
            finished_at=finished_at,
            status="NOT_CONFIGURED",
            provider_response_id=None,
            http_status=None,
            diagnostic=None,
            sources=(),
            request_payload_hash=request_hash,
            native_usage=(),
            pricing=PricingApplication(
                None,
                None,
                "",
                pricing_context="NOT_CONFIGURED",
                runtime_conditions=tuple(sorted(runtime_conditions.items())),
                pricing_model="PER_REQUEST",
                native_usage_unit=PERPLEXITY_SEARCH_REQUEST,
                native_usage_quantity=0.0,
            ),
            attempt_id=None,
        )
        with PerplexitySearchRepository(workspace.database, audit_id=audit_id) as repository:
            repository.save(run)
        return run

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "RASAi-Search-Intelligence/1",
    }
    effective_transport = transport or _default_transport

    diagnostic: ProviderDiagnostic | None = None
    provider_response_id: str | None = None
    sources: tuple[PerplexitySource, ...] = ()
    http_status: int | None = None
    billable: bool | None = None
    status = "ERROR"

    try:
        response = effective_transport(
            ENDPOINT,
            headers,
            body,
            float(timeout_seconds),
        )
        http_status = int(response.status)
        request_id = (
            _headers_get(response.headers, "x-request-id")
            or _headers_get(response.headers, "request-id")
        )
        if 200 <= http_status < 300:
            billable = True
            try:
                provider_response_id, sources = _parse_success_payload(response.body)
                status = "SUCCESS"
            except ValueError:
                diagnostic = ProviderDiagnostic(
                    error_class=ProviderErrorClass.INVALID_RESPONSE,
                    http_status=http_status,
                    request_id=request_id,
                )
                status = "INVALID_RESPONSE"
        else:
            billable = False
            error_type, error_code = _extract_error_shape(response.body)
            error_class = _http_error_class(http_status)
            diagnostic = ProviderDiagnostic(
                error_class=error_class,
                http_status=http_status,
                error_type=error_type,
                error_code=error_code,
                request_id=request_id,
                retry_after_seconds=_retry_after(response.headers),
            )
            status = error_class.value
    except PerplexityTimeoutError:
        diagnostic = ProviderDiagnostic(error_class=ProviderErrorClass.TIMEOUT_ERROR)
        status = ProviderErrorClass.TIMEOUT_ERROR.value
        billable = None
    except PerplexityNetworkError:
        diagnostic = ProviderDiagnostic(error_class=ProviderErrorClass.NETWORK_ERROR)
        status = ProviderErrorClass.NETWORK_ERROR.value
        billable = None

    finished_at = _utc_now()
    native_usage = (
        NativeUsageComponent(
            unit=PERPLEXITY_SEARCH_REQUEST,
            quantity=1.0,
            source_metric="perplexity.search.request",
            component_type="REQUEST",
            billable=billable,
            observed_at=finished_at,
        ),
    )
    pricing = resolve_native_usage_cost(
        PROVIDER,
        SURFACE,
        native_usage,
        finished_at,
        runtime_conditions=runtime_conditions,
    )

    transient_run = PerplexitySearchRun(
        run_id=_new_id("PXSR"),
        audit_id=audit_id,
        queries=queries,
        purpose=str(purpose or "SEARCH_INTELLIGENCE"),
        search_type=normalized_type,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        provider_response_id=provider_response_id,
        http_status=http_status,
        diagnostic=diagnostic,
        sources=sources,
        request_payload_hash=request_hash,
        native_usage=native_usage,
        pricing=pricing,
    )
    attempt_id = _persist_attempt(workspace, transient_run)
    run = PerplexitySearchRun(
        run_id=transient_run.run_id,
        audit_id=transient_run.audit_id,
        queries=transient_run.queries,
        purpose=transient_run.purpose,
        search_type=transient_run.search_type,
        started_at=transient_run.started_at,
        finished_at=transient_run.finished_at,
        status=transient_run.status,
        provider_response_id=transient_run.provider_response_id,
        http_status=transient_run.http_status,
        diagnostic=transient_run.diagnostic,
        sources=transient_run.sources,
        request_payload_hash=transient_run.request_payload_hash,
        native_usage=transient_run.native_usage,
        pricing=transient_run.pricing,
        attempt_id=attempt_id,
    )
    with PerplexitySearchRepository(workspace.database, audit_id=audit_id) as repository:
        repository.save(run)
    return run


def humanized_perplexity_summary(run: PerplexitySearchRun) -> dict[str, Any]:
    """Return report/console-safe labels without exposing internal enums or secrets."""

    mode_label = "Busca rápida" if run.search_type == "fast" else "Busca web"
    if run.pricing.estimated_cost is None:
        cost_label = "UNPRICED"
    else:
        currency = run.pricing.currency or "USD"
        cost_label = f"{currency} {run.pricing.estimated_cost:.6f}"
    return {
        "origem": "Perplexity Search API - pesquisa externa",
        "provenance": "Pesquisa externa; não é evidência determinística RASAi",
        "modo": mode_label,
        "consultas": len(run.queries),
        "requests": sum(item.quantity for item in run.native_usage),
        "fontes": len(run.sources),
        "custo": cost_label,
        "status": run.status,
    }
