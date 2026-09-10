"""Audit logging for external AI request/response envelopes.

The log is deliberately separate from scoring evidence. It captures the request body
passed to the provider transport and the response envelope returned by the adapter,
while never recording credential headers. Content-context interpretations produced
for AUTO editorial fields are extracted transiently and redacted from database
persistence so they can be rendered without becoming canonical audit data.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
import sqlite3
import time
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from rasai.persistence import AuditWorkspace

MAX_CAPTURE_BYTES_ENV = "RASAI_AI_EXCHANGE_LOG_MAX_BYTES"
DEFAULT_MAX_CAPTURE_BYTES = 512 * 1024
_CONTEXT_KEY = "content_context_interpretation"
_CONTEXT_REDACTION = "[INTERPRETACAO_AUTO_EXIBIDA_NO_RELATORIO_NAO_PERSISTIDA]"
_PRIVATE_REASONING_KEYS = frozenset({
    "chain_of_thought",
    "chain-of-thought",
    "internal_reasoning",
    "reasoning_content",
    "thinking",
    "thoughts",
})
_SECRET_KEYS = frozenset({
    "api_key",
    "apikey",
    "key",
    "authorization",
    "password",
    "access_token",
    "refresh_token",
    "client_secret",
    "bearer",
})
_PURPOSE_MARKERS = (
    ("rasai_m24_technical_remediation", "TECHNICAL_REMEDIATION"),
    ("rasai_content_remediation", "CONTENT_REMEDIATION"),
    ("rasai_source_quality", "SOURCE_QUALITY_EXPLANATION"),
    ("rasai_semantic_assessment", "SEMANTIC_ANALYSIS"),
)
_METADATA_PATTERN = {
    "snapshot_id": re.compile(r'"snapshot_id"\s*:\s*"([^"]+)"'),
    "page_url": re.compile(r'"page_url"\s*:\s*"([^"]+)"'),
}


@dataclass(frozen=True, slots=True)
class AiExchange:
    exchange_id: str
    sequence_no: int
    provider: str
    model: str | None
    purpose: str
    snapshot_id: str | None
    page_url: str | None
    endpoint: str
    started_at: str
    finished_at: str
    duration_ms: int
    outcome: str
    http_status: int | None
    exception_type: str | None
    request_payload: str
    request_sha256: str
    request_truncated: bool
    response_payload: str | None
    response_sha256: str | None
    response_truncated: bool


@dataclass(frozen=True, slots=True)
class ContextInterpretationRecord:
    sequence_no: int
    provider: str
    model: str | None
    snapshot_id: str | None
    page_url: str | None
    fields: Mapping[str, Mapping[str, Any]]


class AiExchangeRecorder:
    """In-memory execution recorder shared by every provider in one AI session."""

    def __init__(self, *, max_capture_bytes: int | None = None) -> None:
        configured = max_capture_bytes
        if configured is None:
            try:
                configured = int(os.environ.get(MAX_CAPTURE_BYTES_ENV, DEFAULT_MAX_CAPTURE_BYTES))
            except (TypeError, ValueError):
                configured = DEFAULT_MAX_CAPTURE_BYTES
        self.max_capture_bytes = max(4096, min(int(configured), 4 * 1024 * 1024))
        self._exchanges: list[AiExchange] = []
        self._interpretations: list[ContextInterpretationRecord] = []

    @property
    def exchanges(self) -> tuple[AiExchange, ...]:
        return tuple(self._exchanges)

    @property
    def context_interpretations(self) -> tuple[ContextInterpretationRecord, ...]:
        return tuple(self._interpretations)

    def append_exchange(
        self,
        *,
        provider: str,
        model: str | None,
        endpoint: str,
        body: bytes,
        started_at: datetime,
        duration_ms: int,
        outcome: str,
        response: Any = None,
        http_status: int | None = None,
        exception_type: str | None = None,
        raw_http_error_body: bytes | None = None,
    ) -> None:
        request_text = body.decode("utf-8", errors="replace")
        request_for_log = _sanitize_request_text(request_text)
        request_payload, request_sha, request_truncated = _bounded(
            request_for_log, self.max_capture_bytes
        )
        purpose, snapshot_id, page_url = _request_metadata(request_text)

        interpretation = _extract_context_interpretation(response)
        if interpretation is not None:
            normalized = _normalize_context_interpretation(
                interpretation,
                allowed_evidence_ids=_evidence_ids_from_request(request_text),
            )
            if normalized is not None:
                self._interpretations.append(
                    ContextInterpretationRecord(
                        sequence_no=len(self._exchanges) + 1,
                        provider=provider,
                        model=model,
                        snapshot_id=snapshot_id,
                        page_url=page_url,
                        fields=normalized,
                    )
                )

        response_text: str | None
        if raw_http_error_body is not None:
            response_text = raw_http_error_body.decode("utf-8", errors="replace")
            response_text = _sanitize_response_text(response_text)
        elif response is None:
            response_text = None
        else:
            response_text = _serialize_response_for_log(response)

        response_payload = response_sha = None
        response_truncated = False
        if response_text is not None:
            response_payload, response_sha, response_truncated = _bounded(
                response_text, self.max_capture_bytes
            )

        finished_at = datetime.now(timezone.utc)
        self._exchanges.append(
            AiExchange(
                exchange_id=f"AIX-{uuid4().hex.upper()}",
                sequence_no=len(self._exchanges) + 1,
                provider=provider,
                model=model,
                purpose=purpose,
                snapshot_id=snapshot_id,
                page_url=page_url,
                endpoint=_sanitize_endpoint(endpoint),
                started_at=started_at.isoformat(),
                finished_at=finished_at.isoformat(),
                duration_ms=max(0, int(duration_ms)),
                outcome=outcome,
                http_status=http_status,
                exception_type=exception_type,
                request_payload=request_payload,
                request_sha256=request_sha,
                request_truncated=request_truncated,
                response_payload=response_payload,
                response_sha256=response_sha,
                response_truncated=response_truncated,
            )
        )


def instrument_provider_transport(provider: Any, recorder: AiExchangeRecorder) -> None:
    """Wrap a provider transport exactly once, sharing the supplied recorder."""
    if getattr(provider, "_rasai_exchange_instrumented", False):
        provider._rasai_exchange_recorder = recorder
        return
    original = getattr(provider, "_transport", None)
    if not callable(original):
        return

    provider._rasai_exchange_instrumented = True
    provider._rasai_exchange_recorder = recorder

    def traced(url: str, headers: dict[str, str], body: bytes, timeout: float):
        started_at = datetime.now(timezone.utc)
        started_perf = time.perf_counter()
        try:
            # Headers are forwarded but never copied into recorder state.
            raw = original(url, headers, body, timeout)
        except HTTPError as exc:
            try:
                error_body = exc.read(recorder.max_capture_bytes * 2)
            except Exception:
                error_body = b""
            recorder.append_exchange(
                provider=str(getattr(provider, "name", "UNKNOWN")),
                model=getattr(provider, "model", None),
                endpoint=url,
                body=body,
                started_at=started_at,
                duration_ms=int((time.perf_counter() - started_perf) * 1000),
                outcome="HTTP_ERROR",
                http_status=int(exc.code),
                exception_type=type(exc).__name__,
                raw_http_error_body=error_body,
            )
            raise HTTPError(exc.url, exc.code, exc.msg, exc.headers, io.BytesIO(error_body)) from exc
        except Exception as exc:
            recorder.append_exchange(
                provider=str(getattr(provider, "name", "UNKNOWN")),
                model=getattr(provider, "model", None),
                endpoint=url,
                body=body,
                started_at=started_at,
                duration_ms=int((time.perf_counter() - started_perf) * 1000),
                outcome="EXCEPTION",
                exception_type=type(exc).__name__,
            )
            raise

        recorder.append_exchange(
            provider=str(getattr(provider, "name", "UNKNOWN")),
            model=getattr(provider, "model", None),
            endpoint=url,
            body=body,
            started_at=started_at,
            duration_ms=int((time.perf_counter() - started_perf) * 1000),
            outcome="RESPONSE",
            response=raw,
        )
        return _strip_transient_context_interpretation(raw)

    provider._transport = traced


def _bounded(text: str, max_bytes: int) -> tuple[str, str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    digest = hashlib.sha256(encoded).hexdigest()
    if len(encoded) <= max_bytes:
        return text, digest, False
    clipped = encoded[:max_bytes].decode("utf-8", errors="replace")
    return clipped + "\n[TRUNCADO PELO RASAI]", digest, True


def _sanitize_endpoint(url: str) -> str:
    try:
        parsed = urlsplit(url)
        query = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            query.append((key, "[REDACTED]" if key.casefold() in _SECRET_KEYS else value))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    except Exception:
        return str(url)


def _sanitize_tree(value: Any, *, redact_context: bool) -> Any:
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            token = str(key).casefold()
            if token in _SECRET_KEYS:
                output[str(key)] = "[REDACTED]"
            elif token in _PRIVATE_REASONING_KEYS:
                output[str(key)] = "[PRIVATE_REASONING_NOT_PERSISTED]"
            elif redact_context and token == _CONTEXT_KEY:
                output[str(key)] = _CONTEXT_REDACTION
            else:
                output[str(key)] = _sanitize_tree(item, redact_context=redact_context)
        return output
    if isinstance(value, list):
        return [_sanitize_tree(item, redact_context=redact_context) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_tree(item, redact_context=redact_context) for item in value]
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0:1] in {"{", "["}:
            try:
                decoded = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                return value
            sanitized = _sanitize_tree(decoded, redact_context=redact_context)
            return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    return value


def _sanitize_request_text(text: str) -> str:
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text
    return json.dumps(
        _sanitize_tree(decoded, redact_context=False),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _sanitize_response_text(text: str) -> str:
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return text
    return json.dumps(
        _sanitize_tree(decoded, redact_context=True),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _serialize_response_for_log(raw: Any) -> str:
    sanitized = _sanitize_tree(deepcopy(raw), redact_context=True)
    try:
        return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(sanitized)


def _request_metadata(text: str) -> tuple[str, str | None, str | None]:
    lower = text.casefold()
    purpose = "AI_REQUEST"
    for marker, label in _PURPOSE_MARKERS:
        if marker in lower:
            purpose = label
            break
    if purpose == "AI_REQUEST":
        if "website content remediation assistant" in lower:
            purpose = "CONTENT_REMEDIATION"
        elif "crawling, robots.txt, sitemap" in lower:
            purpose = "TECHNICAL_REMEDIATION"
        elif "search & ai readiness" in lower and "semantic" in lower:
            purpose = "SEMANTIC_ANALYSIS"

    snapshot_id = page_url = None
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = text

    def walk(value: Any) -> None:
        nonlocal snapshot_id, page_url
        if isinstance(value, Mapping):
            if snapshot_id is None and value.get("snapshot_id"):
                snapshot_id = str(value.get("snapshot_id"))
            if page_url is None and value.get("page_url"):
                page_url = str(value.get("page_url"))
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            for name, pattern in _METADATA_PATTERN.items():
                match = pattern.search(value)
                if match:
                    if name == "snapshot_id" and snapshot_id is None:
                        snapshot_id = match.group(1)
                    elif name == "page_url" and page_url is None:
                        page_url = match.group(1)
            if "{" in value:
                candidate = value[value.find("{") :]
                try:
                    walk(json.loads(candidate))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass

    walk(decoded)
    return purpose, snapshot_id, page_url


def _evidence_ids_from_request(text: str) -> frozenset[str]:
    values: set[str] = set()
    pattern = re.compile(r'"evidence_id"\s*:\s*"([^"]+)"')
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        decoded = text

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            evidence_id = value.get("evidence_id")
            if evidence_id:
                values.add(str(evidence_id))
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            values.update(match.group(1) for match in pattern.finditer(value))
            if "{" in value:
                try:
                    walk(json.loads(value[value.find("{") :]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass

    walk(decoded)
    return frozenset(values)


def _extract_context_interpretation(raw: Any) -> Any | None:
    found: list[Any] = []

    def walk(value: Any) -> None:
        if found:
            return
        if isinstance(value, Mapping):
            if _CONTEXT_KEY in value:
                found.append(value[_CONTEXT_KEY])
                return
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{"):
                try:
                    walk(json.loads(stripped))
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass

    walk(raw)
    return found[0] if found else None


_CONTEXT_VALUES: dict[str, frozenset[str]] = {
    "risk_profile": frozenset({"standard", "ymyl"}),
    "ymyl_category": frozenset({
        "none", "health-safety", "financial-security", "civic-societal",
        "other-significant-welfare",
    }),
    "page_purpose": frozenset({
        "informational", "transactional", "product-service", "review-comparison",
        "news-editorial", "support-documentation", "forum-ugc", "other",
    }),
    "intended_audience": frozenset({"general", "professional", "mixed"}),
    "experience_requirement": frozenset({"required", "beneficial", "not-expected"}),
    "freshness_sensitivity": frozenset({"low", "medium", "high"}),
    "content_origin": frozenset({"first-party", "third-party", "user-generated", "mixed"}),
}


def _normalize_context_interpretation(
    raw: Any,
    *,
    allowed_evidence_ids: frozenset[str],
) -> dict[str, dict[str, Any]] | None:
    if not isinstance(raw, Mapping):
        return None
    output: dict[str, dict[str, Any]] = {}
    for field, allowed_values in _CONTEXT_VALUES.items():
        item = raw.get(field)
        if not isinstance(item, Mapping):
            return None
        status = str(item.get("status") or "").strip().upper()
        if status not in {"INTERPRETED", "NOT_DETERMINABLE", "NOT_REQUESTED"}:
            return None
        raw_value = item.get("value")
        value = None if raw_value is None else str(raw_value).strip().casefold()
        if status == "INTERPRETED" and value not in allowed_values:
            return None
        if status != "INTERPRETED" and value not in {None, ""}:
            return None
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            return None
        if not 0.0 <= confidence <= 1.0:
            return None
        rationale = str(item.get("rationale") or "").strip()
        evidence_raw = item.get("evidence_ids")
        if not isinstance(evidence_raw, list):
            return None
        evidence_ids = tuple(str(value).strip() for value in evidence_raw if str(value).strip())
        if not set(evidence_ids).issubset(allowed_evidence_ids):
            return None
        output[field] = {
            "status": status,
            "value": value or None,
            "confidence": confidence,
            "rationale": rationale[:1200],
            "evidence_ids": evidence_ids,
        }
    return output


def _strip_transient_context_interpretation(raw: Any) -> Any:
    """Return a copy consumable by legacy normalizers, removing only transient context."""
    found = False

    def walk(value: Any) -> Any:
        nonlocal found
        if isinstance(value, Mapping):
            output: dict[str, Any] = {}
            for key, item in value.items():
                if str(key).casefold() == _CONTEXT_KEY:
                    found = True
                    continue
                output[str(key)] = walk(item)
            return output
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, tuple):
            return [walk(item) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{"):
                try:
                    decoded = json.loads(stripped)
                except (TypeError, ValueError, json.JSONDecodeError):
                    return value
                transformed = walk(decoded)
                if found:
                    return json.dumps(transformed, ensure_ascii=False, separators=(",", ":"))
            return value
        return value

    transformed = walk(deepcopy(raw))
    return transformed if found else raw


def persist_ai_exchange_log(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    recorder: AiExchangeRecorder | None,
) -> int:
    """Persist sanitized external exchanges. AUTO context interpretations stay in memory only."""
    if recorder is None:
        return 0
    connection = sqlite3.connect(workspace.database)
    try:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_exchange_log (
                    exchange_id TEXT PRIMARY KEY,
                    audit_id TEXT NOT NULL REFERENCES audits(audit_id) ON DELETE CASCADE,
                    sequence_no INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT,
                    purpose TEXT NOT NULL,
                    snapshot_id TEXT,
                    page_url TEXT,
                    endpoint TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    outcome TEXT NOT NULL,
                    http_status INTEGER,
                    exception_type TEXT,
                    request_payload TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    request_truncated INTEGER NOT NULL,
                    response_payload TEXT,
                    response_sha256 TEXT,
                    response_truncated INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ai_exchange_audit
                    ON ai_exchange_log(audit_id,sequence_no);
                CREATE INDEX IF NOT EXISTS idx_ai_exchange_provider
                    ON ai_exchange_log(audit_id,provider,purpose);
                """
            )
            count = 0
            for item in recorder.exchanges:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO ai_exchange_log (
                        exchange_id,audit_id,sequence_no,provider,model,purpose,
                        snapshot_id,page_url,endpoint,started_at,finished_at,duration_ms,
                        outcome,http_status,exception_type,request_payload,request_sha256,
                        request_truncated,response_payload,response_sha256,response_truncated
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        item.exchange_id, audit_id, item.sequence_no, item.provider, item.model,
                        item.purpose, item.snapshot_id, item.page_url, item.endpoint,
                        item.started_at, item.finished_at, item.duration_ms, item.outcome,
                        item.http_status, item.exception_type, item.request_payload,
                        item.request_sha256, 1 if item.request_truncated else 0,
                        item.response_payload, item.response_sha256,
                        1 if item.response_truncated else 0,
                    ),
                )
                count += max(0, int(cursor.rowcount))
        return count
    finally:
        connection.close()
