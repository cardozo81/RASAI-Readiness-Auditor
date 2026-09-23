"""Optional evidence-bound AI remediation for M24 technical diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from rasai.domain import new_id
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ProviderState,
    ResponsesSemanticProvider,
    RuntimeProviderState,
    _diagnostic_from_http,
    _response_error,
    _usage_from_native,
    estimate_cost,
)
from rasai.m18_persistence import M18Persistence
from rasai.m24_crawling_discovery import M24Diagnostic, persist_ai_result
from rasai.persistence import AuditWorkspace
from rasai.provider_extensions import IsolatedStructuredSemanticProvider, gemini_wire_schema
from rasai.semantic import _extract_json_payload

CONTRACT_VERSION = "M24-TECHNICAL-REMEDIATION-v2"


@dataclass(frozen=True, slots=True)
class M24AiResult:
    state: ProviderState
    provider: str | None = None
    model: str | None = None
    explanation: dict[str, Any] | None = None
    reason: str | None = None


_RESOURCE_RULES: dict[str, tuple[str, ...]] = {
    "SITEMAP": ("BR-GEO-003",),
    "ROBOTS": ("BR-GEO-017", "BR-GEO-018"),
}


def _decode_json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list, tuple)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _resource_context_facts(
    workspace: AuditWorkspace,
    audit_id: str,
) -> tuple[list[dict[str, Any]], dict[str, frozenset[str]]]:
    """Build non-diagnostic resource facts from persisted scoring inputs.

    A clean/present robots.txt may produce no M24 problem diagnostic; that must not
    prevent an explicitly enabled technical-AI assessment from reviewing the same
    deterministic evidence. These facts are provider context only and are not new
    findings or score contributions by themselves.
    """
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = list(
            connection.execute(
                """SELECT rule_id,result,observed_value,evidence_ids
                   FROM rule_executions
                   WHERE audit_id=? AND rule_id IN ('BR-GEO-003','BR-GEO-017','BR-GEO-018')
                   ORDER BY rule_id,rule_execution_id""",
                (audit_id,),
            ).fetchall()
        )
    except sqlite3.OperationalError:
        rows = []
    finally:
        connection.close()

    facts: list[dict[str, Any]] = []
    resource_evidence: dict[str, frozenset[str]] = {}
    for resource, rule_ids in _RESOURCE_RULES.items():
        selected = [row for row in rows if str(row["rule_id"]) in rule_ids]
        evidence_ids: list[str] = []
        rule_states: list[dict[str, Any]] = []
        for row in selected:
            raw_ids = _decode_json_value(row["evidence_ids"], [])
            if isinstance(raw_ids, (list, tuple)):
                for evidence_id in raw_ids:
                    value = str(evidence_id).strip()
                    if value and value not in evidence_ids:
                        evidence_ids.append(value)
            rule_states.append(
                {
                    "rule_id": str(row["rule_id"]),
                    "result": str(row["result"]),
                    "observed": _decode_json_value(row["observed_value"], row["observed_value"]),
                }
            )
        if not rule_states or not evidence_ids:
            continue
        resource_evidence[resource] = frozenset(evidence_ids)
        facts.append(
            {
                "code": f"M24-RESOURCE-{resource}-BASELINE",
                "category": resource,
                "severity": "INFO",
                "title": f"Evidência determinística de {resource.lower()} para avaliação técnica bounded",
                "scope_url": None,
                "observed": {"rule_states": rule_states},
                "evidence_ids": evidence_ids,
                "deterministic_remediation": "Nenhuma conclusão adicional: avaliar somente a evidência fornecida.",
                "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
            }
        )
    return facts, resource_evidence


def maybe_remediate_m24(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    provider: Any,
    diagnostics: tuple[M24Diagnostic, ...],
) -> M24AiResult:
    """Explain deterministic M24 diagnostics without changing technical conclusions."""
    candidates = _candidates(provider)
    if not candidates:
        configured_state = _configured_provider_state(provider)
        if configured_state is not None:
            result = M24AiResult(
                state=ProviderState.UNAVAILABLE,
                reason=f"M24_AI_PROVIDER_{configured_state}",
            )
        else:
            result = M24AiResult(
                state=ProviderState.NOT_CONFIGURED,
                reason="AI_NOT_CONFIGURED_FOR_M24",
            )
        _persist_result(workspace, audit_id, result)
        return result

    page_row = _first_snapshot(workspace, audit_id)
    if page_row is None:
        result = M24AiResult(
            state=ProviderState.UNAVAILABLE,
            reason="M24_AI_NO_SNAPSHOT_CONTEXT",
        )
        _persist_result(workspace, audit_id, result)
        return result

    resource_facts, resource_evidence = _resource_context_facts(workspace, audit_id)
    allowed_codes = frozenset(
        [item.code for item in diagnostics]
        + [str(item["code"]) for item in resource_facts]
    )
    allowed_evidence_set = {
        evidence_id
        for item in diagnostics
        for evidence_id in item.evidence_ids
        if evidence_id
    }
    for values in resource_evidence.values():
        allowed_evidence_set.update(values)
    allowed_evidence = frozenset(allowed_evidence_set)
    facts = [
        {
            "code": item.code,
            "category": item.category,
            "severity": item.severity,
            "title": item.title,
            "scope_url": item.scope_url,
            "observed": item.observed,
            "evidence_ids": list(item.evidence_ids),
            "deterministic_remediation": item.remediation,
            "scoring_role": "BOUNDED_RESOURCE_ASSESSMENT_ELIGIBLE",
        }
        for item in diagnostics[:40]
    ]
    facts.extend(resource_facts)

    last: M24AiResult | None = None
    for attempt_index, candidate in enumerate(candidates, 1):
        result, attempt = _call(
            candidate,
            facts=facts,
            allowed_codes=allowed_codes,
            allowed_evidence=allowed_evidence,
            resource_evidence=resource_evidence,
            page_row=page_row,
            attempt_index=attempt_index,
        )
        _persist_attempt(
            workspace=workspace,
            audit_id=audit_id,
            page_row=page_row,
            attempt=attempt,
        )
        last = result
        if result.state is ProviderState.AVAILABLE:
            _persist_result(workspace, audit_id, result)
            return result

    final = last or M24AiResult(
        state=ProviderState.UNAVAILABLE,
        reason="M24_AI_UNAVAILABLE",
    )
    _persist_result(workspace, audit_id, final)
    return final


def _candidate_items(provider: Any) -> tuple[Any, ...]:
    routed = getattr(provider, "providers", None)
    if isinstance(routed, tuple):
        return tuple(routed)
    return (provider,) if provider is not None else ()


def _supported_candidate(candidate: Any) -> bool:
    return isinstance(candidate, (ResponsesSemanticProvider, IsolatedStructuredSemanticProvider))


def _configured_provider_state(provider: Any) -> str | None:
    configured = [
        item for item in _candidate_items(provider)
        if _supported_candidate(item) and bool(getattr(item, "api_key", None))
    ]
    if not configured:
        return None
    if any(getattr(item, "_runtime_state", RuntimeProviderState.ACTIVE) is RuntimeProviderState.QUARANTINED_FOR_AUDIT for item in configured):
        return "QUARANTINED_FOR_AUDIT"
    return "UNAVAILABLE"


def _candidates(provider: Any) -> tuple[Any, ...]:
    output: list[Any] = []
    for item in _candidate_items(provider):
        if not _supported_candidate(item):
            continue
        if not bool(getattr(item, "api_key", None)):
            continue
        state = getattr(item, "_runtime_state", RuntimeProviderState.ACTIVE)
        if state is RuntimeProviderState.QUARANTINED_FOR_AUDIT:
            continue
        output.append(item)
    return tuple(output)


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_pt": {"type": "string", "minLength": 1, "maxLength": 2000},
            "actions": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "diagnostic_code": {"type": "string", "minLength": 1},
                        "objective_pt": {"type": "string", "minLength": 1, "maxLength": 1200},
                        "recommended_change_pt": {"type": "string", "minLength": 1, "maxLength": 2500},
                        "evidence_ids": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "human_validation_required": {"type": "boolean"},
                    },
                    "required": [
                        "diagnostic_code",
                        "objective_pt",
                        "recommended_change_pt",
                        "evidence_ids",
                        "human_validation_required",
                    ],
                },
            },
            "resource_assessments": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "resource": {"type": "string", "enum": ["ROBOTS", "SITEMAP"]},
                        "verdict": {"type": "string", "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"]},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "evidence_ids": {
                            "type": "array",
                            "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                        "rationale_pt": {"type": "string", "minLength": 1, "maxLength": 1600},
                    },
                    "required": ["resource", "verdict", "confidence", "evidence_ids", "rationale_pt"],
                },
            },
            "policy_note_pt": {"type": "string", "minLength": 1, "maxLength": 1600},
        },
        "required": ["summary_pt", "actions", "resource_assessments", "policy_note_pt"],
    }


def _candidate_payload(candidate: Any, *, schema: dict[str, Any], instructions: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    facts_json = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
    name = str(getattr(candidate, "name", "")).upper()
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        if name == "GEMINI":
            return {
                "model": candidate.model,
                "input": instructions + "\n\nDiagnósticos técnicos persistidos:\n" + facts_json,
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": gemini_wire_schema(schema),
                },
            }
        if name == "QWEN":
            return {
                "model": candidate.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": "Diagnósticos técnicos persistidos:\n" + facts_json},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "rasai_m24_technical_remediation", "schema": schema, "strict": True},
                },
            }
        if name == "ANTHROPIC":
            return {
                "model": candidate.model,
                "max_tokens": 8192,
                "system": instructions,
                "messages": [{"role": "user", "content": "Diagnósticos técnicos persistidos:\n" + facts_json}],
                "output_config": {"format": {"type": "json_schema", "schema": schema}},
            }
        # XAI uses the Responses-style contract.
        return {
            "model": candidate.model,
            "instructions": instructions,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": "Diagnósticos técnicos persistidos:\n" + facts_json}]}],
            "reasoning": {"effort": str(getattr(candidate, "reasoning_profile", "HIGH")).casefold()},
            "text": {"format": {"type": "json_schema", "name": "rasai_m24_technical_remediation", "schema": schema, "strict": True}},
        }

    if candidate.structured_mode == "json_object":
        local_instructions = instructions + "\nSchema local obrigatório:\n" + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        fmt: dict[str, Any] = {"type": "json_object"}
    else:
        local_instructions = instructions
        fmt = {"type": "json_schema", "name": "rasai_m24_technical_remediation", "schema": schema}
        if candidate.name == "OPENAI":
            fmt["strict"] = True
    return {
        "model": candidate.model,
        "instructions": local_instructions,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Diagnósticos técnicos persistidos:\n" + facts_json}]}],
        "reasoning": {"effort": candidate.requested_reasoning_effort.casefold()},
        "text": {"format": fmt},
    }


def _candidate_usage(candidate: Any, raw: Mapping[str, Any]):
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        return candidate._usage(raw)
    return _usage_from_native(raw)


def _candidate_native_error(candidate: Any, raw: Mapping[str, Any]):
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        return candidate._native_error(raw)
    return _response_error(raw)


def _candidate_extract_payload(candidate: Any, raw: Mapping[str, Any]) -> Any:
    if isinstance(candidate, IsolatedStructuredSemanticProvider):
        return candidate._extract_payload(raw)
    return _extract_json_payload(dict(raw))


def _call(
    candidate: Any,
    *,
    facts: list[dict[str, Any]],
    allowed_codes: frozenset[str],
    allowed_evidence: frozenset[str],
    resource_evidence: Mapping[str, frozenset[str]],
    page_row: Mapping[str, Any],
    attempt_index: int,
) -> tuple[M24AiResult, ProviderAttempt]:
    schema = _schema()
    instructions = (
        "Você é um especialista técnico em crawling, robots.txt, sitemap e controles de crawlers. "
        "Responda em português do Brasil e somente em JSON. Use exclusivamente os diagnósticos "
        "determinísticos fornecidos. Não invente pesos numéricos nem altere a fórmula do SCORE-GEO-004/SARI-001. "
        "Além das ações, classifique ROBOTS e/ou SITEMAP somente quando houver evidência fornecida, "
        "usando POSITIVE, NEUTRAL ou NEGATIVE. O runtime converte essa classe por fatores estáticos/versionados. "
        "Não invente URL, status HTTP, configuração, crawler, evidência, causa raiz, política ou fato. "
        "Cada ação deve referenciar um diagnostic_code fornecido e somente evidence_ids fornecidos. "
        "OAI-SearchBot está relacionado à descoberta no ChatGPT Search; GPTBot está relacionado a "
        "potencial uso para treinamento. Google-Extended é um token de controle de usos específicos "
        "Google/Gemini e não requisito de inclusão/ranking no Google Search. Nunca recomende liberar "
        "GPTBot ou Google-Extended como técnica de SEO/Search. Mudanças nesses controles exigem decisão "
        "de política humana. llms.txt é proposta comunitária experimental, não web standard obrigatório. "
        "Não apresente sua ausência como defeito nem como requisito GEO. "
        "Quando a evidência não permitir uma mudança exata e segura, recomende validação humana."
    )
    payload = _candidate_payload(candidate, schema=schema, instructions=instructions, facts=facts)
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
        usage = _candidate_usage(candidate, raw)
        native_error = _candidate_native_error(candidate, raw)
        if native_error is not None:
            diagnostic = native_error
            status = AttemptStatus.TECHNICAL_ERROR
            reason = native_error.reason
        else:
            explanation = _validate(
                _candidate_extract_payload(candidate, raw),
                allowed_codes=allowed_codes,
                allowed_evidence=allowed_evidence,
                resource_evidence=resource_evidence,
            )
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
            f"contract={CONTRACT_VERSION};diagnostics={len(facts)};"
            "scoring_impact=BOUNDED_STATIC_FACTORS"
        ),
        request_payload_hash=payload_hash,
        provider_qualification=candidate.policy.qualification,
        provider_reliability_score=candidate.policy.reliability_score,
        semantic_contract_version=CONTRACT_VERSION,
    )
    if status is AttemptStatus.SUCCESS and explanation is not None:
        return (
            M24AiResult(
                state=ProviderState.AVAILABLE,
                provider=candidate.name,
                model=candidate.model,
                explanation=explanation,
            ),
            attempt,
        )
    return (
        M24AiResult(
            state=ProviderState.UNAVAILABLE,
            provider=candidate.name,
            model=candidate.model,
            reason=reason or "M24_AI_UNAVAILABLE",
        ),
        attempt,
    )


def _validate(
    value: Any,
    *,
    allowed_codes: frozenset[str],
    allowed_evidence: frozenset[str],
    resource_evidence: Mapping[str, frozenset[str]],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("M24 AI root must be an object")
    summary = str(value.get("summary_pt") or "").strip()
    policy_note = str(value.get("policy_note_pt") or "").strip()
    actions = value.get("actions")
    resource_assessments = value.get("resource_assessments")
    if not summary or not policy_note or not isinstance(actions, list) or not isinstance(resource_assessments, list):
        raise ValueError("M24 AI response misses required fields")
    output_actions: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for raw in actions[:12]:
        if not isinstance(raw, Mapping):
            raise ValueError("M24 AI action must be an object")
        code = str(raw.get("diagnostic_code") or "").strip()
        if code not in allowed_codes:
            raise ValueError("M24 AI action references unknown diagnostic code")
        if code in seen_codes:
            continue
        seen_codes.add(code)
        objective = str(raw.get("objective_pt") or "").strip()
        change = str(raw.get("recommended_change_pt") or "").strip()
        evidence_raw = raw.get("evidence_ids")
        if not objective or not change or not isinstance(evidence_raw, list):
            raise ValueError("M24 AI action contains invalid fields")
        evidence_ids = tuple(str(item).strip() for item in evidence_raw if str(item).strip())
        if not set(evidence_ids).issubset(allowed_evidence):
            raise ValueError("M24 AI action references evidence outside supplied universe")
        output_actions.append(
            {
                "diagnostic_code": code,
                "objective_pt": objective[:1200],
                "recommended_change_pt": change[:2500],
                "evidence_ids": list(evidence_ids),
                "human_validation_required": bool(raw.get("human_validation_required")),
            }
        )
    output_resources: list[dict[str, Any]] = []
    seen_resources: set[str] = set()
    for raw in resource_assessments[:2]:
        if not isinstance(raw, Mapping):
            raise ValueError("M24 AI resource assessment must be an object")
        resource = str(raw.get("resource") or "").strip().upper()
        verdict = str(raw.get("verdict") or "").strip().upper()
        if resource not in {"ROBOTS", "SITEMAP"} or verdict not in {"POSITIVE", "NEUTRAL", "NEGATIVE"}:
            raise ValueError("M24 AI resource assessment contains invalid classification")
        if resource in seen_resources:
            raise ValueError("M24 AI resource assessment duplicates a resource")
        seen_resources.add(resource)
        rationale = str(raw.get("rationale_pt") or "").strip()
        evidence_raw = raw.get("evidence_ids")
        if not rationale or not isinstance(evidence_raw, list):
            raise ValueError("M24 AI resource assessment contains invalid fields")
        evidence_ids = tuple(str(item).strip() for item in evidence_raw if str(item).strip())
        allowed_for_resource = resource_evidence.get(resource, frozenset())
        if not evidence_ids or not set(evidence_ids).issubset(allowed_for_resource):
            raise ValueError("M24 AI resource assessment references evidence outside its resource universe")
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise ValueError("M24 AI resource assessment confidence is invalid") from exc
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("M24 AI resource assessment confidence is outside 0..1")
        output_resources.append({
            "resource": resource,
            "verdict": verdict,
            "confidence": confidence,
            "evidence_ids": list(evidence_ids),
            "rationale_pt": rationale[:1600],
        })
    return {
        "summary_pt": summary[:2000],
        "actions": output_actions,
        "resource_assessments": output_resources,
        "policy_note_pt": policy_note[:1600],
    }


def _first_snapshot(workspace: AuditWorkspace, audit_id: str) -> dict[str, Any] | None:
    uri = workspace.database.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        row = connection.execute(
            """
            SELECT ps.snapshot_id,ps.page_id,ps.device,
                   COALESCE(ps.final_url,p.normalized_url) AS url
            FROM page_snapshots ps JOIN pages p ON p.page_id=ps.page_id
            WHERE p.audit_id=? ORDER BY ps.captured_at LIMIT 1
            """,
            (audit_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


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


def _persist_result(
    workspace: AuditWorkspace,
    audit_id: str,
    result: M24AiResult,
) -> Path:
    artifact_dir = workspace.artifacts / "m24"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "ai-technical-remediation.json"
    payload = {
        "contract_version": CONTRACT_VERSION,
        "state": result.state.value,
        "provider": result.provider,
        "model": result.model,
        "reason": result.reason,
        "explanation": result.explanation,
        "scoring_impact": "BOUNDED_STATIC_FACTORS" if result.explanation and result.explanation.get("resource_assessments") else "NONE",
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    reference = path.relative_to(workspace.root).as_posix()
    persist_ai_result(
        workspace=workspace,
        audit_id=audit_id,
        state=result.state.value,
        provider=result.provider,
        model=result.model,
        reason=result.reason,
        artifact_reference=reference,
    )
    return path
