"""Optional evidence-bound AI explanation for deterministic source-quality diagnostics.

The AI layer never decides whether TLS/DNS/redirect transport is valid. It receives
only persisted deterministic facts and may add a human-readable explanation/remediation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from searchgeo.domain import new_id
from searchgeo.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderState,
    ResponsesSemanticProvider,
    _diagnostic_from_http,
    _response_error,
    _usage_from_native,
    estimate_cost,
)
from searchgeo.m18_persistence import M18Persistence
from searchgeo.persistence import AuditWorkspace
from searchgeo.semantic import _extract_json_payload

from searchgeo.source_quality import (
    SOURCE_QUALITY_AI_ARTIFACT,
    SourceQualityAssessment,
)


CONTRACT_VERSION = "SOURCE-QUALITY-AI-v1"


@dataclass(frozen=True, slots=True)
class SourceQualityAiResult:
    state: ProviderState
    provider: str | None = None
    model: str | None = None
    explanation: dict[str, Any] | None = None
    reason: str | None = None


def maybe_explain_source_quality(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    provider: Any,
    assessment: SourceQualityAssessment,
) -> SourceQualityAiResult:
    """Use at most one successful Responses-compatible provider for explanation.

    Unsupported extension-provider wire formats fail open to deterministic diagnostics.
    AUTO may try the next built-in provider when a configured provider is unavailable.
    """
    candidates = _candidates(provider)
    if not candidates:
        result = SourceQualityAiResult(
            state=ProviderState.NOT_CONFIGURED,
            reason="AI_NOT_CONFIGURED_OR_UNSUPPORTED_FOR_SOURCE_QUALITY",
        )
        _persist_artifact(workspace, result)
        return result

    page_row = _first_snapshot(workspace, audit_id)
    if page_row is None:
        result = SourceQualityAiResult(
            state=ProviderState.UNAVAILABLE,
            reason="SOURCE_QUALITY_AI_NO_SNAPSHOT",
        )
        _persist_artifact(workspace, result)
        return result

    last: SourceQualityAiResult | None = None
    for attempt_index, candidate in enumerate(candidates, 1):
        result, attempt = _call(candidate, assessment, page_row, attempt_index=attempt_index)
        _persist_attempt(
            workspace=workspace,
            audit_id=audit_id,
            page_row=page_row,
            attempt=attempt,
        )
        last = result
        if result.state is ProviderState.AVAILABLE:
            _persist_artifact(workspace, result)
            return result
        if result.state is ProviderState.NOT_CONFIGURED:
            continue

    final = last or SourceQualityAiResult(
        state=ProviderState.UNAVAILABLE,
        reason="SOURCE_QUALITY_AI_UNAVAILABLE",
    )
    _persist_artifact(workspace, final)
    return final


def _candidates(provider: Any) -> tuple[ResponsesSemanticProvider, ...]:
    routed = getattr(provider, "providers", None)
    if isinstance(routed, tuple):
        return tuple(
            item
            for item in routed
            if isinstance(item, ResponsesSemanticProvider)
            and bool(getattr(item, "api_key", None))
        )
    if isinstance(provider, ResponsesSemanticProvider) and bool(getattr(provider, "api_key", None)):
        return (provider,)
    return ()


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_pt": {"type": "string", "minLength": 1, "maxLength": 1800},
            "likely_root_cause_pt": {"type": "string", "minLength": 1, "maxLength": 1800},
            "redirect_assessment_pt": {"type": "string", "minLength": 1, "maxLength": 1800},
            "recommended_actions_pt": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string", "minLength": 1, "maxLength": 1000},
            },
            "human_validation_required": {"type": "boolean"},
        },
        "required": [
            "summary_pt",
            "likely_root_cause_pt",
            "redirect_assessment_pt",
            "recommended_actions_pt",
            "human_validation_required",
        ],
    }


def _call(
    candidate: ResponsesSemanticProvider,
    assessment: SourceQualityAssessment,
    page_row: Mapping[str, Any],
    *,
    attempt_index: int,
) -> tuple[SourceQualityAiResult, ProviderAttempt]:
    schema = _schema()
    instructions = (
        "Você é um analista técnico de infraestrutura web. Responda em português do Brasil e somente em JSON. "
        "Use exclusivamente os fatos fornecidos. A classificação técnica determinística do SearchGEO é soberana: "
        "não transforme erro TLS/DNS/protocolo em comportamento normal e nunca recomende desabilitar validação TLS. "
        "Explique a causa provável, a cadeia de redirecionamentos e ações de correção para um analista humano. "
        "Um redirecionamento HTTP bem-sucedido pode ser intencional; quando a intenção de negócio não estiver nas "
        "evidências, marque que requer validação humana. Não invente detalhes do certificado, CDN, proxy ou servidor."
    )
    if candidate.structured_mode == "json_object":
        instructions += "\nSchema local obrigatório:\n" + json.dumps(
            schema, ensure_ascii=False, separators=(",", ":")
        )
        fmt: dict[str, Any] = {"type": "json_object"}
    else:
        fmt = {
            "type": "json_schema",
            "name": "searchgeo_source_quality",
            "schema": schema,
        }
        if candidate.name == "OPENAI":
            fmt["strict"] = True

    facts = {
        "deterministic_contract": "SOURCE-QUALITY-1",
        "all_pages_hard_blocked": assessment.all_pages_hard_blocked,
        "hard_blocker_kinds": list(assessment.hard_blocker_kinds),
        "issues": [item.as_dict() for item in assessment.issues],
    }
    payload = {
        "model": candidate.model,
        "instructions": instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Evidências técnicas persistidas:\n"
                        + json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
                    }
                ],
            }
        ],
        "reasoning": {"effort": candidate.requested_reasoning_effort.casefold()},
        "text": {"format": fmt},
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_hash = hashlib.sha256(body).hexdigest()
    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    usage = None
    diagnostic = None
    status = AttemptStatus.SUCCESS
    explanation = None
    reason = None
    try:
        raw = candidate._transport(candidate.endpoint, candidate._headers(), body, candidate.timeout)
        if not isinstance(raw, Mapping):
            raise ValueError("provider envelope is not an object")
        usage = _usage_from_native(raw)
        native_error = _response_error(raw)
        if native_error is not None:
            diagnostic = native_error
            status = AttemptStatus.TECHNICAL_ERROR
            reason = native_error.reason
        else:
            explanation = _validate_explanation(_extract_json_payload(dict(raw)))
    except HTTPError as exc:
        diagnostic = _diagnostic_from_http(exc)
        status = AttemptStatus.TECHNICAL_ERROR
        reason = diagnostic.reason
    except TimeoutError:
        diagnostic = ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR)
        status = AttemptStatus.TECHNICAL_ERROR
        reason = diagnostic.reason
    except (URLError, OSError):
        diagnostic = ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR)
        status = AttemptStatus.TECHNICAL_ERROR
        reason = diagnostic.reason
    except Exception as exc:
        diagnostic = ProviderDiagnostic(
            ProviderErrorClass.CONTRACT_ERROR,
            error_type=type(exc).__name__,
        )
        status = AttemptStatus.CONTRACT_ERROR
        reason = diagnostic.reason

    finished_at = datetime.now(timezone.utc)
    duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
    estimated, currency, pricing_version = estimate_cost(
        candidate.name,
        candidate.model,
        usage,
        finished_at,
    )
    attempt = ProviderAttempt(
        provider=candidate.name,
        model=candidate.model,
        reasoning_profile=candidate.reasoning_profile,
        provider_rank=candidate.policy.rank,
        attempt_index=attempt_index,
        snapshot_id=str(page_row["snapshot_id"]),
        url=str(page_row["url"]),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        status=status,
        diagnostic=diagnostic,
        usage=usage,
        estimated_cost=estimated,
        cost_currency=currency,
        pricing_version=pricing_version,
        request_message_summary=(
            f"contract={CONTRACT_VERSION};issues={len(assessment.issues)};"
            f"hard_blocked={assessment.all_pages_hard_blocked}"
        ),
        request_payload_hash=payload_hash,
        provider_qualification=candidate.policy.qualification,
        provider_reliability_score=candidate.policy.reliability_score,
        semantic_contract_version=CONTRACT_VERSION,
    )
    if status is AttemptStatus.SUCCESS and explanation is not None:
        return (
            SourceQualityAiResult(
                state=ProviderState.AVAILABLE,
                provider=candidate.name,
                model=candidate.model,
                explanation=explanation,
            ),
            attempt,
        )
    return (
        SourceQualityAiResult(
            state=ProviderState.UNAVAILABLE,
            provider=candidate.name,
            model=candidate.model,
            reason=reason or "SOURCE_QUALITY_AI_UNAVAILABLE",
        ),
        attempt,
    )


def _validate_explanation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("source-quality AI root must be an object")
    required = (
        "summary_pt",
        "likely_root_cause_pt",
        "redirect_assessment_pt",
        "recommended_actions_pt",
        "human_validation_required",
    )
    if any(key not in value for key in required):
        raise ValueError("source-quality AI response misses required fields")
    output: dict[str, Any] = {}
    for key in ("summary_pt", "likely_root_cause_pt", "redirect_assessment_pt"):
        text = str(value.get(key) or "").strip()
        if not text:
            raise ValueError(f"{key} must not be empty")
        output[key] = text[:1800]
    actions = value.get("recommended_actions_pt")
    if not isinstance(actions, list):
        raise ValueError("recommended_actions_pt must be an array")
    output["recommended_actions_pt"] = [
        str(item).strip()[:1000]
        for item in actions[:8]
        if str(item).strip()
    ]
    output["human_validation_required"] = bool(value.get("human_validation_required"))
    return output


def _first_snapshot(workspace: AuditWorkspace, audit_id: str) -> dict[str, Any] | None:
    import sqlite3

    try:
        connection = sqlite3.connect(
            f"file:{workspace.database.resolve().as_posix()}?mode=ro",
            uri=True,
            timeout=0.5,
        )
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                """SELECT ps.snapshot_id,ps.page_id,ps.device,
                          COALESCE(ps.final_url,p.normalized_url) AS url
                   FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
                   WHERE p.audit_id=? ORDER BY ps.captured_at LIMIT 1""",
                (audit_id,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return dict(row) if row is not None else None


def _persist_attempt(
    *,
    workspace: AuditWorkspace,
    audit_id: str,
    page_row: Mapping[str, Any],
    attempt: ProviderAttempt,
) -> None:
    with M18Persistence(workspace) as store:
        store.add_attempt(
            attempt_id=new_id("AIA"),
            audit_id=audit_id,
            page_id=str(page_row["page_id"]),
            snapshot_id=str(page_row["snapshot_id"]),
            url=str(page_row["url"]),
            device=str(page_row["device"]),
            attempt=attempt,
        )


def _persist_artifact(workspace: AuditWorkspace, result: SourceQualityAiResult) -> Path:
    path = workspace.root / SOURCE_QUALITY_AI_ARTIFACT
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "state": result.state.value,
        "provider": result.provider,
        "model": result.model,
        "reason": result.reason,
        "explanation": result.explanation,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
