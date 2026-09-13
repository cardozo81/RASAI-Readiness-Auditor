"""Deterministic evolution and optional evidence-bound AI analysis for CONS reports.

The source AUD workspaces are always read-only. Monitoring and Fix Verification own the
facts; AI can only interpret a bounded packet of those persisted facts and recommend
next actions. AI output never changes SARI/SCORE-GEO or the source audit databases.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from rasai.ai_cost_policy import CandidateCostEstimate, PRICING_VERSION, estimate_candidate_cost
from rasai.ai_execution_state import clear_current_ai_execution
from rasai.ai_resilience import DECISION_FALLBACK, DECISION_FALLBACK_SUCCESS, DECISION_STOP, DECISION_SUCCESS
from rasai.improvement_intelligence import (
    _provider_extract,
    _provider_native_error,
    _provider_payload,
    _provider_usage,
)
from rasai.m18_ai import (
    AttemptStatus,
    ProviderAttempt,
    ProviderDiagnostic,
    ProviderErrorClass,
    ResponsesSemanticProvider,
    _diagnostic_from_http as _core_diagnostic_from_http,
    estimate_cost,
)
from rasai.monitoring.compare import compare_audits
from rasai.monitoring.models import ChangeEvent, ComparisonResult
from rasai.provider_extensions import _diagnostic_from_http as _extension_diagnostic_from_http
from rasai.provider_registry import get_provider_registration
from rasai.provider_runtime_policy import build_semantic_provider, provider_reasoning_env
from rasai.quality.verification import VerificationBundle, verify_fixes

from .index import ConsolidationIndex
from .models import ConsolidationFilter, GenerationResult

SPECIALIST_CONTRACT = "CONSOLIDATED-SPECIALIST-001"
EVOLUTION_CONTRACT = "CONSOLIDATED-EVOLUTION-001"
AI_SCOPE = "CONSOLIDATED_SPECIALIST"
_ALLOWED_COMPARISON_MODES = frozenset({"FIRST_LAST", "LATEST_PREVIOUS", "MANUAL"})
_TOPIC_ORDER = (
    "SEO",
    "GEO_AI_READINESS",
    "PERFORMANCE",
    "UX_APDEX",
    "ACCESSIBILITY",
    "INFRASTRUCTURE",
    "SECURITY",
    "CONTENT_SEMANTICS",
)
_TOPIC_LABELS = {
    "SEO": "SEO",
    "GEO_AI_READINESS": "GEO / AI Readiness",
    "PERFORMANCE": "Performance",
    "UX_APDEX": "UX / Apdex",
    "ACCESSIBILITY": "Acessibilidade",
    "INFRASTRUCTURE": "Infraestrutura",
    "SECURITY": "Segurança",
    "CONTENT_SEMANTICS": "Conteúdo e semântica",
}


@dataclass(frozen=True, slots=True)
class SpecialistTokenHint:
    estimated_input_tokens: int
    estimated_output_tokens: int


@dataclass(frozen=True, slots=True)
class SpecialistPreview:
    available: bool
    reason: str | None
    baseline_audit_id: str | None
    current_audit_id: str | None
    comparison_mode: str
    candidates: tuple[CandidateCostEstimate, ...]
    selected: CandidateCostEstimate | None
    event_count: int = 0


@dataclass(frozen=True, slots=True)
class SpecialistAttempt:
    provider: str
    model: str
    reasoning: str
    status: str
    duration_ms: int
    estimated_cost: float | None
    currency: str | None
    pricing_version: str | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    error_class: str | None = None
    http_status: int | None = None


@dataclass(frozen=True, slots=True)
class SpecialistRun:
    requested: bool
    status: str
    summary: str
    topic_analyses: tuple[dict[str, Any], ...]
    attempts: tuple[SpecialistAttempt, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class EvolutionBundle:
    comparison: ComparisonResult
    verification: VerificationBundle
    baseline_workspace: Path
    current_workspace: Path
    events: tuple[dict[str, Any], ...]
    fixes: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


def validate_comparison_mode(value: str) -> str:
    mode = str(value or "FIRST_LAST").strip().upper()
    if mode not in _ALLOWED_COMPARISON_MODES:
        raise ValueError("comparison_mode deve ser FIRST_LAST, LATEST_PREVIOUS ou MANUAL")
    return mode


def _workspace(root: Path, row: Mapping[str, Any]) -> Path:
    return root / Path(str(row.get("db_path") or "")).parent


def _select_rows(root: Path, filters: ConsolidationFilter) -> tuple[dict[str, Any], dict[str, Any]]:
    index = ConsolidationIndex(root)
    rows = list(index.candidate_audits(filters))
    if len(rows) < 2:
        raise ValueError("a análise de evolução requer pelo menos duas auditorias concluídas no universo filtrado")
    mode = validate_comparison_mode(filters.comparison_mode)
    if mode == "FIRST_LAST":
        return rows[0], rows[-1]
    if mode == "LATEST_PREVIOUS":
        return rows[-2], rows[-1]
    baseline = next((row for row in rows if str(row.get("audit_id")) == str(filters.baseline_audit_id or "")), None)
    current = next((row for row in rows if str(row.get("audit_id")) == str(filters.current_audit_id or "")), None)
    if baseline is None or current is None:
        raise ValueError("baseline/current manual deve pertencer às auditorias do universo filtrado")
    if str(baseline.get("audit_id")) == str(current.get("audit_id")):
        raise ValueError("baseline e current devem ser auditorias distintas")
    if str(baseline.get("event_time")) > str(current.get("event_time")):
        raise ValueError("baseline manual deve ser anterior ao current")
    return baseline, current


def _event_in_scope(event: ChangeEvent, filters: ConsolidationFilter) -> bool:
    if filters.devices and event.device and event.device.upper() not in {item.upper() for item in filters.devices}:
        return False
    if filters.urls:
        selected = set(filters.urls)
        if event.url is not None and event.url not in selected:
            return False
        # Audit-level score/finding aggregates cannot be projected onto an arbitrary
        # URL subset without recalculation. Match the base consolidator's guard.
        if event.url is None and event.domain in {"SCORE", "FINDINGS"}:
            return False
    return True


def _topic(event: ChangeEvent) -> str:
    label = str(event.label or "").casefold()
    rule = str(event.rule_id or "").upper()
    if event.domain in {"APDEX", "UX_APDEX"}:
        return "UX_APDEX"
    if event.domain == "PERFORMANCE":
        if "accessibility" in label:
            return "ACCESSIBILITY"
        if "seo" in label:
            return "SEO"
        return "PERFORMANCE"
    if event.domain == "PAGE":
        if any(token in label for token in ("canonical", "robots", "title")):
            return "SEO"
        return "INFRASTRUCTURE"
    if event.domain == "SCORE":
        upper = str(event.label or "").upper()
        if "ACCESS" in upper and "AI" not in upper:
            return "ACCESSIBILITY"
        if any(token in upper for token in ("PERFORMANCE", "EXPERIENCE")):
            return "PERFORMANCE"
        if any(token in upper for token in ("INDEX", "DISCOVERY", "CRAWL")):
            return "SEO"
        if any(token in upper for token in ("CONTENT", "SEMANTIC", "ENTITY", "CITATION", "ANSWER", "AI_", "GEO")):
            return "GEO_AI_READINESS"
        return "GEO_AI_READINESS"
    if event.domain == "RULE":
        # Rule IDs are retained for evidence lookup; rules tied to transport/indexing are
        # additionally recognizable by persisted label/metadata in the detailed AUD.
        if rule in {"BR-GEO-001", "BR-GEO-005", "BR-GEO-006", "BR-GEO-007", "BR-GEO-053", "BR-GEO-054"}:
            return "INFRASTRUCTURE"
        return "GEO_AI_READINESS"
    return "CONTENT_SEMANTICS"


def _event_id(index: int) -> str:
    return f"CHANGE-{index:04d}"


def _fix_id(index: int) -> str:
    return f"FIX-{index:04d}"


def build_evolution(audits_root: str | Path, filters: ConsolidationFilter) -> EvolutionBundle:
    root = Path(audits_root)
    baseline_row, current_row = _select_rows(root, filters)
    baseline_workspace = _workspace(root, baseline_row)
    current_workspace = _workspace(root, current_row)
    comparison = compare_audits(baseline_workspace, current_workspace)
    verification = verify_fixes(baseline_workspace, current_workspace)

    raw_events = [
        event for event in comparison.events
        if _event_in_scope(event, filters)
        and (event.material or event.status in {"NOT_COMPARABLE", "DATA_UNAVAILABLE"})
    ]
    status_rank = {"REGRESSED": 0, "NEW": 1, "RESOLVED": 2, "IMPROVED": 3, "CHANGED": 4, "NOT_COMPARABLE": 5, "DATA_UNAVAILABLE": 6}
    raw_events.sort(key=lambda item: (status_rank.get(item.status, 9), -_severity_rank(item.severity), item.domain, item.key))
    events = tuple(
        {
            "evidence_id": _event_id(index),
            "topic": _topic(event),
            "domain": event.domain,
            "label": event.label,
            "status": event.status,
            "before": event.before,
            "after": event.after,
            "severity": event.severity,
            "device": event.device,
            "url": event.url,
            "rule_id": event.rule_id,
            "unit": event.unit,
            "delta": event.delta,
            "delta_percent": event.delta_percent,
            "reason": event.reason,
        }
        for index, event in enumerate(raw_events, 1)
    )

    selected_devices = {item.upper() for item in filters.devices}
    selected_urls = set(filters.urls)
    fix_items = [
        item for item in verification.items
        if (not selected_devices or not item.device or item.device.upper() in selected_devices)
        and (not selected_urls or item.url is None or item.url in selected_urls)
    ]
    fixes = tuple(
        {
            "evidence_id": _fix_id(index),
            "topic": "GEO_AI_READINESS",
            "rule_id": item.rule_id,
            "url": item.url,
            "device": item.device,
            "severity": item.severity,
            "status": item.status,
            "before": item.before,
            "after": item.after,
            "reason": item.reason,
        }
        for index, item in enumerate(fix_items, 1)
    )
    limitations = tuple(dict.fromkeys((*comparison.compatibility_notes, *verification.limitations)))
    return EvolutionBundle(
        comparison=comparison,
        verification=verification,
        baseline_workspace=baseline_workspace,
        current_workspace=current_workspace,
        events=events,
        fixes=fixes,
        limitations=limitations,
    )


def _severity_rank(value: str) -> int:
    return {"CRITICAL": 5, "HIGH": 4, "MEDIUM": 3, "LOW": 2, "INFO": 1}.get(str(value).upper(), 0)


def _packet(bundle: EvolutionBundle) -> dict[str, Any]:
    events = list(bundle.events[:180])
    fixes = list(bundle.fixes[:120])
    return {
        "contract": SPECIALIST_CONTRACT,
        "baseline": {"audit_id": bundle.comparison.baseline.audit_id, "event_time": bundle.comparison.baseline.event_time},
        "current": {"audit_id": bundle.comparison.current.audit_id, "event_time": bundle.comparison.current.event_time},
        "comparison": {
            "comparable": bundle.comparison.comparable,
            "counts": bundle.comparison.counts,
            "material_counts": bundle.comparison.material_counts,
            "limitations": list(bundle.limitations),
        },
        "changes": events,
        "fix_verification": fixes,
        "governance": {
            "sari_score_impact": "NONE",
            "causal_claims": "FORBIDDEN",
            "security_mode": "PASSIVE_ONLY",
            "human_review_required": True,
        },
    }


def _token_hint(packet: Mapping[str, Any]) -> SpecialistTokenHint:
    raw = json.dumps(packet, ensure_ascii=False, separators=(",", ":"), default=str)
    input_tokens = max(2_000, int(math.ceil((len(raw) + 4_000) / 4.0)))
    topics = len({str(item.get("topic")) for item in packet.get("changes", []) if isinstance(item, Mapping)})
    output_tokens = min(8_000, 1_800 + max(topics, 1) * 300)
    return SpecialistTokenHint(input_tokens, output_tokens)


def _effective_env(filters: ConsolidationFilter, env: Mapping[str, str] | None = None) -> dict[str, str]:
    result = dict(os.environ if env is None else env)
    registration = get_provider_registration(filters.ai_provider or "")
    if registration is not None and filters.ai_reasoning:
        variable = provider_reasoning_env(registration.provider_name)
        if variable:
            result[variable] = filters.ai_reasoning
    return result


def _build_ai(filters: ConsolidationFilter, env: Mapping[str, str] | None = None) -> Any:
    selection = str(filters.ai_provider or "none")
    model = filters.ai_model if selection.casefold() not in {"auto", "none", ""} else None
    provider = build_semantic_provider(selection, model_override=model, env=_effective_env(filters, env))
    timeout = float(filters.ai_timeout_seconds or 180.0)
    if hasattr(provider, "timeout"):
        provider.timeout = timeout
    return provider


def preview_specialist(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    env: Mapping[str, str] | None = None,
) -> SpecialistPreview:
    try:
        bundle = build_evolution(audits_root, filters)
    except (OSError, ValueError, RuntimeError) as exc:
        return SpecialistPreview(False, f"{type(exc).__name__}: {exc}", None, None, filters.comparison_mode, (), None)
    if not filters.specialist_ai or not filters.ai_provider or filters.ai_provider.casefold() == "none":
        return SpecialistPreview(
            False,
            "AI_NOT_REQUESTED",
            bundle.comparison.baseline.audit_id,
            bundle.comparison.current.audit_id,
            filters.comparison_mode,
            (),
            None,
            len(bundle.events),
        )
    try:
        provider = _build_ai(filters, env)
        hint = _token_hint(_packet(bundle))
        now = datetime.now(timezone.utc)
        if hasattr(provider, "ordered_candidates_for_need"):
            candidates = provider.ordered_candidates_for_need(hint, scope=AI_SCOPE)
            estimates = tuple(estimate_candidate_cost(item, hint, scope=AI_SCOPE, at=now) for item in candidates)
        else:
            estimates = (estimate_candidate_cost(provider, hint, scope=AI_SCOPE, at=now),)
        selected = estimates[0] if estimates else None
        if selected is None:
            return SpecialistPreview(False, "AI_PROVIDER_CHAIN_EXHAUSTED", bundle.comparison.baseline.audit_id, bundle.comparison.current.audit_id, filters.comparison_mode, (), None, len(bundle.events))
        return SpecialistPreview(True, None, bundle.comparison.baseline.audit_id, bundle.comparison.current.audit_id, filters.comparison_mode, estimates, selected, len(bundle.events))
    except Exception as exc:
        return SpecialistPreview(False, f"AI_NOT_AVAILABLE:{type(exc).__name__}:{str(exc)[:240]}", bundle.comparison.baseline.audit_id, bundle.comparison.current.audit_id, filters.comparison_mode, (), None, len(bundle.events))
    finally:
        clear_current_ai_execution()


def _schema(evidence_ids: tuple[str, ...]) -> dict[str, Any]:
    topic = {
        "type": "object",
        "additionalProperties": False,
        "required": ["topic", "assessment", "recommended_actions", "priority", "confidence", "evidence_ids"],
        "properties": {
            "topic": {"type": "string", "enum": list(_TOPIC_ORDER)},
            "assessment": {"type": "string", "maxLength": 3000},
            "recommended_actions": {"type": "array", "maxItems": 8, "items": {"type": "string", "maxLength": 1500}},
            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_ids": {"type": "array", "uniqueItems": True, "maxItems": 30, "items": {"type": "string", "enum": list(evidence_ids)}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "topic_analyses"],
        "properties": {
            "summary": {"type": "string", "maxLength": 5000},
            "topic_analyses": {"type": "array", "maxItems": len(_TOPIC_ORDER), "items": topic},
        },
    }


def _instructions() -> str:
    return (
        "You are the evidence-bound SEO/GEO evolution specialist for RASAi. Interpret only the supplied persisted "
        "comparison and Fix Verification evidence. Return JSON only and match the schema exactly. Do not recalculate "
        "or alter SARI/SCORE-GEO. Distinguish an observed improvement from a FIXED/PARTIALLY_FIXED verification. "
        "Do not claim that a technical change caused Search, AI visibility, traffic, conversion or ranking changes; "
        "temporal association is not causality. Security analysis is passive only. Never invent URLs, rule IDs, "
        "metrics, fixes, causes, credentials, statistics or evidence. Recommendations must be practical and grouped "
        "by the requested topic. Cite only supplied evidence_ids. Write explanatory text in pt-BR. Human review is mandatory."
    )


def _validated_payload(payload: Any, allowed: set[str]) -> tuple[str, tuple[dict[str, Any], ...]]:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("topic_analyses"), list):
        raise ValueError("specialist response must contain summary and topic_analyses")
    analyses: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in payload["topic_analyses"][: len(_TOPIC_ORDER)]:
        if not isinstance(raw, Mapping):
            raise ValueError("topic analysis must be an object")
        topic = str(raw.get("topic") or "")
        if topic not in _TOPIC_ORDER or topic in seen:
            continue
        evidence = tuple(str(item) for item in raw.get("evidence_ids", ()) if str(item))
        if not set(evidence).issubset(allowed):
            raise ValueError("AI cited evidence outside the supplied packet")
        priority = str(raw.get("priority") or "P3").upper()
        confidence = float(raw.get("confidence"))
        if priority not in {"P0", "P1", "P2", "P3"} or not 0 <= confidence <= 1:
            raise ValueError("invalid specialist priority/confidence")
        actions = tuple(str(item)[:1500] for item in raw.get("recommended_actions", ()) if str(item).strip())[:8]
        analyses.append({
            "topic": topic,
            "assessment": str(raw.get("assessment") or "")[:3000],
            "recommended_actions": actions,
            "priority": priority,
            "confidence": confidence,
            "evidence_ids": evidence,
        })
        seen.add(topic)
    return str(payload.get("summary") or "")[:5000], tuple(analyses)


def _attempt_record(provider: Any, *, status: AttemptStatus, started: datetime, duration_ms: int, usage: Any, diagnostic: ProviderDiagnostic | None, request_hash: str, index: int) -> ProviderAttempt:
    amount, currency, pricing_version = estimate_cost(str(provider.name), str(provider.model), usage, datetime.now(timezone.utc))
    finished = datetime.now(timezone.utc)
    return ProviderAttempt(
        provider=str(provider.name),
        model=str(provider.model),
        reasoning_profile=str(getattr(provider, "reasoning_profile", getattr(provider, "requested_reasoning_effort", "PROVIDER_DEFAULT"))),
        provider_rank=int(getattr(getattr(provider, "policy", None), "rank", 999)),
        attempt_index=index,
        snapshot_id="CONSOLIDATED",
        url="consolidated://evolution",
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        status=status,
        diagnostic=diagnostic,
        usage=usage,
        estimated_cost=amount,
        cost_currency=currency,
        pricing_version=pricing_version,
        request_message_summary=f"contract={SPECIALIST_CONTRACT}",
        request_payload_hash=request_hash,
        provider_qualification=str(getattr(getattr(provider, "policy", None), "qualification", "PROVISIONAL")),
        provider_reliability_score=getattr(getattr(provider, "policy", None), "reliability_score", None),
        semantic_contract_version=SPECIALIST_CONTRACT,
        retry_eligible=False,
        decision=DECISION_STOP,
    )


def _public_attempt(attempt: ProviderAttempt) -> SpecialistAttempt:
    usage = attempt.usage
    diagnostic = attempt.diagnostic
    error_class = diagnostic.error_class.value if diagnostic is not None and diagnostic.error_class is not None else None
    return SpecialistAttempt(
        provider=attempt.provider,
        model=attempt.model or "",
        reasoning=attempt.reasoning_profile,
        status=attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status),
        duration_ms=attempt.duration_ms,
        estimated_cost=attempt.estimated_cost,
        currency=attempt.cost_currency,
        pricing_version=attempt.pricing_version,
        input_tokens=getattr(usage, "input_tokens", None) if usage else None,
        cached_input_tokens=getattr(usage, "cached_input_tokens", None) if usage else None,
        output_tokens=getattr(usage, "output_tokens", None) if usage else None,
        reasoning_tokens=getattr(usage, "reasoning_tokens", None) if usage else None,
        error_class=error_class,
        http_status=getattr(diagnostic, "http_status", None) if diagnostic else None,
    )


def run_ai(bundle: EvolutionBundle, filters: ConsolidationFilter, *, env: Mapping[str, str] | None = None) -> SpecialistRun:
    if not filters.specialist_ai:
        return SpecialistRun(False, "NOT_REQUESTED", "", (), ())
    packet = _packet(bundle)
    allowed = tuple(sorted({str(item["evidence_id"]) for item in (*bundle.events, *bundle.fixes)}))
    if not allowed:
        return SpecialistRun(True, "NO_DATA", "", (), (), "nenhuma mudança material elegível para análise")
    schema = _schema(allowed)
    instructions = _instructions()
    user_text = "Persisted RASAi consolidated evolution evidence:\n" + json.dumps(packet, ensure_ascii=False, default=str)
    request_hash = sha256(user_text.encode("utf-8")).hexdigest()
    attempts: list[ProviderAttempt] = []
    try:
        selection = _build_ai(filters, env)
        hint = _token_hint(packet)
        if hasattr(selection, "ordered_candidates_for_need"):
            candidates = selection.ordered_candidates_for_need(hint, scope=AI_SCOPE)
            coordinator = selection.coordinator
        else:
            candidates = (selection,)
            coordinator = None
        if not candidates:
            return SpecialistRun(True, "UNAVAILABLE", "", (), (), "AI_PROVIDER_CHAIN_EXHAUSTED")
        fallback_from: str | None = None
        fallback_reason: str | None = None
        for ordinal, provider in enumerate(candidates, 1):
            body = json.dumps(_provider_payload(provider, instructions=instructions, user_text=user_text, schema=schema), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            started = datetime.now(timezone.utc)
            started_perf = time.perf_counter()
            status = AttemptStatus.TECHNICAL_ERROR
            diagnostic: ProviderDiagnostic | None = None
            usage = None
            raw: Mapping[str, Any] | None = None
            try:
                candidate = provider._transport(provider.endpoint, provider._headers(), body, float(filters.ai_timeout_seconds or 180.0))
                if not isinstance(candidate, Mapping):
                    diagnostic = ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE)
                else:
                    raw = candidate
                    usage = _provider_usage(provider, raw)
                    diagnostic = _provider_native_error(provider, raw)
                    if diagnostic is None:
                        status = AttemptStatus.SUCCESS
            except HTTPError as exc:
                diagnostic = _core_diagnostic_from_http(exc) if isinstance(provider, ResponsesSemanticProvider) else _extension_diagnostic_from_http(exc)
            except TimeoutError:
                diagnostic = ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR)
            except (URLError, OSError):
                diagnostic = ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR)
            except Exception as exc:
                diagnostic = ProviderDiagnostic(ProviderErrorClass.UNKNOWN_PROVIDER_ERROR, error_type=type(exc).__name__)
            duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
            attempt = _attempt_record(provider, status=status, started=started, duration_ms=duration_ms, usage=usage, diagnostic=diagnostic, request_hash=request_hash, index=ordinal)
            if fallback_from:
                attempt = _replace_attempt(attempt, fallback_from=fallback_from, fallback_reason=fallback_reason)
            if coordinator is not None:
                coordinator.record_attempt(attempt, scope=AI_SCOPE)
            if status is AttemptStatus.SUCCESS and raw is not None:
                try:
                    summary, analyses = _validated_payload(_provider_extract(provider, raw), set(allowed))
                except Exception as exc:
                    diagnostic = ProviderDiagnostic(ProviderErrorClass.CONTRACT_ERROR, error_type=type(exc).__name__, error_code="CONSOLIDATED_SPECIALIST_OUTPUT_INVALID")
                    attempt = _attempt_record(provider, status=AttemptStatus.CONTRACT_ERROR, started=started, duration_ms=duration_ms, usage=usage, diagnostic=diagnostic, request_hash=request_hash, index=ordinal)
                    if coordinator is not None:
                        coordinator.record_attempt(attempt, scope=AI_SCOPE)
                else:
                    attempt = _replace_decision(attempt, DECISION_FALLBACK_SUCCESS if fallback_from else DECISION_SUCCESS)
                    attempts.append(attempt)
                    return SpecialistRun(True, "COMPLETE", summary, analyses, tuple(_public_attempt(item) for item in attempts))
            attempts.append(attempt)
            if coordinator is not None and not coordinator.is_eligible(str(provider.name)):
                pass
            if ordinal < len(candidates):
                attempts[-1] = _replace_decision(attempts[-1], DECISION_FALLBACK)
                fallback_from = str(provider.name)
                fallback_reason = diagnostic.reason if diagnostic is not None else "AI_PROVIDER_UNAVAILABLE"
        reason = attempts[-1].diagnostic.reason if attempts and attempts[-1].diagnostic is not None else "AI_PROVIDER_UNAVAILABLE"
        return SpecialistRun(True, "UNAVAILABLE", "", (), tuple(_public_attempt(item) for item in attempts), reason)
    finally:
        clear_current_ai_execution()


def _replace_decision(attempt: ProviderAttempt, decision: str) -> ProviderAttempt:
    from dataclasses import replace
    return replace(attempt, decision=decision)


def _replace_attempt(attempt: ProviderAttempt, *, fallback_from: str, fallback_reason: str | None) -> ProviderAttempt:
    from dataclasses import replace
    return replace(attempt, fallback_from_provider=fallback_from, fallback_reason=fallback_reason)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _deterministic_html(bundle: EvolutionBundle) -> str:
    counts = bundle.comparison.material_counts
    cards = "".join(
        f"<div class='metric'><span>{label}</span><strong>{int(counts.get(status, 0))}</strong></div>"
        for status, label in (("IMPROVED", "Melhorias"), ("RESOLVED", "Resolvidos"), ("REGRESSED", "Regressões"), ("NEW", "Novos sinais"))
    )
    rows = []
    for item in bundle.events[:250]:
        target = item.get("url") or "escopo global"
        context = " / ".join(part for part in (item.get("device"), item.get("rule_id")) if part)
        delta = f" Δ {_fmt(item.get('delta'))} {escape(str(item.get('unit') or ''))}" if item.get("delta") is not None else ""
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(item['evidence_id']))}</code></td>"
            f"<td>{escape(_TOPIC_LABELS.get(str(item['topic']), str(item['topic'])))}</td>"
            f"<td>{escape(str(item['status']))}</td>"
            f"<td>{escape(str(item['label']))}</td>"
            f"<td>{escape(_fmt(item.get('before')))} → {escape(_fmt(item.get('after')))}{escape(delta)}</td>"
            f"<td>{escape(str(target))}<br><small>{escape(context)}</small></td>"
            "</tr>"
        )
    fix_rows = "".join(
        "<tr>"
        f"<td><code>{escape(str(item['evidence_id']))}</code></td><td>{escape(str(item['rule_id']))}</td>"
        f"<td>{escape(str(item['status']))}</td><td>{escape(_fmt(item.get('before')))} → {escape(_fmt(item.get('after')))}</td>"
        f"<td>{escape(str(item.get('url') or 'escopo global'))}</td>"
        "</tr>"
        for item in bundle.fixes[:200]
    ) or "<tr><td colspan='5'>Nenhum FAIL/WARNING do baseline elegível para Fix Verification neste escopo.</td></tr>"
    notes = "".join(f"<li>{escape(item)}</li>" for item in bundle.limitations)
    return f"""
<section id='specialist-evolution' class='panel'>
  <div class='kicker'>Evolução determinística</div>
  <h2>O que melhorou, piorou e foi verificado</h2>
  <p>Comparação <strong>{escape(bundle.comparison.baseline.audit_id)}</strong> → <strong>{escape(bundle.comparison.current.audit_id)}</strong>. Os deltas abaixo são calculados pelo Monitoring/Fix Verification; não dependem de IA.</p>
  <div class='metric-grid'>{cards}</div>
  <div class='table-wrap bounded'><table><thead><tr><th>Evidência</th><th>Tópico</th><th>Estado</th><th>Sinal</th><th>Antes → depois</th><th>Escopo</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="6">Nenhuma mudança material comparável no par selecionado.</td></tr>'}</tbody></table></div>
  <h3>Fix Verification</h3>
  <p><code>FIXED</code> significa que uma condição FAIL/WARNING persistida atingiu PASS na auditoria atual. Isso não prova impacto downstream em Search/IA.</p>
  <div class='table-wrap bounded'><table><thead><tr><th>Evidência</th><th>Regra</th><th>Verificação</th><th>Antes → depois</th><th>URL</th></tr></thead><tbody>{fix_rows}</tbody></table></div>
  {f"<details><summary>Limitações de comparabilidade</summary><ul>{notes}</ul></details>" if notes else ''}
</section>
"""


def _ai_html(run: SpecialistRun) -> str:
    if not run.requested:
        return ""
    if run.status != "COMPLETE":
        return f"<section id='specialist-ai' class='panel'><div class='kicker'>Análise especialista por IA</div><h2>IA indisponível; análise determinística preservada</h2><p>{escape(run.reason or run.status)}</p></section>"
    cards = []
    for item in run.topic_analyses:
        actions = "".join(f"<li>{escape(str(action))}</li>" for action in item.get("recommended_actions", ()))
        evidence = ", ".join(str(value) for value in item.get("evidence_ids", ())) or "-"
        cards.append(
            f"<article class='page-card'><div class='panel-head'><div><div class='kicker'>{escape(_TOPIC_LABELS.get(str(item['topic']), str(item['topic'])))}</div>"
            f"<h3>Prioridade {escape(str(item['priority']))}</h3></div><span class='badge'>confiança {float(item['confidence']):.2f}</span></div>"
            f"<p>{escape(str(item['assessment']))}</p><h4>Próximas ações</h4><ul>{actions}</ul>"
            f"<p><strong>Evidências:</strong> <code>{escape(evidence)}</code></p></article>"
        )
    attempts = "".join(
        f"<tr><td>{escape(item.provider)}</td><td>{escape(item.model)}</td><td>{escape(item.reasoning)}</td><td>{escape(item.status)}</td>"
        f"<td>{item.input_tokens if item.input_tokens is not None else '-'}</td><td>{item.output_tokens if item.output_tokens is not None else '-'}</td>"
        f"<td>{item.estimated_cost if item.estimated_cost is not None else '-'}</td><td>{escape(item.currency or '-')}</td></tr>"
        for item in run.attempts
    )
    return f"""
<section id='specialist-ai' class='panel'>
  <div class='kicker'>Análise especialista por IA · advisory/non-scoring</div>
  <h2>Leitura SEO/GEO da evolução e plano priorizado</h2>
  <p>{escape(run.summary)}</p>
  <div class='page-grid'>{''.join(cards)}</div>
  <details><summary>Uso de IA desta análise</summary><div class='table-wrap'><table><thead><tr><th>Provider</th><th>Modelo</th><th>Reasoning</th><th>Status</th><th>Input</th><th>Output</th><th>Custo estimado</th><th>Moeda</th></tr></thead><tbody>{attempts}</tbody></table></div></details>
  <p class='notice info'><strong>Limite:</strong> recomendações são interpretação assistida por IA sobre evidência persistida. Associação temporal não é causalidade e nenhuma conclusão desta seção altera SARI/SCORE-GEO.</p>
</section>
"""


def _augment_report(path: Path, bundle: EvolutionBundle, run: SpecialistRun) -> None:
    html = path.read_text(encoding="utf-8")
    block = _deterministic_html(bundle) + _ai_html(run)
    if "id='specialist-evolution'" in html or 'id="specialist-evolution"' in html:
        return
    if "<footer" in html:
        rendered = html.replace("<footer", block + "<footer", 1)
    else:
        rendered = html.replace("</body>", block + "</body>", 1)
    path.write_text(rendered, encoding="utf-8", newline="\n")


def _augment_manifest(path: Path, filters: ConsolidationFilter, bundle: EvolutionBundle, run: SpecialistRun) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evolution_analysis"] = {
        "contract": EVOLUTION_CONTRACT,
        "comparison_mode": filters.comparison_mode,
        "baseline_audit_id": bundle.comparison.baseline.audit_id,
        "current_audit_id": bundle.comparison.current.audit_id,
        "comparable": bundle.comparison.comparable,
        "material_counts": bundle.comparison.material_counts,
        "fix_verification_counts": bundle.verification.counts,
        "event_count": len(bundle.events),
        "limitations": list(bundle.limitations),
    }
    payload["specialist_ai"] = {
        "contract": SPECIALIST_CONTRACT,
        "requested": run.requested,
        "status": run.status,
        "provider_selection": filters.ai_provider if run.requested else None,
        "model_selection": filters.ai_model if run.requested else None,
        "reasoning_selection": filters.ai_reasoning if run.requested else None,
        "pricing_version": PRICING_VERSION if run.requested else None,
        "reason": run.reason,
        "attempts": [asdict(item) for item in run.attempts],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def enrich_result(audits_root: str | Path, filters: ConsolidationFilter, result: GenerationResult, *, env: Mapping[str, str] | None = None) -> GenerationResult:
    """Add deterministic evolution and optional AI analysis to a fresh CONS snapshot.

    Failures in optional analysis never invalidate the already generated consolidated
    report. The source AUD workspaces remain read-only throughout.
    """
    try:
        bundle = build_evolution(audits_root, filters)
    except Exception as exc:
        try:
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            manifest["evolution_analysis"] = {"contract": EVOLUTION_CONTRACT, "status": "UNAVAILABLE", "reason": f"{type(exc).__name__}: {str(exc)[:300]}"}
            result.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        except Exception:
            pass
        return result
    try:
        run = run_ai(bundle, filters, env=env) if filters.specialist_ai else SpecialistRun(False, "NOT_REQUESTED", "", (), ())
    except Exception as exc:
        run = SpecialistRun(True, "UNAVAILABLE", "", (), (), f"{type(exc).__name__}: {str(exc)[:300]}")
    try:
        _augment_report(result.report_path, bundle, run)
        _augment_manifest(result.manifest_path, filters, bundle, run)
        artifact = result.report_dir / "specialist-analysis.json"
        artifact.write_text(
            json.dumps({
                "contract": SPECIALIST_CONTRACT,
                "evolution_contract": EVOLUTION_CONTRACT,
                "comparison": {
                    "baseline_audit_id": bundle.comparison.baseline.audit_id,
                    "current_audit_id": bundle.comparison.current.audit_id,
                    "comparable": bundle.comparison.comparable,
                    "material_counts": bundle.comparison.material_counts,
                },
                "changes": list(bundle.events),
                "fix_verification": list(bundle.fixes),
                "ai": {
                    "requested": run.requested,
                    "status": run.status,
                    "summary": run.summary,
                    "topic_analyses": list(run.topic_analyses),
                    "attempts": [asdict(item) for item in run.attempts],
                    "reason": run.reason,
                },
            }, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except Exception:
        # The consolidated report is a derivative. Optional enrichment must fail open.
        return result
    return result
