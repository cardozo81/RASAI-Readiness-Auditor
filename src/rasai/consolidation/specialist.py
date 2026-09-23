"""Evolução determinística e análise longitudinal por IA para relatórios CONS-5.

Os workspaces AUD permanecem somente leitura. Monitoring e Fix Verification definem
os fatos; a IA obrigatória do consolidado interpreta apenas evidências persistidas e
não altera SARI, SCORE-GEO, findings nem bancos fonte.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
import os
import re
from pathlib import Path
import time
from typing import Any, Mapping
from urllib.error import HTTPError, URLError

from rasai.ai_cost_policy import CandidateCostEstimate, PRICING_VERSION, estimate_candidate_cost
from rasai.ai_task_profiles import profile_identity, render_task_profiles
from rasai.catalog_report_public_labels import public_label
from rasai.ai_execution_state import clear_current_ai_execution, current_ai_executions
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
from rasai.monitoring.models import AuditSnapshot, ChangeEvent, ComparisonResult
from rasai.monitoring.reader import read_audit_snapshot
from rasai.provider_extensions import _diagnostic_from_http as _extension_diagnostic_from_http
from rasai.provider_registry import get_provider_registration
from rasai.provider_runtime_policy import build_semantic_provider, provider_reasoning_env
from rasai.quality.verification import VerificationBundle, verify_fixes
from rasai.secret_safety import redact_value

from .catalog_longitudinal import CATALOG_LONGITUDINAL_CONTRACT, CatalogInterval, CatalogSnapshot, build_catalog_intervals
from .comparability import annotate_audit_configurations, configuration_comparability
from .governance import build_source_governance
from .index import ConsolidationIndex
from .models import ConsolidationFilter, GenerationResult

SPECIALIST_CONTRACT = "CONSOLIDATED-SPECIALIST-001"
LONGITUDINAL_CONTRACT = "CONSOLIDATED-LONGITUDINAL-001"
AI_SCOPE = "CONSOLIDATED_SPECIALIST"
MAX_AI_ROUNDS = 2  # rodada inicial + uma única rodada adicional
DEFAULT_RETRY_DELAY_SECONDS = 1.0
RATE_LIMIT_RETRY_DELAY_SECONDS = 5.0
MAX_RETRY_DELAY_SECONDS = 15.0
_RETRYABLE_ERROR_CLASSES = frozenset({
    ProviderErrorClass.RATE_LIMIT_ERROR,
    ProviderErrorClass.NETWORK_ERROR,
    ProviderErrorClass.TIMEOUT_ERROR,
    ProviderErrorClass.SERVER_ERROR,
    ProviderErrorClass.EMPTY_RESPONSE,
})
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
    excluded_candidates: tuple[str, ...] = ()
    forecast: dict[str, Any] | None = None
    context_projection: dict[str, Any] | None = None


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
    attempt_no: int = 1
    round_no: int = 1
    decision: str | None = None
    retry_eligible: bool = False
    fallback_from_provider: str | None = None
    fallback_reason: str | None = None
    error_code: str | None = None
    error_type: str | None = None
    retry_after_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class SpecialistRun:
    requested: bool
    status: str
    summary: str
    topic_analyses: tuple[dict[str, Any], ...]
    attempts: tuple[SpecialistAttempt, ...]
    reason: str | None = None
    interval_analyses: tuple[dict[str, Any], ...] = ()
    tradeoffs: tuple[dict[str, Any], ...] = ()
    strategy: dict[str, tuple[str, ...]] | None = None
    profile_id: str | None = None
    profile_version: str | None = None
    rounds: int = 0
    candidates: tuple[dict[str, Any], ...] = ()
    excluded_candidates: tuple[str, ...] = ()
    forecast: dict[str, Any] | None = None
    exchanges: tuple[dict[str, Any], ...] = ()
    context_projection: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EvolutionBundle:
    comparison: ComparisonResult
    verification: VerificationBundle
    baseline_workspace: Path
    current_workspace: Path
    events: tuple[dict[str, Any], ...]
    fixes: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LongitudinalBundle:
    url: str
    device: str
    audit_ids: tuple[str, ...]
    event_times: tuple[str, ...]
    intervals: tuple[EvolutionBundle, ...]
    global_evolution: EvolutionBundle
    catalog_snapshots: tuple[CatalogSnapshot, ...]
    catalog_intervals: tuple[CatalogInterval, ...]
    limitations: tuple[str, ...]
    governance: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LongitudinalPreparation:
    root_identity: str
    filter_identity: str
    source_fingerprint: str
    bundle: LongitudinalBundle
    full_packet: dict[str, Any]
    full_evidence_ids: tuple[str, ...]
    projected_packet: dict[str, Any]
    projected_evidence_ids: tuple[str, ...]
    context_projection: dict[str, Any]
    token_hint: SpecialistTokenHint


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


def build_evolution(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    baseline_snapshot: AuditSnapshot | None = None,
    current_snapshot: AuditSnapshot | None = None,
) -> EvolutionBundle:
    root = Path(audits_root)
    if (baseline_snapshot is None) != (current_snapshot is None):
        raise ValueError("baseline_snapshot e current_snapshot devem ser fornecidos em conjunto")
    if baseline_snapshot is None:
        baseline_row, current_row = _select_rows(root, filters)
        baseline_workspace = _workspace(root, baseline_row)
        current_workspace = _workspace(root, current_row)
        comparison = compare_audits(baseline_workspace, current_workspace)
    else:
        assert current_snapshot is not None
        baseline_workspace = baseline_snapshot.workspace
        current_workspace = current_snapshot.workspace
        comparison = compare_audits(
            baseline_workspace,
            current_workspace,
            baseline_snapshot=baseline_snapshot,
            current_snapshot=current_snapshot,
        )
    verification = verify_fixes(
        baseline_workspace,
        current_workspace,
        comparison=comparison,
    )

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


def _instructions() -> str:
    profile = render_task_profiles("EVOLUTION")
    return (
        profile
        + "\nRegras normativas do consolidado: interprete somente evidências persistidas fornecidas pelo RASAi. "
        "Responda somente em JSON e cumpra exatamente o schema. Não recalcule nem altere SARI/SCORE-GEO. "
        "Diferencie melhoria observada de correção verificada. Associação temporal não é causalidade. "
        "Não invente URLs, seletores, regras, métricas, vulnerabilidades, correções, causas, credenciais, "
        "estatísticas ou evidências. Segurança é exclusivamente passiva. Cite somente evidence_ids fornecidos. "
        "Escreva todo texto explicativo em português do Brasil. A decisão final permanece humana. "
        "Interprete source_audit_governance.conclusion_state de forma estrita: NON_CONCLUSIVE exige leitura não conclusiva/contextual "
        "e deve identificar somente AUDs realmente pendentes ou que requerem reprocessamento. CONCLUSIVE_WITH_LIMITATIONS significa que "
        "as AUDs estão finais e elegíveis, sem trabalho obrigatório pendente; explicite as limitações, mas não declare a série não conclusiva "
        "nem recomende reprocessamento sem evidência de trabalho pendente. CONCLUSIVE significa série final sem essa ressalva estrutural."
    )


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


def _public_attempt(attempt: ProviderAttempt, *, round_no: int) -> SpecialistAttempt:
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
        attempt_no=attempt.attempt_index,
        round_no=round_no,
        decision=attempt.decision,
        retry_eligible=bool(attempt.retry_eligible),
        fallback_from_provider=attempt.fallback_from_provider,
        fallback_reason=attempt.fallback_reason,
        error_code=getattr(diagnostic, "error_code", None) if diagnostic else None,
        error_type=getattr(diagnostic, "error_type", None) if diagnostic else None,
        retry_after_seconds=getattr(diagnostic, "retry_after_seconds", None) if diagnostic else None,
    )


def _candidate_view(item: CandidateCostEstimate) -> dict[str, Any]:
    return {
        "provider": item.provider,
        "model": item.model,
        "scope": item.scope,
        "reasoning_profile": item.reasoning_profile,
        "estimated_input_tokens": item.estimated_input_tokens,
        "estimated_cached_input_tokens": item.estimated_cached_input_tokens,
        "estimated_output_tokens": item.estimated_output_tokens,
        "estimated_cost": item.estimated_cost,
        "currency": item.currency,
        "pricing_context": item.pricing_context,
        "pricing_version": item.pricing_version,
        "basis": item.basis,
    }


def _forecast(estimates: tuple[CandidateCostEstimate, ...]) -> dict[str, Any]:
    priced = [item for item in estimates if item.estimated_cost is not None and item.currency]
    currencies = {str(item.currency) for item in priced}
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    expected = estimates[0].estimated_cost if estimates and estimates[0].estimated_cost is not None else None
    likely_low = min((float(item.estimated_cost) for item in priced), default=None)
    first_round = sum(float(item.estimated_cost) for item in priced) if priced and currency else None
    potential = (first_round * MAX_AI_ROUNDS) if first_round is not None else None
    pricing_coverage = (len(priced) / len(estimates)) if estimates else 0.0
    # Pricing coverage can be complete while token/output volume remains a pre-execution
    # estimate. Do not call that financial forecast "ALTA" without observed calibration.
    confidence = "MÉDIA" if estimates and len(priced) == len(estimates) and currency else ("BAIXA" if priced else "NENHUMA")
    return {
        "pricing_version": PRICING_VERSION,
        "currency": currency,
        "expected_cost": float(expected) if expected is not None else None,
        "likely_low": likely_low,
        "likely_high": first_round,
        "potential": potential,
        "confidence": confidence,
        "confidence_basis": (
            "preços conhecidos; volume de tokens/saída permanece estimado antes da execução"
            if priced else
            "sem cobertura de preço suficiente para estimativa financeira"
        ),
        "pricing_coverage": pricing_coverage,
        "max_rounds": MAX_AI_ROUNDS,
        "candidate_count": len(estimates),
        "unpriced_candidates": len(estimates) - len(priced),
        "candidates": [_candidate_view(item) for item in estimates],
    }


def _retryable(diagnostic: ProviderDiagnostic | None) -> bool:
    return bool(diagnostic is not None and diagnostic.error_class in _RETRYABLE_ERROR_CLASSES)


def _chain_failure_reason(attempts: list[tuple[ProviderAttempt, int]]) -> str:
    latest_by_provider: dict[str, ProviderAttempt] = {}
    for attempt, _round_no in attempts:
        latest_by_provider[attempt.provider] = attempt
    parts: list[str] = []
    for provider, attempt in latest_by_provider.items():
        diagnostic = attempt.diagnostic
        if diagnostic is None:
            parts.append(f"{provider}: indisponível")
            continue
        detail = diagnostic.reason
        parts.append(f"{provider}: {detail}")
    return " | ".join(parts) if parts else "cadeia de provedores de IA esgotada"


def _retry_delay(attempts: list[tuple[ProviderAttempt, int]], round_no: int) -> float:
    explicit_delays: list[float] = []
    has_rate_limit = False
    for item, item_round in attempts:
        if item_round != round_no or not item.retry_eligible or item.diagnostic is None:
            continue
        if item.diagnostic.error_class is ProviderErrorClass.RATE_LIMIT_ERROR:
            has_rate_limit = True
        retry_after = item.diagnostic.retry_after_seconds
        if retry_after is None:
            continue
        try:
            delay = float(retry_after)
        except (TypeError, ValueError):
            continue
        if delay >= 0:
            explicit_delays.append(delay)

    if explicit_delays:
        suggested = max(explicit_delays)
        if has_rate_limit:
            suggested = max(suggested, RATE_LIMIT_RETRY_DELAY_SECONDS)
    elif has_rate_limit:
        suggested = RATE_LIMIT_RETRY_DELAY_SECONDS
    else:
        suggested = DEFAULT_RETRY_DELAY_SECONDS

    return max(
        DEFAULT_RETRY_DELAY_SECONDS,
        min(suggested, MAX_RETRY_DELAY_SECONDS),
    )


def _capture_ai_exchanges() -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    for execution in current_ai_executions():
        recorder = getattr(execution, "recorder", None)
        if recorder is None:
            continue
        for item in getattr(recorder, "exchanges", ()):
            output.append(asdict(item))
    output.sort(key=lambda item: (int(item.get("sequence_no") or 0), str(item.get("started_at") or "")))
    return tuple(output)



def _replace_decision(attempt: ProviderAttempt, decision: str) -> ProviderAttempt:
    from dataclasses import replace
    return replace(attempt, decision=decision)


def _replace_attempt(attempt: ProviderAttempt, *, fallback_from: str, fallback_reason: str | None) -> ProviderAttempt:
    from dataclasses import replace
    return replace(attempt, fallback_from_provider=fallback_from, fallback_reason=fallback_reason)


_HUMAN_TERMS = {
    "Answerability": "Capacidade de resposta",
    "Citation Readiness": "Preparação para citação",
    "Structured Data": "Dados estruturados",
    "Evidence & Trust": "Evidências e confiabilidade",
    "Intent Coverage": "Cobertura de intenções",
    "Entity Clarity": "Clareza de entidades",
    "Semantic Structure": "Estrutura semântica",
    "Content Value": "Valor do conteúdo",
    "Discovery & Crawler Access": "Acesso e descoberta",
    "Rendering & Extractability": "Renderização e extração",
    "Indexability": "Indexabilidade e canonicalização",
    "Lighthouse Performance": "Lighthouse Performance",
    "TBT lab": "Total Blocking Time",
    "LCP lab": "LCP de laboratório",
    "FCP lab": "FCP de laboratório",
    "CLS lab": "CLS de laboratório",
    "PASS": "Aprovado",
    "FAIL": "Não aprovado",
    "WARNING": "Atenção",
    "NOT_APPLICABLE": "Não aplicável",
    "UNAVAILABLE": "Indisponível",
    "COMPLETE": "Completo",
    "COMPLETED": "Concluído",
    "INCOMPLETE": "Incompleto",
    "PARTIAL": "Parcial",
    "CONSOLIDATED": "Consolidado",
    "MOBILE": "Dispositivo móvel",
    "DESKTOP": "Desktop",
    "OVERALL_READINESS": "SARI - Índice de prontidão para Busca e IA",
    "Overall Readiness Score": "SARI - Índice de prontidão para Busca e IA",
    "Performance Score": "Lighthouse Performance",
    "Accessibility Score": "Lighthouse Accessibility",
    "Best Practices Score": "Lighthouse Best Practices",
    "SEO Score": "Lighthouse SEO",
    "DISCOVERY_ACCESS": "Acesso e descoberta",
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Indexabilidade e canonicalização",
    "CONTENT_EXTRACTABILITY": "Renderização e extração",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
    "CONTENT_VALUE": "Valor do conteúdo",
    "Lighthouse Accessibility": "Lighthouse Accessibility",
    "Lighthouse SEO": "SEO Lighthouse",
    "Best Practices Lighthouse": "Lighthouse Best Practices",
    "Synthetic Navigation Apdex": "Apdex de navegação",
    "Synthetic User Experience Apdex": "Apdex de experiência",
    "Synthetic navigation mean": "Média da navegação sintética",
    "Synthetic navigation p95": "p95 da navegação sintética",
    "HTTP status": "Status HTTP",
    "Final URL": "URL final",
    "Canonical": "URL canônica",
    "Meta robots": "Diretiva meta robots",
    "Title": "Título",
}


def _human_term(value: Any) -> str:
    text = str(value or "")
    return public_label(text) or _HUMAN_TERMS.get(text) or text


def _event_indicator_label(item: Mapping[str, Any]) -> str:
    domain = str(item.get("domain") or "").upper()
    raw = str(item.get("label") or "-")
    if domain == "APDEX":
        labels = {
            "Synthetic Navigation Apdex": "Apdex de navegação",
            "Apdex Score": "Apdex de navegação",
            "Synthetic navigation mean": "Média da navegação sintética",
            "Synthetic navigation p95": "p95 da navegação sintética",
        }
        return labels.get(raw, _human_term(raw))
    if domain == "UX_APDEX":
        return "Apdex de experiência" if "Apdex" in raw else _human_term(raw)
    if domain == "FINDINGS" and raw.upper().endswith(" FINDINGS"):
        severity = raw[:-9].strip().upper()
        label = {
            "CRITICAL": "Ocorrências críticas",
            "HIGH": "Ocorrências de severidade alta",
            "MEDIUM": "Ocorrências de severidade média",
            "LOW": "Ocorrências de severidade baixa",
            "INFO": "Ocorrências informativas",
        }.get(severity)
        if label:
            return label
    return _human_term(raw)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return _human_term(value)


def _longitudinal_rows(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    index: ConsolidationIndex | None = None,
) -> tuple[dict[str, Any], ...]:
    if len(filters.urls) != 1:
        raise ValueError("o relatório consolidado exige exatamente uma URL")
    if len(filters.devices) != 1:
        raise ValueError("o relatório consolidado exige exatamente um dispositivo")
    effective_index = index or ConsolidationIndex(audits_root)
    rows = effective_index.candidate_audits(filters)
    if len(rows) < 2:
        raise ValueError("o relatório consolidado exige pelo menos duas auditorias elegíveis da mesma URL e dispositivo")
    selected_device = filters.devices[0].upper()
    for row in rows:
        if int(row.get("url_count") or 0) != 1:
            raise ValueError(
                f"{row.get('audit_id')}: o consolidado por URL exige auditoria com uma única URL persistida"
            )
        try:
            devices = {str(item).upper() for item in json.loads(str(row.get("devices_json") or "[]"))}
        except (TypeError, ValueError, json.JSONDecodeError):
            devices = set()
        if devices != {selected_device}:
            raise ValueError(
                f"{row.get('audit_id')}: conjunto de dispositivos incompatível com o consolidado {selected_device}"
            )
    return rows


def build_longitudinal(audits_root: str | Path, filters: ConsolidationFilter) -> LongitudinalBundle:
    root = Path(audits_root)
    rows = _longitudinal_rows(root, filters)
    intervals: list[EvolutionBundle] = []
    workspaces: list[Path] = []
    for row in rows:
        rel = Path(str(row["db_path"]))
        workspace = (root / rel).parent if not rel.is_absolute() else rel.parent
        workspaces.append(workspace)
    audit_snapshots = tuple(read_audit_snapshot(workspace) for workspace in workspaces)
    snapshot_by_workspace = {
        str(workspace.resolve()): snapshot
        for workspace, snapshot in zip(workspaces, audit_snapshots)
    }
    for index in range(1, len(rows)):
        pair = replace(
            filters,
            comparison_mode="MANUAL",
            baseline_audit_id=str(rows[index - 1]["audit_id"]),
            current_audit_id=str(rows[index]["audit_id"]),
        )
        intervals.append(
            build_evolution(
                root,
                pair,
                baseline_snapshot=audit_snapshots[index - 1],
                current_snapshot=audit_snapshots[index],
            )
        )
    global_pair = replace(
        filters,
        comparison_mode="MANUAL",
        baseline_audit_id=str(rows[0]["audit_id"]),
        current_audit_id=str(rows[-1]["audit_id"]),
    )
    global_evolution = build_evolution(
        root,
        global_pair,
        baseline_snapshot=audit_snapshots[0],
        current_snapshot=audit_snapshots[-1],
    )
    snapshots, catalog_intervals = build_catalog_intervals(
        tuple(workspaces),
        url=filters.urls[0],
        device=filters.devices[0],
        audit_snapshots=snapshot_by_workspace,
    )
    limitations: list[str] = []
    for item in intervals:
        limitations.extend(item.limitations)
    governance = build_source_governance(root, rows)
    configured_rows = annotate_audit_configurations(root, rows)
    governance["configuration_comparability"] = configuration_comparability(
        configured_rows,
        comparison_mode=filters.comparison_mode,
        baseline_audit_id=filters.baseline_audit_id,
        current_audit_id=filters.current_audit_id,
    )
    for overlap in governance.get("temporal_revision_overlaps", ()):
        if not isinstance(overlap, Mapping):
            continue
        mode = str(overlap.get("revision_mode") or "UNKNOWN").upper()
        audit_id = str(overlap.get("audit_id") or "")
        next_audit_id = str(overlap.get("next_audit_id") or "")
        revision_at = str(overlap.get("revision_at") or "")
        if mode == "REPLAY_SAFE":
            limitations.append(
                f"{audit_id} recebeu revisão REPLAY_SAFE em {revision_at} após a observação de {next_audit_id}; "
                "dados derivados dessa revisão reutilizam evidência persistida da observação original e devem ser lidos "
                "como revisão posterior, não como nova observação temporal."
            )
        elif mode == "LIVE_RECOLLECTION":
            limitations.append(
                f"{audit_id} recebeu LIVE_RECOLLECTION em {revision_at} após a observação de {next_audit_id}; "
                "dados afetados por essa recoleta não representam necessariamente o estado cronológico original do marco "
                "e exigem qualificação temporal explícita."
            )
        else:
            limitations.append(
                f"{audit_id} recebeu revisão posterior à observação de {next_audit_id}, mas o modo temporal do RPR "
                "não pôde ser comprovado; a comparação correspondente exige revisão manual."
            )
    conclusion_state = str(governance.get("conclusion_state") or "NON_CONCLUSIVE")
    if conclusion_state == "NON_CONCLUSIVE":
        limitations.append(
            "Uma ou mais auditorias fonte não possuem encerramento comprovadamente final; "
            "a interpretação longitudinal deve permanecer não conclusiva até regularização das fontes."
        )
    elif conclusion_state == "CONCLUSIVE_WITH_LIMITATIONS":
        limitations.append(
            "As auditorias fonte possuem encerramento final e são elegíveis para consolidação, "
            "mas registram limitações não bloqueantes que devem permanecer explícitas na interpretação."
        )
    return LongitudinalBundle(
        url=filters.urls[0],
        device=filters.devices[0].upper(),
        audit_ids=tuple(str(row["audit_id"]) for row in rows),
        event_times=tuple(str(row["event_time"]) for row in rows),
        intervals=tuple(intervals),
        global_evolution=global_evolution,
        catalog_snapshots=snapshots,
        catalog_intervals=catalog_intervals,
        limitations=tuple(dict.fromkeys(limitations)),
        governance=governance,
    )


def _compact_catalog_state(snapshot: CatalogSnapshot) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for catalog in snapshot.catalogs:
        output.append({
            "catalog_id": catalog.get("catalog_id"),
            "label": catalog.get("label"),
            "purpose": catalog.get("purpose"),
            "expected_result": catalog.get("expected_result"),
            "status": catalog.get("status"),
            "status_detail": catalog.get("status_detail"),
            "metrics": list(catalog.get("metrics") or ()),
            "sources": list(catalog.get("sources") or ()),
            "configuration": list(catalog.get("configuration") or ()),
        })
    return output


def _compact_catalog_change(item: Mapping[str, Any]) -> dict[str, Any]:
    copied = dict(item)
    evidence = copied.get("evidence")
    if isinstance(evidence, Mapping):
        compact = dict(evidence)
        for field in ("added", "removed"):
            values = compact.get(field)
            if isinstance(values, list):
                compact[field] = values[:5]
                if len(values) > 5:
                    compact[f"{field}_examples_limited"] = True
        copied["evidence"] = compact
    return copied


def _longitudinal_packet(bundle: LongitudinalBundle) -> tuple[dict[str, Any], tuple[str, ...]]:
    interval_payloads: list[dict[str, Any]] = []
    allowed: list[str] = []
    for pos, pair in enumerate(bundle.intervals, 1):
        prefix = f"I{pos:03d}"
        events = []
        for item in pair.events:
            copied = dict(item)
            copied["evidence_id"] = f"{prefix}-{item['evidence_id']}"
            allowed.append(str(copied["evidence_id"]))
            events.append(copied)
        fixes = []
        for item in pair.fixes:
            copied = dict(item)
            copied["evidence_id"] = f"{prefix}-{item['evidence_id']}"
            allowed.append(str(copied["evidence_id"]))
            fixes.append(copied)
        catalog_interval = bundle.catalog_intervals[pos - 1]
        catalog_changes = []
        for change_index, item in enumerate(catalog_interval.changes, 1):
            copied = dict(item)
            copied["evidence_id"] = f"{prefix}-CAT-{change_index:04d}"
            allowed.append(str(copied["evidence_id"]))
            catalog_changes.append(copied)
        interval_payloads.append({
            "interval_id": catalog_interval.interval_id,
            "baseline": {
                "audit_id": pair.comparison.baseline.audit_id,
                "event_time": pair.comparison.baseline.event_time,
            },
            "current": {
                "audit_id": pair.comparison.current.audit_id,
                "event_time": pair.comparison.current.event_time,
            },
            "comparable": pair.comparison.comparable,
            "limitations": list(pair.limitations),
            "changes": events,
            "fix_verification": fixes,
            "catalog_changes": catalog_changes,
            "stable_within_expected": catalog_interval.stable_expected,
            "stable_requiring_attention": catalog_interval.stable_attention,
        })
    global_events = []
    for item in bundle.global_evolution.events:
        copied = dict(item)
        copied["evidence_id"] = f"GLOBAL-{item['evidence_id']}"
        allowed.append(str(copied["evidence_id"]))
        global_events.append(copied)
    global_fixes = []
    for item in bundle.global_evolution.fixes:
        copied = dict(item)
        copied["evidence_id"] = f"GLOBAL-{item['evidence_id']}"
        allowed.append(str(copied["evidence_id"]))
        global_fixes.append(copied)
    packet = {
        "contract": LONGITUDINAL_CONTRACT,
        "catalog_contract": CATALOG_LONGITUDINAL_CONTRACT,
        "scope": {
            "url": bundle.url,
            "device": bundle.device,
            "audit_count": len(bundle.audit_ids),
            "audit_ids": list(bundle.audit_ids),
            "event_times": list(bundle.event_times),
        },
        "intervals": interval_payloads,
        "initial_to_final": {
            "baseline_audit_id": bundle.global_evolution.comparison.baseline.audit_id,
            "current_audit_id": bundle.global_evolution.comparison.current.audit_id,
            "changes": global_events,
            "fix_verification": global_fixes,
            "limitations": list(bundle.global_evolution.limitations),
        },
        "catalog_state_initial": list(bundle.catalog_snapshots[0].catalogs),
        "catalog_state_final": list(bundle.catalog_snapshots[-1].catalogs),
        "governance": {
            "source": "somente dados persistidos das auditorias selecionadas",
            "recollection": False,
            "sari_score_impact": "nenhum",
            "causal_claims_without_evidence": "proibido",
            "security_mode": "somente passivo",
            "human_review_required": True,
            "source_audit_governance": bundle.governance,
        },
    }
    return packet, tuple(dict.fromkeys(allowed))


AI_CONTEXT_CONTRACT = "CONSOLIDATED-AI-CONTEXT-001"
AI_MAX_INPUT_HINT_TOKENS = 80_000
_AI_TEXT_SHORT = 420
_AI_TEXT_MEDIUM = 900
_AI_TEXT_LONG = 1600


def _ai_text(value: Any, limit: int = _AI_TEXT_SHORT) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _ai_value(value: Any, *, text_limit: int = _AI_TEXT_SHORT, list_limit: int = 10) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _ai_text(value, text_limit)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in list(value.items())[:20]:
            output[str(key)] = _ai_value(item, text_limit=text_limit, list_limit=list_limit)
        return output
    if isinstance(value, (list, tuple)):
        return [
            _ai_value(item, text_limit=text_limit, list_limit=list_limit)
            for item in list(value)[:list_limit]
        ]
    return _ai_text(value, text_limit)


def _ai_technical_finding(item: Mapping[str, Any]) -> dict[str, Any]:
    affected = []
    for element in item.get("affected_elements", ())[:1]:
        if not isinstance(element, Mapping):
            continue
        affected.append({
            "selector": _ai_text(element.get("selector"), 260),
            "tag_name": _ai_text(element.get("tag_name"), 60),
            "outer_html": _ai_text(element.get("outer_html"), 650),
            "text_excerpt": _ai_text(element.get("text_excerpt"), 360),
        })
    return {
        "evidence_id": item.get("evidence_id"),
        "rule_id": item.get("rule_id"),
        "url": item.get("url"),
        "device": item.get("device"),
        "severity": item.get("severity"),
        "evolution_status": item.get("evolution_status"),
        "relevant_to_material_change": item.get("relevant_to_material_change"),
        "finding_title": _ai_text(item.get("finding_title"), 260),
        "cause_type": _ai_text(item.get("cause_type"), 120),
        "cause_summary": _ai_text(item.get("cause_summary"), _AI_TEXT_MEDIUM),
        "observed_value": _ai_value(item.get("observed_value"), text_limit=500, list_limit=5),
        "expected_condition": _ai_text(item.get("expected_condition"), 500),
        "exact_change": _ai_text(item.get("exact_change"), _AI_TEXT_LONG),
        "example_after": _ai_text(item.get("example_after"), 900),
        "acceptance_criteria": _ai_value(item.get("acceptance_criteria"), text_limit=360, list_limit=5),
        "revalidation_steps": _ai_value(item.get("revalidation_steps"), text_limit=360, list_limit=5),
        "affected_elements": affected,
    }


def _ai_rule_reference(item: Mapping[str, Any]) -> dict[str, Any]:
    remediation = item.get("remediation") if isinstance(item.get("remediation"), Mapping) else {}
    return {
        "rule_id": item.get("rule_id"),
        "tooltip": _ai_text(item.get("tooltip"), 420),
        "remediation": {
            "title": _ai_text(remediation.get("title"), 220),
            "target": _ai_text(remediation.get("target"), 140),
            "element": _ai_text(remediation.get("element"), 140),
            "location": _ai_text(remediation.get("location"), 180),
            "action": _ai_text(remediation.get("action"), 420),
            "description": _ai_text(remediation.get("description"), 650),
            "example": _ai_text(remediation.get("example"), 650),
            "acceptance": _ai_value(remediation.get("acceptance"), text_limit=300, list_limit=5),
            "validation": _ai_value(remediation.get("validation"), text_limit=300, list_limit=5),
            "human_decision": _ai_text(remediation.get("human_decision"), 360),
        },
    }


def _ai_catalog_evidence(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return _ai_value(value, text_limit=220, list_limit=2)
    output: dict[str, Any] = {}
    for key in ("added_count", "removed_count", "count", "state", "source", "methodology"):
        if key in value:
            output[key] = _ai_value(value.get(key), text_limit=180, list_limit=2)
    for key in ("added", "removed"):
        values = value.get(key)
        if isinstance(values, list) and values:
            output[f"{key}_example"] = _ai_value(values[0], text_limit=220, list_limit=2)
    return output


def _ai_catalog_change(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "evidence_id": item.get("evidence_id"),
        "catalog_id": item.get("catalog_id"),
        "catalog_label": _ai_text(item.get("catalog_label"), 160),
        "label": _ai_text(item.get("label"), 220),
        "category": _ai_text(item.get("category"), 100),
        "status": item.get("status"),
        "before": _ai_value(item.get("before"), text_limit=260, list_limit=3),
        "after": _ai_value(item.get("after"), text_limit=260, list_limit=3),
        "delta": item.get("delta"),
        "delta_percent": item.get("delta_percent"),
        "unit": item.get("unit"),
        "detail": _ai_text(item.get("detail"), 300),
        "reason": _ai_text(item.get("reason"), 280),
        "evidence": _ai_catalog_evidence(item.get("evidence")),
    }


def _ai_metric_summary(value: Any) -> dict[str, Any]:
    metrics = [item for item in (value or ()) if isinstance(item, Mapping)]
    state_counts: dict[str, int] = {}
    for item in metrics:
        state = str(item.get("state") or item.get("status") or "SEM_ESTADO")
        state_counts[state] = state_counts.get(state, 0) + 1
    examples = []
    for item in metrics[:6]:
        examples.append({
            "metric_id": _ai_text(item.get("metric_id"), 160),
            "label": _ai_text(item.get("label"), 180),
            "state": _ai_text(item.get("state") or item.get("status"), 80),
            "value": _ai_value(item.get("value"), text_limit=160, list_limit=2),
            "unit": _ai_text(item.get("unit"), 60),
        })
    return {
        "count": len(metrics),
        "states": dict(sorted(state_counts.items())),
        "examples": examples,
    }


def _ai_catalog_state(values: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in values or ():
        if not isinstance(item, Mapping):
            continue
        output.append({
            "catalog_id": item.get("catalog_id"),
            "label": _ai_text(item.get("label"), 160),
            "purpose": _ai_text(item.get("purpose"), 220),
            "expected_result": _ai_text(item.get("expected_result"), 220),
            "status": item.get("status"),
            "status_detail": _ai_text(item.get("status_detail"), 280),
            "metrics": _ai_metric_summary(item.get("metrics")),
            "configuration": _ai_value(item.get("configuration"), text_limit=260, list_limit=16),
            "effective_external_state": _ai_value(item.get("effective_external_state"), text_limit=360, list_limit=8),
        })
    return output


def _ai_status_counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in values or ():
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or item.get("evolution_status") or "SEM_ESTADO")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _ai_catalog_counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in values or ():
        if not isinstance(item, Mapping):
            continue
        catalog = str(item.get("catalog_id") or "SEM_CATALOGO")
        counts[catalog] = counts.get(catalog, 0) + 1
    return dict(sorted(counts.items()))


def _ai_priority(item: Mapping[str, Any]) -> tuple[int, int, str]:
    status = str(item.get("status") or item.get("evolution_status") or "").upper()
    severity = str(item.get("severity") or "").upper()
    status_rank = {
        "REGRESSED": 0,
        "NEW": 1,
        "NOVO": 1,
        "PERSISTENTE_ATENCAO": 2,
        "STILL_FAILING": 2,
        "CONFIGURACAO_ALTERADA": 3,
        "DATA_UNAVAILABLE": 4,
        "DADO_INDISPONIVEL": 4,
        "NOT_COMPARABLE": 5,
        "CHANGED": 6,
        "ALTERADO": 6,
        "PARTIALLY_FIXED": 7,
        "FIXED": 8,
        "RESOLVED": 8,
        "IMPROVED": 9,
    }.get(status, 20)
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}.get(severity, 9)
    return status_rank, severity_rank, str(item.get("evidence_id") or item.get("rule_id") or item.get("label") or "")


def _ai_select(values: Any, limit: int) -> list[Mapping[str, Any]]:
    material = [item for item in (values or ()) if isinstance(item, Mapping)]
    material.sort(key=_ai_priority)
    return material[:max(0, limit)]


def _collect_evidence_ids(value: Any, output: list[str]) -> None:
    if isinstance(value, Mapping):
        evidence_id = value.get("evidence_id")
        if evidence_id:
            output.append(str(evidence_id))
        for item in value.values():
            _collect_evidence_ids(item, output)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _collect_evidence_ids(item, output)


def _ai_project_with_limits(
    packet: Mapping[str, Any],
    *,
    level: str,
    interval_changes: int,
    interval_fixes: int,
    catalog_changes: int,
    interval_technical: int,
    global_changes: int,
    global_fixes: int,
    global_technical: int,
    rule_references: int,
) -> tuple[dict[str, Any], tuple[str, ...], dict[str, Any]]:
    intervals: list[dict[str, Any]] = []
    interval_coverage: list[dict[str, Any]] = []
    packet_governance = packet.get("governance") if isinstance(packet.get("governance"), Mapping) else {}
    source_governance = (
        packet_governance.get("source_audit_governance")
        if isinstance(packet_governance.get("source_audit_governance"), Mapping)
        else {}
    )
    configuration = (
        source_governance.get("configuration_comparability")
        if isinstance(source_governance.get("configuration_comparability"), Mapping)
        else {}
    )
    configuration_pair_status = str(configuration.get("pair_status") or "INSUFFICIENT_DATA").upper()
    for raw in packet.get("intervals", ()):
        if not isinstance(raw, Mapping):
            continue
        raw_changes = [item for item in raw.get("changes", ()) if isinstance(item, Mapping)]
        raw_fixes = [item for item in raw.get("fix_verification", ()) if isinstance(item, Mapping)]
        raw_catalog = [item for item in raw.get("catalog_changes", ()) if isinstance(item, Mapping)]
        raw_technical = [item for item in raw.get("current_technical_findings", ()) if isinstance(item, Mapping)]
        selected_changes = _ai_select(raw_changes, interval_changes)
        selected_fixes = _ai_select(raw_fixes, interval_fixes)
        selected_catalog = _ai_select(raw_catalog, catalog_changes)
        selected_technical = _ai_select(raw_technical, interval_technical)
        intervals.append({
            "interval_id": raw.get("interval_id"),
            "baseline": _ai_value(raw.get("baseline"), text_limit=240, list_limit=6),
            "current": _ai_value(raw.get("current"), text_limit=240, list_limit=6),
            "scope_comparable": raw.get("comparable"),
            "configuration_pair_status": configuration_pair_status,
            "limitations": _ai_value(raw.get("limitations"), text_limit=360, list_limit=8),
            "changes": [_ai_value(item, text_limit=500, list_limit=8) for item in selected_changes],
            "fix_verification": [_ai_value(item, text_limit=500, list_limit=8) for item in selected_fixes],
            "catalog_changes": [_ai_catalog_change(item) for item in selected_catalog],
            "stable_within_expected": raw.get("stable_within_expected"),
            "stable_requiring_attention": raw.get("stable_requiring_attention"),
            "current_technical_findings": [_ai_technical_finding(item) for item in selected_technical],
            "coverage": {
                "changes_total": len(raw_changes),
                "changes_sent": len(selected_changes),
                "changes_by_status": _ai_status_counts(raw_changes),
                "fixes_total": len(raw_fixes),
                "fixes_sent": len(selected_fixes),
                "catalog_changes_total": len(raw_catalog),
                "catalog_changes_sent": len(selected_catalog),
                "catalog_changes_by_catalog": _ai_catalog_counts(raw_catalog),
                "catalog_changes_by_status": _ai_status_counts(raw_catalog),
                "technical_findings_total": len(raw_technical),
                "technical_findings_sent": len(selected_technical),
            },
        })
        interval_coverage.append({
            "interval_id": raw.get("interval_id"),
            "changes_total": len(raw_changes),
            "changes_sent": len(selected_changes),
            "fixes_total": len(raw_fixes),
            "fixes_sent": len(selected_fixes),
            "catalog_changes_total": len(raw_catalog),
            "catalog_changes_sent": len(selected_catalog),
            "technical_findings_total": len(raw_technical),
            "technical_findings_sent": len(selected_technical),
            "catalogs_with_changes": _ai_catalog_counts(raw_catalog),
        })

    initial = packet.get("initial_to_final") if isinstance(packet.get("initial_to_final"), Mapping) else {}
    raw_global_changes = [item for item in initial.get("changes", ()) if isinstance(item, Mapping)]
    raw_global_fixes = [item for item in initial.get("fix_verification", ()) if isinstance(item, Mapping)]
    raw_global_technical = [item for item in initial.get("current_technical_findings", ()) if isinstance(item, Mapping)]
    selected_global_changes = _ai_select(raw_global_changes, global_changes)
    selected_global_fixes = _ai_select(raw_global_fixes, global_fixes)
    selected_global_technical = _ai_select(raw_global_technical, global_technical)
    raw_refs = [item for item in packet.get("rule_reference", ()) if isinstance(item, Mapping)]
    selected_refs = raw_refs[:max(0, rule_references)]

    projected = {
        "contract": packet.get("contract"),
        "catalog_contract": packet.get("catalog_contract"),
        "ai_context_contract": AI_CONTEXT_CONTRACT,
        "scope": _ai_value(packet.get("scope"), text_limit=240, list_limit=20),
        "intervals": intervals,
        "initial_to_final": {
            "baseline_audit_id": initial.get("baseline_audit_id"),
            "current_audit_id": initial.get("current_audit_id"),
            "changes": [_ai_value(item, text_limit=500, list_limit=8) for item in selected_global_changes],
            "fix_verification": [_ai_value(item, text_limit=500, list_limit=8) for item in selected_global_fixes],
            "limitations": _ai_value(initial.get("limitations"), text_limit=360, list_limit=8),
            "current_technical_findings": [_ai_technical_finding(item) for item in selected_global_technical],
            "coverage": {
                "changes_total": len(raw_global_changes),
                "changes_sent": len(selected_global_changes),
                "changes_by_status": _ai_status_counts(raw_global_changes),
                "fixes_total": len(raw_global_fixes),
                "fixes_sent": len(selected_global_fixes),
                "technical_findings_total": len(raw_global_technical),
                "technical_findings_sent": len(selected_global_technical),
            },
        },
        "catalog_state_initial": _ai_catalog_state(packet.get("catalog_state_initial")),
        "catalog_state_final": _ai_catalog_state(packet.get("catalog_state_final")),
        "rule_reference": [_ai_rule_reference(item) for item in selected_refs],
        "governance": _ai_value(packet.get("governance"), text_limit=360, list_limit=16),
    }
    evidence_ids: list[str] = []
    _collect_evidence_ids(projected, evidence_ids)
    meta = {
        "contract": AI_CONTEXT_CONTRACT,
        "level": level,
        "max_input_hint_tokens": AI_MAX_INPUT_HINT_TOKENS,
        "intervals": interval_coverage,
        "global": projected["initial_to_final"]["coverage"],
        "rule_references_total": len(raw_refs),
        "rule_references_sent": len(selected_refs),
        "catalogs_initial": [item.get("catalog_id") for item in projected["catalog_state_initial"]],
        "catalogs_final": [item.get("catalog_id") for item in projected["catalog_state_final"]],
        "source_is_complete_locally": True,
        "projection_is_lossy_for_ai": True,
        "full_evidence_artifact": "longitudinal-evidence.json",
    }
    projected["context_projection"] = meta
    return projected, tuple(dict.fromkeys(evidence_ids)), meta


def _ai_packet_projection(packet: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...], dict[str, Any]]:
    tiers = (
        ("BALANCED", 80, 40, 48, 6, 100, 50, 10, 32),
        ("COMPACT", 50, 24, 32, 5, 70, 32, 8, 24),
        ("STRICT", 30, 16, 20, 4, 45, 20, 6, 18),
        ("MINIMAL", 16, 8, 10, 3, 24, 10, 4, 10),
        ("EMERGENCY", 8, 4, 5, 2, 12, 5, 2, 6),
    )
    last: tuple[dict[str, Any], tuple[str, ...], dict[str, Any]] | None = None
    for tier in tiers:
        level, ic, iff, cc, it, gc, gf, gt, rr = tier
        projected, evidence_ids, meta = _ai_project_with_limits(
            packet,
            level=level,
            interval_changes=ic,
            interval_fixes=iff,
            catalog_changes=cc,
            interval_technical=it,
            global_changes=gc,
            global_fixes=gf,
            global_technical=gt,
            rule_references=rr,
        )
        hint = _token_hint(projected)
        meta["estimated_input_tokens"] = hint.estimated_input_tokens
        meta["estimated_output_tokens"] = hint.estimated_output_tokens
        projected["context_projection"] = meta
        last = (projected, evidence_ids, meta)
        if hint.estimated_input_tokens <= AI_MAX_INPUT_HINT_TOKENS:
            return last
    if last is None:
        raise ValueError("não foi possível construir o contexto longitudinal da IA")
    if int(last[2].get("estimated_input_tokens") or 0) > AI_MAX_INPUT_HINT_TOKENS:
        raise ValueError(
            "o contexto longitudinal permanece acima do limite seguro mesmo após projeção mínima"
        )
    return last



def _longitudinal_schema(evidence_ids: tuple[str, ...], interval_ids: tuple[str, ...]) -> dict[str, Any]:
    evidence_item: dict[str, Any] = {"type": "string"}
    if evidence_ids:
        evidence_item["enum"] = list(evidence_ids)
    evidence_array = {
        "type": "array",
        "uniqueItems": True,
        "maxItems": 50,
        "items": evidence_item,
    }
    interval = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "interval_id", "assessment", "evidence_level", "benefited_indicators",
            "harmed_indicators", "stable_indicators", "recommended_path", "evidence_ids",
        ],
        "properties": {
            "interval_id": {"type": "string", "enum": list(interval_ids)},
            "assessment": {"type": "string", "maxLength": 5000},
            "evidence_level": {
                "type": "string",
                "enum": ["EVIDENCIA_DIRETA", "ASSOCIACAO_FORTE", "ASSOCIACAO_POSSIVEL", "INDETERMINADO"],
            },
            "benefited_indicators": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 500}},
            "harmed_indicators": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 500}},
            "stable_indicators": {"type": "array", "maxItems": 30, "items": {"type": "string", "maxLength": 500}},
            "recommended_path": {"type": "string", "maxLength": 5000},
            "evidence_ids": evidence_array,
        },
    }
    topic = {
        "type": "object",
        "additionalProperties": False,
        "required": ["topic", "assessment", "cause_analysis", "recommended_actions", "priority", "confidence", "evidence_ids"],
        "properties": {
            "topic": {"type": "string", "enum": list(_TOPIC_ORDER)},
            "assessment": {"type": "string", "maxLength": 5000},
            "cause_analysis": {"type": "string", "maxLength": 5000},
            "recommended_actions": {"type": "array", "maxItems": 12, "items": {"type": "string", "maxLength": 1600}},
            "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "evidence_ids": evidence_array,
        },
    }
    tradeoff = {
        "type": "object",
        "additionalProperties": False,
        "required": ["title", "assessment", "affected_topics", "recommended_path", "evidence_ids"],
        "properties": {
            "title": {"type": "string", "maxLength": 500},
            "assessment": {"type": "string", "maxLength": 4000},
            "affected_topics": {"type": "array", "maxItems": len(_TOPIC_ORDER), "items": {"type": "string", "enum": list(_TOPIC_ORDER)}},
            "recommended_path": {"type": "string", "maxLength": 4000},
            "evidence_ids": evidence_array,
        },
    }
    strategy = {
        "type": "object",
        "additionalProperties": False,
        "required": ["preservar", "corrigir", "otimizar", "conciliar", "investigar"],
        "properties": {
            key: {"type": "array", "maxItems": 20, "items": {"type": "string", "maxLength": 1500}}
            for key in ("preservar", "corrigir", "otimizar", "conciliar", "investigar")
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary", "interval_analyses", "topic_analyses", "tradeoffs", "strategy"],
        "properties": {
            "summary": {"type": "string", "maxLength": 8000},
            "interval_analyses": {"type": "array", "minItems": len(interval_ids), "maxItems": len(interval_ids), "items": interval},
            "topic_analyses": {"type": "array", "maxItems": len(_TOPIC_ORDER), "items": topic},
            "tradeoffs": {"type": "array", "maxItems": 20, "items": tradeoff},
            "strategy": strategy,
        },
    }


_AUDIT_REFERENCE_RE = re.compile(r"\bAUD-[A-Za-z0-9][A-Za-z0-9_-]*\b")


def _validate_canonical_audit_references(value: Any, allowed_audit_ids: set[str]) -> None:
    if not allowed_audit_ids:
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_canonical_audit_references(item, allowed_audit_ids)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_canonical_audit_references(item, allowed_audit_ids)
        return
    if not isinstance(value, str):
        return
    invalid = sorted({token for token in _AUDIT_REFERENCE_RE.findall(value) if token not in allowed_audit_ids})
    if invalid:
        raise ValueError("IA citou AUD inexistente ou identificador truncado: " + ", ".join(invalid))


_UNRELATED_COMPARABILITY_PATTERNS = (
    re.compile(r"\bintervalo (?:é |foi )?comparável\b", re.IGNORECASE),
    re.compile(r"\bsérie (?:é |foi )?comparável\b", re.IGNORECASE),
    re.compile(r"\bmarcos (?:são |foram )?comparáveis\b", re.IGNORECASE),
    re.compile(r"\bcomparável entre\b", re.IGNORECASE),
    re.compile(r"\bcomparabilidade (?:plena|total|equivalente)\b", re.IGNORECASE),
)
_COMPARABILITY_NEGATION_RE = re.compile(
    r"(?:"
    r"\bnão\s+(?:há|existe|é|são|foi|foram|apresenta|apresentam|possui|possuem|"
    r"permite|permitem|sustenta|sustentam|fornece|fornecem|tem|têm|temos)\b"
    r"|\bsem\b"
    r"|\bausência de\b"
    r"|\bausente\b"
    r"|\bincomparável\b"
    r"|\bincomparáveis\b"
    r")",
    re.IGNORECASE,
)


def _comparability_match_is_negated(text: str, start: int) -> bool:
    clause_start = max(
        text.rfind(".", 0, start),
        text.rfind(";", 0, start),
        text.rfind(":", 0, start),
        text.rfind("\n", 0, start),
    )
    context = text[clause_start + 1:start]
    return bool(_COMPARABILITY_NEGATION_RE.search(context))


def _validate_configuration_comparability_language(value: Any, pair_status: str | None) -> None:
    """Reject AI wording that upgrades an UNRELATED pair into a controlled comparison."""
    if str(pair_status or "").upper() != "UNRELATED":
        return
    if isinstance(value, Mapping):
        for item in value.values():
            _validate_configuration_comparability_language(item, pair_status)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_configuration_comparability_language(item, pair_status)
        return
    if not isinstance(value, str):
        return
    for pattern in _UNRELATED_COMPARABILITY_PATTERNS:
        for match in pattern.finditer(value):
            if _comparability_match_is_negated(value, match.start()):
                continue
            raise ValueError(
                "IA tratou configuração UNRELATED como comparação controlada; use 'comparação contextual'"
            )


def _validated_longitudinal_payload(
    payload: Any,
    *,
    allowed: set[str],
    interval_ids: tuple[str, ...],
    allowed_audit_ids: set[str] | None = None,
) -> tuple[str, tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], dict[str, tuple[str, ...]]]:
    if not isinstance(payload, Mapping):
        raise ValueError("resposta longitudinal da IA deve ser objeto")
    _validate_canonical_audit_references(payload, set(allowed_audit_ids or ()))
    raw_intervals = payload.get("interval_analyses")
    raw_topics = payload.get("topic_analyses")
    raw_tradeoffs = payload.get("tradeoffs")
    raw_strategy = payload.get("strategy")
    if not isinstance(raw_intervals, list) or not isinstance(raw_topics, list) or not isinstance(raw_tradeoffs, list) or not isinstance(raw_strategy, Mapping):
        raise ValueError("resposta longitudinal da IA está incompleta")

    intervals: list[dict[str, Any]] = []
    seen_intervals: set[str] = set()
    for raw in raw_intervals:
        if not isinstance(raw, Mapping):
            raise ValueError("análise de intervalo deve ser objeto")
        interval_id = str(raw.get("interval_id") or "")
        if interval_id not in interval_ids or interval_id in seen_intervals:
            continue
        evidence = tuple(str(item) for item in raw.get("evidence_ids", ()) if str(item))
        if not set(evidence).issubset(allowed):
            raise ValueError("IA citou evidência fora do pacote longitudinal")
        intervals.append({
            "interval_id": interval_id,
            "assessment": str(raw.get("assessment") or "")[:5000],
            "evidence_level": str(raw.get("evidence_level") or "INDETERMINADO"),
            "benefited_indicators": tuple(str(item)[:500] for item in raw.get("benefited_indicators", ()) if str(item).strip())[:30],
            "harmed_indicators": tuple(str(item)[:500] for item in raw.get("harmed_indicators", ()) if str(item).strip())[:30],
            "stable_indicators": tuple(str(item)[:500] for item in raw.get("stable_indicators", ()) if str(item).strip())[:30],
            "recommended_path": str(raw.get("recommended_path") or "")[:5000],
            "evidence_ids": evidence,
        })
        seen_intervals.add(interval_id)
    if seen_intervals != set(interval_ids):
        raise ValueError("IA não analisou todos os intervalos obrigatórios")

    topics: list[dict[str, Any]] = []
    seen_topics: set[str] = set()
    for raw in raw_topics[: len(_TOPIC_ORDER)]:
        if not isinstance(raw, Mapping):
            continue
        topic = str(raw.get("topic") or "")
        if topic not in _TOPIC_ORDER or topic in seen_topics:
            continue
        evidence = tuple(str(item) for item in raw.get("evidence_ids", ()) if str(item))
        if not set(evidence).issubset(allowed):
            raise ValueError("IA citou evidência fora do pacote longitudinal")
        confidence = float(raw.get("confidence"))
        priority = str(raw.get("priority") or "P3").upper()
        if priority not in {"P0", "P1", "P2", "P3"} or not 0 <= confidence <= 1:
            raise ValueError("prioridade ou confiança inválida na análise longitudinal")
        topics.append({
            "topic": topic,
            "assessment": str(raw.get("assessment") or "")[:5000],
            "cause_analysis": str(raw.get("cause_analysis") or raw.get("assessment") or "")[:5000],
            "recommended_actions": tuple(str(item)[:1600] for item in raw.get("recommended_actions", ()) if str(item).strip())[:12],
            "priority": priority,
            "confidence": confidence,
            "evidence_ids": evidence,
        })
        seen_topics.add(topic)

    tradeoffs: list[dict[str, Any]] = []
    for raw in raw_tradeoffs[:20]:
        if not isinstance(raw, Mapping):
            continue
        evidence = tuple(str(item) for item in raw.get("evidence_ids", ()) if str(item))
        if not set(evidence).issubset(allowed):
            raise ValueError("IA citou evidência fora do pacote longitudinal")
        topics_values = tuple(str(item) for item in raw.get("affected_topics", ()) if str(item) in _TOPIC_ORDER)
        tradeoffs.append({
            "title": str(raw.get("title") or "")[:500],
            "assessment": str(raw.get("assessment") or "")[:4000],
            "affected_topics": topics_values,
            "recommended_path": str(raw.get("recommended_path") or "")[:4000],
            "evidence_ids": evidence,
        })

    strategy: dict[str, tuple[str, ...]] = {}
    for key in ("preservar", "corrigir", "otimizar", "conciliar", "investigar"):
        values = raw_strategy.get(key)
        if not isinstance(values, list):
            raise ValueError(f"estratégia longitudinal ausente: {key}")
        strategy[key] = tuple(str(item)[:1500] for item in values if str(item).strip())[:20]
    return str(payload.get("summary") or "")[:8000], tuple(intervals), tuple(topics), tuple(tradeoffs), strategy


def _preparation_filter_identity(filters: ConsolidationFilter) -> str:
    return json.dumps(filters.canonical(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _preparation_root_identity(audits_root: str | Path) -> str:
    return str(Path(audits_root).resolve())


def _validate_preparation(
    prepared: LongitudinalPreparation,
    audits_root: str | Path,
    filters: ConsolidationFilter,
) -> None:
    if prepared.root_identity != _preparation_root_identity(audits_root):
        raise ValueError("preparação longitudinal pertence a outro diretório de auditorias")
    if prepared.filter_identity != _preparation_filter_identity(filters):
        raise ValueError("preparação longitudinal pertence a filtros diferentes")


def _validate_prepared_bundle(
    prepared: LongitudinalPreparation,
    bundle: LongitudinalBundle,
    filters: ConsolidationFilter,
) -> None:
    if prepared.filter_identity != _preparation_filter_identity(filters):
        raise ValueError("preparação longitudinal pertence a filtros diferentes")
    if prepared.bundle is not bundle:
        raise ValueError("a execução de IA deve usar o mesmo LongitudinalBundle preparado")


def prepare_longitudinal_specialist(
    audits_root: str | Path,
    filters: ConsolidationFilter,
) -> LongitudinalPreparation:
    root = Path(audits_root)
    bundle = build_longitudinal(root, filters)
    full_packet, full_evidence_ids = _longitudinal_packet(bundle)
    packet, projected_evidence_ids, projection_meta = _ai_packet_projection(full_packet)
    hint = _token_hint(packet)
    index = ConsolidationIndex(root)
    rows = index.candidate_audits(filters)
    source_fingerprint = index.source_set_fingerprint(rows)
    return LongitudinalPreparation(
        root_identity=_preparation_root_identity(root),
        filter_identity=_preparation_filter_identity(filters),
        source_fingerprint=source_fingerprint,
        bundle=bundle,
        full_packet=full_packet,
        full_evidence_ids=full_evidence_ids,
        projected_packet=packet,
        projected_evidence_ids=projected_evidence_ids,
        context_projection=projection_meta,
        token_hint=hint,
    )


def preview_longitudinal_specialist(
    audits_root: str | Path,
    filters: ConsolidationFilter,
    *,
    env: Mapping[str, str] | None = None,
    prepared: LongitudinalPreparation | None = None,
) -> SpecialistPreview:
    try:
        preparation = prepared or prepare_longitudinal_specialist(audits_root, filters)
        _validate_preparation(preparation, audits_root, filters)
        bundle = preparation.bundle
        projection_meta = preparation.context_projection
        provider = _build_ai(filters, env)
        hint = preparation.token_hint
        now = datetime.now(timezone.utc)
        excluded = tuple(str(item) for item in getattr(provider, "excluded_configurations", ()) or ())
        if hasattr(provider, "ordered_candidates_for_need"):
            candidates = provider.ordered_candidates_for_need(hint, scope=AI_SCOPE)
            estimates = tuple(estimate_candidate_cost(item, hint, scope=AI_SCOPE, at=now) for item in candidates)
        else:
            estimates = (estimate_candidate_cost(provider, hint, scope=AI_SCOPE, at=now),)
        selected = estimates[0] if estimates else None
        forecast = _forecast(estimates)
        if selected is None:
            return SpecialistPreview(
                False,
                "AI_PROVIDER_CHAIN_EXHAUSTED",
                bundle.audit_ids[0],
                bundle.audit_ids[-1],
                "LONGITUDINAL",
                (),
                None,
                sum(len(item.events) for item in bundle.intervals),
                excluded,
                forecast,
                projection_meta,
            )
        return SpecialistPreview(
            True,
            None,
            bundle.audit_ids[0],
            bundle.audit_ids[-1],
            "LONGITUDINAL",
            estimates,
            selected,
            sum(len(item.events) for item in bundle.intervals),
            excluded,
            forecast,
            projection_meta,
        )
    except Exception as exc:
        return SpecialistPreview(
            False,
            f"{type(exc).__name__}: {str(exc)[:300]}",
            None,
            None,
            "LONGITUDINAL",
            (),
            None,
        )
    finally:
        clear_current_ai_execution()


def run_longitudinal_ai(
    bundle: LongitudinalBundle,
    filters: ConsolidationFilter,
    *,
    env: Mapping[str, str] | None = None,
    prepared: LongitudinalPreparation | None = None,
    expected_preview: SpecialistPreview | None = None,
) -> SpecialistRun:
    if not filters.specialist_ai:
        return SpecialistRun(
            requested=False,
            status="NOT_REQUESTED",
            summary="",
            topic_analyses=(),
            attempts=(),
            reason="AI_NOT_REQUESTED",
        )
    if not filters.ai_provider or filters.ai_provider.casefold() == "none":
        return SpecialistRun(
            requested=True,
            status="NOT_CONFIGURED",
            summary="",
            topic_analyses=(),
            attempts=(),
            reason="AI_PROVIDER_NOT_CONFIGURED",
        )

    if prepared is None:
        full_packet, _allowed_ids = _longitudinal_packet(bundle)
        packet, allowed_ids, projection_meta = _ai_packet_projection(full_packet)
        hint = _token_hint(packet)
    else:
        _validate_prepared_bundle(prepared, bundle, filters)
        packet = prepared.projected_packet
        allowed_ids = prepared.projected_evidence_ids
        projection_meta = prepared.context_projection
        hint = prepared.token_hint
    interval_ids = tuple(item.interval_id for item in bundle.catalog_intervals)
    schema = _longitudinal_schema(allowed_ids, interval_ids)
    pair_status = str(
        (bundle.governance.get("configuration_comparability") or {}).get("pair_status")
        if isinstance(bundle.governance.get("configuration_comparability"), Mapping)
        else ""
    ).upper()
    comparability_instruction = (
        " As configurações entre os marcos não são equivalentes (estado técnico UNRELATED). "
        "O campo scope_comparable descreve apenas compatibilidade básica de escopo para construir o intervalo; "
        "não significa equivalência da configuração de execução. Descreva o par como comparação contextual; "
        "nunca use 'intervalo comparável', 'série comparável', 'marcos comparáveis' ou outra formulação que "
        "sugira repetição controlada do mesmo teste. Não use UNRELATED como rótulo humano principal. "
        if pair_status == "UNRELATED" else ""
    )
    instructions = _instructions() + (
        "\nAnalise obrigatoriamente cada intervalo consecutivo. Explique picos, quedas e reversões com o nível de evidência apropriado. "
        "Não classifique a página inteira como boa ou ruim. Declare benefícios e prejuízos por indicador ou requisito. "
        "Quando houver trade-off, proponha um caminho que preserve benefícios e reduza regressões. "
        "Itens estáveis e dentro do esperado devem ser reconhecidos como algo a preservar, com menor destaque. "
        "Problemas estáveis devem ser tratados como pendências persistentes. "
        "Em effective_external_state, somente a tentativa marcada effective_for_current_observation=true representa o estado final; "
        "tentativas anteriores são históricas/superadas e nunca devem ser chamadas de tentativa final. "
        "Ao citar uma AUD, copie exatamente um identificador presente em scope.audit_ids; nunca abrevie, trunque ou invente AUD-*. "
        "Se os dados não permitirem explicar uma variação, use INDETERMINADO e diga explicitamente que não há evidência suficiente. "
        "O campo summary deve ser um resumo gerencial em pt-BR que explique, nesta ordem: como a URL estava no marco inicial; "
        "o que aconteceu nos intervalos intermediários e onde houve picos/reversões; como a URL está no marco final; "
        "e quais são os focos iniciais para observação e mudança. "
        "Em cada topic_analysis, use cause_analysis para explicar o que as evidências indicam como causa, associação ou hipótese do problema; "
        "não use linguagem causal quando o nível de evidência não sustentar causalidade. As recommended_actions devem dizer o que fazer e como validar."
        + comparability_instruction
    )
    user_text = "Evidências longitudinais persistidas do RASAi:\n" + json.dumps(packet, ensure_ascii=False, default=str)
    request_hash = sha256(user_text.encode("utf-8")).hexdigest()
    attempts: list[tuple[ProviderAttempt, int]] = []
    profile_ids, profile_versions = profile_identity("EVOLUTION")
    rounds_executed = 0

    try:
        selection = _build_ai(filters, env)
        excluded = tuple(str(item) for item in getattr(selection, "excluded_configurations", ()) or ())
        if hasattr(selection, "ordered_candidates_for_need"):
            first_candidates = selection.ordered_candidates_for_need(hint, scope=AI_SCOPE)
            coordinator = selection.coordinator
        else:
            first_candidates = (selection,)
            coordinator = None

        estimates = tuple(
            estimate_candidate_cost(item, hint, scope=AI_SCOPE, at=datetime.now(timezone.utc))
            for item in first_candidates
        )
        candidate_views = tuple(_candidate_view(item) for item in estimates)
        forecast = _forecast(estimates)
        if expected_preview is not None:
            expected_views = tuple(_candidate_view(item) for item in expected_preview.candidates)
            if (
                candidate_views != expected_views
                or excluded != expected_preview.excluded_candidates
                or forecast != expected_preview.forecast
            ):
                raise RuntimeError(
                    "a cadeia de providers/custo mudou após a prévia autorizada; "
                    "a chamada externa foi bloqueada para exigir nova confirmação"
                )

        if not first_candidates:
            return SpecialistRun(
                True,
                "UNAVAILABLE",
                "",
                (),
                (),
                "nenhum provedor de IA elegível",
                profile_id=profile_ids,
                profile_version=profile_versions,
                rounds=0,
                candidates=candidate_views,
                excluded_candidates=excluded,
                forecast=forecast,
                exchanges=_capture_ai_exchanges(),
                context_projection=projection_meta,
            )

        retry_names: set[str] | None = None
        last_reason: str | None = None

        for round_no in range(1, MAX_AI_ROUNDS + 1):
            if hasattr(selection, "ordered_candidates_for_need"):
                current_candidates = selection.ordered_candidates_for_need(hint, scope=AI_SCOPE)
            else:
                current_candidates = first_candidates
            if retry_names is not None:
                current_candidates = tuple(
                    item for item in current_candidates if str(getattr(item, "name", "")) in retry_names
                )
            if not current_candidates:
                break

            rounds_executed = round_no
            fallback_from: str | None = None
            fallback_reason: str | None = None
            round_attempts_start = len(attempts)

            for position, provider in enumerate(current_candidates, 1):
                body = json.dumps(
                    _provider_payload(provider, instructions=instructions, user_text=user_text, schema=schema),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                started = datetime.now(timezone.utc)
                started_perf = time.perf_counter()
                status = AttemptStatus.TECHNICAL_ERROR
                diagnostic: ProviderDiagnostic | None = None
                usage = None
                raw: Mapping[str, Any] | None = None
                validated: tuple[
                    str,
                    tuple[dict[str, Any], ...],
                    tuple[dict[str, Any], ...],
                    tuple[dict[str, Any], ...],
                    dict[str, tuple[str, ...]],
                ] | None = None

                try:
                    candidate = provider._transport(
                        provider.endpoint,
                        provider._headers(),
                        body,
                        float(filters.ai_timeout_seconds or 180.0),
                    )
                    if not isinstance(candidate, Mapping):
                        diagnostic = ProviderDiagnostic(ProviderErrorClass.INVALID_RESPONSE)
                    else:
                        raw = candidate
                        usage = _provider_usage(provider, raw)
                        diagnostic = _provider_native_error(provider, raw)
                        if diagnostic is None:
                            try:
                                extracted = _provider_extract(provider, raw)
                                _validate_configuration_comparability_language(extracted, pair_status)
                                validated = _validated_longitudinal_payload(
                                    extracted,
                                    allowed=set(allowed_ids),
                                    interval_ids=interval_ids,
                                    allowed_audit_ids=set(bundle.audit_ids),
                                )
                                status = AttemptStatus.SUCCESS
                            except Exception as exc:
                                diagnostic = ProviderDiagnostic(
                                    ProviderErrorClass.CONTRACT_ERROR,
                                    error_type=type(exc).__name__,
                                    error_code="CONSOLIDATED_LONGITUDINAL_OUTPUT_INVALID",
                                )
                                status = AttemptStatus.CONTRACT_ERROR
                except HTTPError as exc:
                    diagnostic = (
                        _core_diagnostic_from_http(exc)
                        if isinstance(provider, ResponsesSemanticProvider)
                        else _extension_diagnostic_from_http(exc)
                    )
                except TimeoutError:
                    diagnostic = ProviderDiagnostic(ProviderErrorClass.TIMEOUT_ERROR)
                except (URLError, OSError):
                    diagnostic = ProviderDiagnostic(ProviderErrorClass.NETWORK_ERROR)
                except Exception as exc:
                    diagnostic = ProviderDiagnostic(
                        ProviderErrorClass.UNKNOWN_PROVIDER_ERROR,
                        error_type=type(exc).__name__,
                    )

                duration_ms = max(0, int((time.perf_counter() - started_perf) * 1000))
                global_index = len(attempts) + 1
                attempt = _attempt_record(
                    provider,
                    status=status,
                    started=started,
                    duration_ms=duration_ms,
                    usage=usage,
                    diagnostic=diagnostic,
                    request_hash=request_hash,
                    index=global_index,
                )
                if fallback_from:
                    attempt = _replace_attempt(
                        attempt,
                        fallback_from=fallback_from,
                        fallback_reason=fallback_reason,
                    )

                retry_eligible = status is not AttemptStatus.SUCCESS and _retryable(diagnostic)
                attempt = replace(attempt, retry_eligible=retry_eligible)

                if status is AttemptStatus.SUCCESS and validated is not None:
                    decision = DECISION_FALLBACK_SUCCESS if attempts or fallback_from else DECISION_SUCCESS
                    attempt = _replace_decision(attempt, decision)
                    if coordinator is not None:
                        coordinator.record_attempt(attempt, scope=AI_SCOPE)
                    attempts.append((attempt, round_no))
                    summary, interval_analyses, analyses, tradeoffs, strategy = validated
                    return SpecialistRun(
                        True,
                        "COMPLETE",
                        summary,
                        analyses,
                        tuple(_public_attempt(item, round_no=item_round) for item, item_round in attempts),
                        interval_analyses=interval_analyses,
                        tradeoffs=tradeoffs,
                        strategy=strategy,
                        profile_id=profile_ids,
                        profile_version=profile_versions,
                        rounds=rounds_executed,
                        candidates=candidate_views,
                        excluded_candidates=excluded,
                        forecast=forecast,
                        exchanges=_capture_ai_exchanges(),
                        context_projection=projection_meta,
                    )

                has_next = position < len(current_candidates)
                if has_next:
                    attempt = _replace_decision(attempt, DECISION_FALLBACK)
                elif round_no < MAX_AI_ROUNDS and retry_eligible:
                    attempt = _replace_decision(attempt, "RETRY_ROUND")
                else:
                    attempt = _replace_decision(attempt, DECISION_STOP)

                if coordinator is not None:
                    coordinator.record_attempt(attempt, scope=AI_SCOPE)
                attempts.append((attempt, round_no))
                last_reason = diagnostic.reason if diagnostic is not None else "provedor indisponível"

                if has_next:
                    fallback_from = str(provider.name)
                    fallback_reason = last_reason

            round_attempts = attempts[round_attempts_start:]
            retry_names = {
                item.provider
                for item, item_round in round_attempts
                if item_round == round_no and item.retry_eligible
            }
            if round_no >= MAX_AI_ROUNDS or not retry_names:
                break
            if attempts:
                last_attempt, last_round = attempts[-1]
                attempts[-1] = (_replace_decision(last_attempt, "RETRY_ROUND"), last_round)

            delay = _retry_delay(attempts, round_no)
            if delay > 0:
                time.sleep(delay)

        reason = _chain_failure_reason(attempts)
        if rounds_executed >= MAX_AI_ROUNDS:
            reason = "AI_PROVIDER_CHAIN_EXHAUSTED_AFTER_RETRY:" + reason
        return SpecialistRun(
            True,
            "UNAVAILABLE",
            "",
            (),
            tuple(_public_attempt(item, round_no=item_round) for item, item_round in attempts),
            reason,
            profile_id=profile_ids,
            profile_version=profile_versions,
            rounds=rounds_executed,
            candidates=candidate_views,
            excluded_candidates=excluded,
            forecast=forecast,
            exchanges=_capture_ai_exchanges(),
            context_projection=projection_meta,
        )
    finally:
        clear_current_ai_execution()


_LONGITUDINAL_STATUS_LABELS = {
    "IMPROVED": "Melhora",
    "RESOLVED": "Resolvido",
    "REGRESSED": "Regressão",
    "NEW": "Novo",
    "UNCHANGED": "Estável",
    "CHANGED": "Alterado",
    "DATA_UNAVAILABLE": "Dado indisponível",
    "NOT_COMPARABLE": "Não comparável",
    "FIXED": "Corrigido",
    "PARTIALLY_FIXED": "Parcialmente corrigido",
    "STILL_FAILING": "Persistente",
    "ALTERADO": "Alterado",
    "NOVO": "Novo",
    "DADO_INDISPONIVEL": "Dado indisponível",
    "CONFIGURACAO_ALTERADA": "Configuração alterada",
    "PERSISTENTE_ATENCAO": "Persistente com atenção",
    "ESTAVEL": "Estável",
    "ESTAVEL_DENTRO_ESPERADO": "Estável dentro do esperado",
}
_EVIDENCE_LEVEL_LABELS = {
    "EVIDENCIA_DIRETA": "Evidência direta",
    "ASSOCIACAO_FORTE": "Associação forte",
    "ASSOCIACAO_POSSIVEL": "Associação possível",
    "INDETERMINADO": "Indeterminado",
}


def _longitudinal_state_html(value: Any) -> str:
    raw = str(value or "").upper()
    label = _LONGITUDINAL_STATUS_LABELS.get(raw, str(value or "-"))
    if raw in {"IMPROVED", "RESOLVED", "FIXED"}:
        tone = "good"
    elif raw in {"REGRESSED", "NEW", "STILL_FAILING"}:
        tone = "bad"
    elif raw in {
        "CHANGED", "PARTIALLY_FIXED", "ALTERADO", "DADO_INDISPONIVEL",
        "CONFIGURACAO_ALTERADA", "PERSISTENTE_ATENCAO",
    }:
        tone = "warn"
    else:
        tone = "neutral"
    return f"<span class='state-text {tone}'>{escape(label)}</span>"


def _catalog_state_html(value: Any) -> str:
    label = _human_term(value or "Sem dado")
    key = label.casefold()
    if key.startswith(("não aplic", "não determin", "não solicit", "não eleg", "sem dado", "automát")):
        tone = "neutral"
    elif key.startswith(("conclu", "aprov", "válid", "valido", "disponível", "disponivel")):
        tone = "good"
    elif key.startswith(("parcial", "atenção", "atencao", "não configur", "nao configur")):
        tone = "warn"
    elif key.startswith(("falha", "erro", "bloque", "indisponível", "indisponivel")):
        tone = "bad"
    else:
        return escape(label)
    return f"<span class='state-text {tone}'>{escape(label)}</span>"


def _longitudinal_deterministic_html(bundle: LongitudinalBundle) -> str:
    global_rows = "".join(
        "<tr>"
        f"<td>{_longitudinal_state_html(item.get('status'))}</td>"
        f"<td>{escape(_event_indicator_label(item))}</td>"
        f"<td>{escape(_fmt(item.get('before')))}</td>"
        f"<td>{escape(_fmt(item.get('after')))}</td>"
        f"<td>{escape(_fmt(item.get('delta')))}</td>"
        f"<td>{escape(str(item.get('url') or 'escopo da URL'))}</td>"
        "</tr>"
        for item in bundle.global_evolution.events
    ) or "<tr><td colspan='6'>Nenhuma variação material comparável entre o marco inicial e o final.</td></tr>"

    alerts: list[tuple[str, str, str]] = []
    for pos, pair in enumerate(bundle.intervals, 1):
        for item in pair.events:
            state = str(item.get("status") or "").upper()
            if state in {"REGRESSED", "NEW", "NOT_COMPARABLE", "DATA_UNAVAILABLE"}:
                alerts.append((
                    _LONGITUDINAL_STATUS_LABELS.get(state, state),
                    f"Intervalo {pos} - {_event_indicator_label(item)}",
                    f"{_fmt(item.get('before'))} para {_fmt(item.get('after'))}",
                ))
        for item in bundle.catalog_intervals[pos - 1].changes:
            state = str(item.get("status") or "").upper()
            if state in {"PERSISTENTE_ATENCAO", "CONFIGURACAO_ALTERADA", "DADO_INDISPONIVEL"}:
                alerts.append((
                    _LONGITUDINAL_STATUS_LABELS.get(state, state),
                    f"Intervalo {pos} - {str(item.get('catalog_label') or item.get('catalog_id') or 'Catálogo')}",
                    _human_term(item.get("label") or "Condição persistente"),
                ))
    alert_cards = "".join(
        f"<article class='page-card'><div class='kicker'>{escape(kind)}</div>"
        f"<h3>{escape(title)}</h3><p>{escape(detail)}</p></article>"
        for kind, title, detail in alerts[:24]
    ) or "<p>Nenhum alerta prioritário foi produzido pelos critérios determinísticos do período.</p>"

    initial_catalogs = {
        str(item.get("catalog_id") or ""): item
        for item in bundle.catalog_snapshots[0].catalogs
        if isinstance(item, Mapping) and item.get("catalog_id")
    }
    final_catalogs = {
        str(item.get("catalog_id") or ""): item
        for item in bundle.catalog_snapshots[-1].catalogs
        if isinstance(item, Mapping) and item.get("catalog_id")
    }
    catalog_ids = tuple(dict.fromkeys((*initial_catalogs.keys(), *final_catalogs.keys())))
    catalog_coverage_rows = "".join(
        "<tr>"
        f"<td>{escape(catalog_id)}</td>"
        f"<td>{escape(_human_term((final_catalogs.get(catalog_id) or initial_catalogs.get(catalog_id) or {}).get('label') or '-'))}</td>"
        f"<td>{_catalog_state_html((initial_catalogs.get(catalog_id) or {}).get('status') or 'Sem dado')}</td>"
        f"<td>{_catalog_state_html((final_catalogs.get(catalog_id) or {}).get('status') or 'Sem dado')}</td>"
        f"<td>{len((initial_catalogs.get(catalog_id) or {}).get('metrics') or ())}</td>"
        f"<td>{len((final_catalogs.get(catalog_id) or {}).get('metrics') or ())}</td>"
        "</tr>"
        for catalog_id in catalog_ids
    ) or "<tr><td colspan='6'>Nenhum catálogo estruturado foi encontrado.</td></tr>"

    interval_blocks: list[str] = []
    for pos, pair in enumerate(bundle.intervals, 1):
        catalog_interval = bundle.catalog_intervals[pos - 1]
        notable = [
            item for item in catalog_interval.changes
            if str(item.get("status")) not in {"ESTAVEL", "ESTAVEL_DENTRO_ESPERADO"}
        ]
        stable_items = [
            item for item in catalog_interval.changes
            if str(item.get("status")) in {"ESTAVEL", "ESTAVEL_DENTRO_ESPERADO"}
        ]
        event_rows = "".join(
            "<tr>"
            f"<td>{_longitudinal_state_html(item.get('status'))}</td>"
            f"<td>{escape(_event_indicator_label(item))}</td>"
            f"<td>{escape(_fmt(item.get('before')))}</td>"
            f"<td>{escape(_fmt(item.get('after')))}</td>"
            f"<td>{escape(_fmt(item.get('delta')))}</td>"
            "</tr>"
            for item in pair.events
        ) or "<tr><td colspan='5'>Nenhuma variação material nos sinais direcionais deste intervalo.</td></tr>"
        catalog_rows = "".join(
            "<tr>"
            f"<td>{escape(str(item.get('catalog_id') or '-'))} - {escape(_human_term(item.get('catalog_label') or '-'))}</td>"
            f"<td>{escape(_human_term(item.get('label') or '-'))}</td>"
            f"<td>{_longitudinal_state_html(item.get('status'))}</td>"
            f"<td>{escape(_fmt(item.get('before')))}</td>"
            f"<td>{escape(_fmt(item.get('after')))}</td>"
            "</tr>"
            for item in notable
        ) or "<tr><td colspan='5'>Sem alterações relevantes nas projeções estruturadas dos catálogos.</td></tr>"
        stable_rows = "".join(
            "<tr>"
            f"<td>{escape(str(item.get('catalog_id') or '-'))} - {escape(_human_term(item.get('catalog_label') or '-'))}</td>"
            f"<td>{escape(_human_term(item.get('label') or '-'))}</td>"
            f"<td>{_longitudinal_state_html(item.get('status'))}</td>"
            f"<td>{escape(_fmt(item.get('before')))}</td>"
            f"<td>{escape(_fmt(item.get('after')))}</td>"
            "</tr>"
            for item in stable_items
        ) or "<tr><td colspan='5'>Nenhum item estável estruturado neste intervalo.</td></tr>"
        interval_blocks.append(f"""
<article class='page-card'>
  <div class='kicker'>Intervalo {pos}</div>
  <h3>{escape(pair.comparison.baseline.audit_id)} até {escape(pair.comparison.current.audit_id)}</h3>
  <p>{escape(pair.comparison.baseline.event_time)} até {escape(pair.comparison.current.event_time)}</p>
  <div class='metric-grid'>
    <div class='metric signal-negative'><span>Regressões</span><strong>{int(pair.comparison.material_counts.get('REGRESSED', 0))}</strong></div>
    <div class='metric signal-positive'><span>Melhorias</span><strong>{int(pair.comparison.material_counts.get('IMPROVED', 0) + pair.comparison.material_counts.get('RESOLVED', 0))}</strong></div>
    <div class='metric'><span>Estáveis dentro do esperado</span><strong>{catalog_interval.stable_expected}</strong></div>
    <div class='metric signal-warning'><span>Estáveis que exigem atenção</span><strong>{catalog_interval.stable_attention}</strong></div>
  </div>
  <h4>Indicadores direcionais</h4>
  <div class='table-wrap bounded'><table><thead><tr><th>Estado</th><th>Indicador</th><th>Antes</th><th>Depois</th><th>Delta</th></tr></thead><tbody>{event_rows}</tbody></table></div>
  <h4>Mudanças dos catálogos</h4>
  <div class='table-wrap bounded'><table><thead><tr><th>Catálogo</th><th>Item</th><th>Estado</th><th>Antes</th><th>Depois</th></tr></thead><tbody>{catalog_rows}</tbody></table></div>
  <details><summary>Itens estáveis e detalhes de menor destaque ({len(stable_items)})</summary>
    <p>Foram processados {len(catalog_interval.changes)} item(ns) estruturados neste intervalo. Os itens estáveis permanecem auditáveis e recolhidos apenas para reduzir ruído visual.</p>
    <div class='table-wrap bounded'><table><thead><tr><th>Catálogo</th><th>Item</th><th>Estado</th><th>Antes</th><th>Depois</th></tr></thead><tbody>{stable_rows}</tbody></table></div>
  </details>
</article>""")
    return f"""
<section id='longitudinal-evolution' class='panel'>
  <div class='kicker'>Evolução longitudinal</div>
  <h2>Trajetória completa da URL por dispositivo</h2>
  <p><strong>URL:</strong> {escape(bundle.url)}<br><strong>Dispositivo:</strong> {escape(bundle.device)}<br><strong>Auditorias:</strong> {len(bundle.audit_ids)}<br><strong>Marco inicial:</strong> {escape(bundle.event_times[0])}<br><strong>Marco final:</strong> {escape(bundle.event_times[-1])}</p>
  <p>A leitura considera cada intervalo consecutivo e também o marco inicial contra o final. Nenhuma URL foi recolhida ou reprocessada para gerar este consolidado.</p>
  <p><a href='longitudinal-evidence.json'>Abrir evidência longitudinal completa e auditável</a></p>
  <h3>Cobertura dos catálogos</h3>
  <p>Todos os catálogos estruturados encontrados nos marcos inicial e final permanecem representados, inclusive quando não há alteração material.</p>
  <div class='table-wrap bounded'><table><thead><tr><th>Catálogo</th><th>Finalidade</th><th>Estado inicial</th><th>Estado final</th><th>Métricas iniciais</th><th>Métricas finais</th></tr></thead><tbody>{catalog_coverage_rows}</tbody></table></div>
  <h3>Marco inicial comparado ao marco final</h3>
  <div class='table-wrap bounded'><table><thead><tr><th>Estado</th><th>Indicador</th><th>Inicial</th><th>Final</th><th>Delta</th><th>Escopo</th></tr></thead><tbody>{global_rows}</tbody></table></div>
  <h3>Alertas direcionados</h3>
  <div class='page-grid'>{alert_cards}</div>
  <h3>Análise por intervalo</h3>
  <div class='page-grid'>{''.join(interval_blocks)}</div>
</section>
"""


def _longitudinal_ai_html(run: SpecialistRun) -> str:
    if run.status != "COMPLETE":
        return ""
    projection = run.context_projection or {}
    projection_html = (
        "<details class='details'><summary>Contexto enviado à IA e cobertura da projeção</summary>"
        f"<p><strong>Contrato:</strong> {escape(str(projection.get('contract') or '-'))}"
        f"<br><strong>Nível de compactação:</strong> {escape(str(projection.get('level') or '-'))}"
        f"<br><strong>Tokens de entrada estimados:</strong> {escape(str(projection.get('estimated_input_tokens') or '-'))}"
        f"<br><strong>Limite seguro:</strong> {escape(str(projection.get('max_input_hint_tokens') or '-'))}"
        "<br><strong>Evidência completa:</strong> preservada localmente em <code>longitudinal-evidence.json</code>.</p>"
        "<p>A compactação afeta somente o contexto enviado à IA. A consolidação determinística e os artifacts locais preservam a cobertura completa das auditorias e catálogos.</p>"
        "</details>"
    )
    interval_cards = []
    for item in run.interval_analyses:
        benefited = "".join(f"<li>{escape(str(value))}</li>" for value in item.get("benefited_indicators", ())) or "<li>Nenhum benefício sustentado destacado.</li>"
        harmed = "".join(f"<li>{escape(str(value))}</li>" for value in item.get("harmed_indicators", ())) or "<li>Nenhum prejuízo sustentado destacado.</li>"
        stable = "".join(f"<li>{escape(str(value))}</li>" for value in item.get("stable_indicators", ())) or "<li>Nenhum item estável destacado.</li>"
        evidence = ", ".join(item.get("evidence_ids", ())) or "Sem evidência específica suficiente"
        interval_cards.append(f"""
<article class='page-card'>
  <div class='kicker'>{escape(str(item.get('interval_id') or 'Intervalo'))}</div>
  <h3>{escape(_EVIDENCE_LEVEL_LABELS.get(str(item.get('evidence_level')), str(item.get('evidence_level'))))}</h3>
  <p>{escape(str(item.get('assessment') or ''))}</p>
  <div class='grid-2'><div><h4>Beneficiados</h4><ul>{benefited}</ul></div><div><h4>Prejudicados</h4><ul>{harmed}</ul></div></div>
  <details><summary>Indicadores estáveis</summary><ul>{stable}</ul></details>
  <h4>Caminho recomendado</h4><p>{escape(str(item.get('recommended_path') or ''))}</p>
  <p><strong>Evidências:</strong> <code>{escape(evidence)}</code></p>
</article>""")
    tradeoffs = "".join(
        f"<article class='page-card'><h3>{escape(str(item.get('title') or 'Conflito entre requisitos'))}</h3>"
        f"<p>{escape(str(item.get('assessment') or ''))}</p><p><strong>Caminho:</strong> {escape(str(item.get('recommended_path') or ''))}</p>"
        f"<p><strong>Dimensões:</strong> {escape(', '.join(_TOPIC_LABELS.get(str(v), str(v)) for v in item.get('affected_topics', ())))}</p></article>"
        for item in run.tradeoffs
    ) or "<p>Nenhum conflito multidimensional específico foi sustentado pelas evidências fornecidas.</p>"
    strategy = run.strategy or {}
    strategy_blocks = "".join(
        f"<div class='strategy-card'><h4>{escape(label)}</h4><ul>{''.join(f'<li>{escape(str(value))}</li>' for value in strategy.get(key, ())) or '<li>Nenhuma ação específica.</li>'}</ul></div>"
        for key, label in (
            ("preservar", "Preservar"),
            ("corrigir", "Corrigir"),
            ("otimizar", "Otimizar"),
            ("conciliar", "Conciliar"),
            ("investigar", "Investigar"),
        )
    )
    topic_cards = []
    for item in run.topic_analyses:
        actions = "".join(f"<li>{escape(str(action))}</li>" for action in item.get("recommended_actions", ()))
        topic_cards.append(
            f"<article class='page-card'><div class='kicker'>{escape(_TOPIC_LABELS.get(str(item['topic']), str(item['topic'])))}</div>"
            f"<h3>Prioridade {escape(str(item['priority']))}</h3><p>{escape(str(item['assessment']))}</p>"
            f"<h4>Ações recomendadas</h4><ul>{actions}</ul></article>"
        )
    return f"""
<section id='longitudinal-ai' class='panel ai-section' data-ai-generated='true'>
  <div class='ai-origin'>Conteúdo interpretativo gerado por IA · requer validação humana</div>
  <div class='kicker'>Análise longitudinal assistida por IA</div>
  <h2>Interpretação multidimensional e caminhos de evolução</h2>
  <p>{escape(run.summary)}</p>
  {projection_html}
  <h3>Análise de cada intervalo</h3>
  <div class='page-grid'>{''.join(interval_cards)}</div>
  <h3>Conflitos e efeitos cruzados</h3>
  <div class='page-grid'>{tradeoffs}</div>
  <h3>Estratégia de evolução</h3>
  <div class='grid-2 strategy-grid'>{strategy_blocks}</div>
  <h3>Leitura por domínio</h3>
  <div class='page-grid'>{''.join(topic_cards)}</div>
  <p class='notice info'><strong>Limite metodológico:</strong> a IA interpreta somente os dados persistidos fornecidos pelo RASAi. Associação temporal não é causalidade. Recomendações exigem decisão e validação humanas.</p>
</section>
"""


def apply_longitudinal_analysis(
    result: GenerationResult,
    filters: ConsolidationFilter,
    bundle: LongitudinalBundle,
    run: SpecialistRun,
    *,
    prepared: LongitudinalPreparation | None = None,
) -> GenerationResult:
    if run.status != "COMPLETE":
        raise RuntimeError(f"análise longitudinal por IA não concluída: {run.reason or run.status}")
    html = result.report_path.read_text(encoding="utf-8")
    block = _longitudinal_deterministic_html(bundle) + _longitudinal_ai_html(run)
    if "<footer" in html:
        html = html.replace("<footer", block + "<footer", 1)
    else:
        html = html.replace("</body>", block + "</body>", 1)
    result.report_path.write_text(html, encoding="utf-8", newline="\n")

    if prepared is None:
        full_evidence, full_evidence_ids = _longitudinal_packet(bundle)
    else:
        _validate_prepared_bundle(prepared, bundle, filters)
        full_evidence = prepared.full_packet
        full_evidence_ids = prepared.full_evidence_ids
    evidence_artifact = {
        "contract": LONGITUDINAL_CONTRACT,
        "catalog_contract": CATALOG_LONGITUDINAL_CONTRACT,
        "evidence_count": len(full_evidence_ids),
        "scope": {
            "url": bundle.url,
            "device": bundle.device,
            "audit_ids": list(bundle.audit_ids),
            "event_times": list(bundle.event_times),
        },
        "evidence": full_evidence,
    }
    evidence_safe = redact_value(evidence_artifact)
    evidence_raw = json.dumps(
        evidence_safe,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"
    evidence_path = result.report_dir / "longitudinal-evidence.json"
    evidence_path.write_text(evidence_raw, encoding="utf-8", newline="\n")
    evidence_sha256 = sha256(evidence_raw.encode("utf-8")).hexdigest()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["longitudinal_analysis"] = {
        "contract": LONGITUDINAL_CONTRACT,
        "catalog_contract": CATALOG_LONGITUDINAL_CONTRACT,
        "url": bundle.url,
        "device": bundle.device,
        "audit_ids": list(bundle.audit_ids),
        "audit_count": len(bundle.audit_ids),
        "period_start": bundle.event_times[0],
        "period_end": bundle.event_times[-1],
        "intervals": [
            {
                "interval_id": catalog.interval_id,
                "baseline_audit_id": catalog.baseline_audit_id,
                "current_audit_id": catalog.current_audit_id,
                "baseline_event_time": catalog.baseline_event_time,
                "current_event_time": catalog.current_event_time,
                "stable_within_expected": catalog.stable_expected,
                "stable_requiring_attention": catalog.stable_attention,
            }
            for catalog in bundle.catalog_intervals
        ],
        "ai_required": True,
        "ai_status": run.status,
        "ai_profile_id": run.profile_id,
        "ai_profile_version": run.profile_version,
        "evidence_file": "longitudinal-evidence.json",
        "evidence_sha256": evidence_sha256,
        "evidence_count": len(full_evidence_ids),
        "ai_context_projection": run.context_projection,
        "limitations": list(bundle.limitations),
    }
    manifest["specialist_ai"] = {
        "contract": SPECIALIST_CONTRACT,
        "requested": True,
        "required": True,
        "status": run.status,
        "provider_selection": filters.ai_provider,
        "model_selection": filters.ai_model,
        "reasoning_selection": filters.ai_reasoning,
        "pricing_version": PRICING_VERSION,
        "profile_id": run.profile_id,
        "profile_version": run.profile_version,
        "reason": run.reason,
        "rounds": run.rounds,
        "candidates": list(run.candidates),
        "excluded_candidates": list(run.excluded_candidates),
        "forecast": run.forecast,
        "context_projection": run.context_projection,
        "attempts": [asdict(item) for item in run.attempts],
        "exchanges_file": "ai-exchanges.json",
    }
    result.manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    artifact = {
        "contract": LONGITUDINAL_CONTRACT,
        "catalog_contract": CATALOG_LONGITUDINAL_CONTRACT,
        "scope": {
            "url": bundle.url,
            "device": bundle.device,
            "audit_ids": list(bundle.audit_ids),
            "event_times": list(bundle.event_times),
        },
        "intervals": [
            {
                "interval_id": catalog.interval_id,
                "baseline_audit_id": catalog.baseline_audit_id,
                "current_audit_id": catalog.current_audit_id,
                "changes": list(catalog.changes),
            }
            for catalog in bundle.catalog_intervals
        ],
        "initial_to_final": {
            "changes": list(bundle.global_evolution.events),
            "fix_verification": list(bundle.global_evolution.fixes),
        },
        "ai": {
            "requested": True,
            "required": True,
            "status": run.status,
            "reason": run.reason,
            "profile_id": run.profile_id,
            "profile_version": run.profile_version,
            "rounds": run.rounds,
            "candidates": list(run.candidates),
            "excluded_candidates": list(run.excluded_candidates),
            "forecast": run.forecast,
            "context_projection": run.context_projection,
            "full_evidence_file": "longitudinal-evidence.json",
            "full_evidence_sha256": evidence_sha256,
            "exchanges_file": "ai-exchanges.json",
            "summary": run.summary,
            "interval_analyses": list(run.interval_analyses),
            "topic_analyses": list(run.topic_analyses),
            "tradeoffs": list(run.tradeoffs),
            "strategy": {key: list(value) for key, value in (run.strategy or {}).items()},
            "attempts": [asdict(item) for item in run.attempts],
        },
    }
    (result.report_dir / "specialist-analysis.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    exchange_artifact = {
        "contract": SPECIALIST_CONTRACT,
        "scope": AI_SCOPE,
        "profile_id": run.profile_id,
        "profile_version": run.profile_version,
        "exchanges": list(run.exchanges),
    }
    (result.report_dir / "ai-exchanges.json").write_text(
        json.dumps(exchange_artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return result
