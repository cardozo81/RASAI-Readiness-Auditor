"""Evidence-bound AI analysis for Competitive Search & Content Intelligence.

This module is intentionally separate from scoring and BR-GEO semantic assessment.
AI receives only deterministic Search Intelligence evidence and may publish recommendations
or hypotheses, never ranking-causality claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rasai.provider_registry import get_provider_registration

from .content import CompetitiveContentAnalysis, CompetitivePageFeatures


COMPETITIVE_AI_CONTRACT_VERSION = "COMPETITIVE-AI-001"
COMPETITIVE_AI_PROMPT_ID = "rasai-competitive-search"
COMPETITIVE_AI_PROMPT_VERSION = "1"


class CompetitiveAiState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"


class CompetitiveAiCategory(StrEnum):
    QUERY_INTENT = "QUERY_INTENT"
    TOPIC_COVERAGE = "TOPIC_COVERAGE"
    ENTITY_COVERAGE = "ENTITY_COVERAGE"
    INFORMATION_ARCHITECTURE = "INFORMATION_ARCHITECTURE"
    STRUCTURED_DATA = "STRUCTURED_DATA"
    EEAT = "EEAT"
    YMYL = "YMYL"
    SEO_AEO_GEO = "SEO_AEO_GEO"


class CompetitiveAiPriority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CompetitiveAiContractError(ValueError):
    pass


class CompetitiveAiEvidenceError(CompetitiveAiContractError):
    pass


@dataclass(frozen=True, slots=True)
class CompetitiveAiEvidence:
    evidence_id: str
    evidence_type: str
    source: str
    observed_value: Any
    artifact_reference: str | None = None


@dataclass(frozen=True, slots=True)
class CompetitiveAiInput:
    observation_id: str
    query: str
    market: str
    language: str
    ymyl_mode: str
    evidence: tuple[CompetitiveAiEvidence, ...]

    @property
    def allowed_evidence_ids(self) -> frozenset[str]:
        return frozenset(item.evidence_id for item in self.evidence)

    def provider_payload(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "query": self.query,
            "market": self.market,
            "language": self.language,
            "ymyl_mode": self.ymyl_mode,
            "methodology": COMPETITIVE_AI_CONTRACT_VERSION,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "evidence_type": item.evidence_type,
                    "source": item.source,
                    "observed_value": item.observed_value,
                    "artifact_reference": item.artifact_reference,
                }
                for item in self.evidence
            ],
        }


@dataclass(frozen=True, slots=True)
class CompetitiveAiOpportunity:
    category: CompetitiveAiCategory
    priority: CompetitiveAiPriority
    title: str
    recommendation: str
    rationale: str
    evidence_ids: tuple[str, ...]
    confidence: float
    causality_note: str


@dataclass(frozen=True, slots=True)
class CompetitiveAiAssessment:
    query_intent: str
    ymyl_assessment: str
    summary: str
    opportunities: tuple[CompetitiveAiOpportunity, ...]
    provider: str
    model: str | None
    contract_version: str = COMPETITIVE_AI_CONTRACT_VERSION
    prompt_id: str = COMPETITIVE_AI_PROMPT_ID
    prompt_version: str = COMPETITIVE_AI_PROMPT_VERSION
    provider_request_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompetitiveAiResult:
    state: CompetitiveAiState
    assessment: CompetitiveAiAssessment | None = None
    reason: str | None = None


class CompetitiveAiProvider(Protocol):
    name: str

    def analyze(self, competitive_input: CompetitiveAiInput) -> CompetitiveAiResult:
        ...


def _page_observed_value(page: CompetitivePageFeatures) -> dict[str, Any]:
    return {
        "role": page.role,
        "domain": page.domain,
        "requested_url": page.requested_url,
        "final_url": page.final_url,
        "fetch_status": page.status.value,
        "http_status": page.http_status,
        "content_type": page.content_type,
        "content_sha256": page.content_sha256,
        "title": page.title,
        "meta_description": page.meta_description,
        "headings": list(page.headings),
        "word_count": page.word_count,
        "query_terms": list(page.query_terms),
        "query_terms_in_title": list(page.query_terms_in_title),
        "query_terms_in_description": list(page.query_terms_in_description),
        "query_terms_in_headings": list(page.query_terms_in_headings),
        "query_terms_in_body": list(page.query_terms_in_body),
        "query_body_coverage": page.query_body_coverage,
        "jsonld_types": list(page.jsonld_types),
    }


def build_competitive_ai_input(
    observation_id: str,
    analysis: CompetitiveContentAnalysis,
    *,
    market: str,
    language: str,
    ymyl_mode: str = "AUTO",
    artifact_reference: str | None = None,
) -> CompetitiveAiInput:
    mode = ymyl_mode.strip().upper()
    if mode not in {"AUTO", "ON", "OFF"}:
        raise ValueError("ymyl_mode must be AUTO, ON or OFF")
    if analysis.comparison_status != "CONSOLIDATED":
        raise ValueError(
            f"competitive AI requires consolidated deterministic content context; "
            f"got {analysis.comparison_status}"
        )
    if analysis.customer_page is None or analysis.customer_page.status.value != "OBSERVED":
        raise ValueError("competitive AI requires an observed customer page")

    evidence: list[CompetitiveAiEvidence] = [
        CompetitiveAiEvidence(
            "CE-QUERY",
            "SEARCH_QUERY_CONTEXT",
            "SERP_OBSERVATION",
            {
                "query": analysis.selection.query,
                "customer_domain": analysis.selection.customer_domain,
                "customer_position": (
                    analysis.selection.customer_result.position
                    if analysis.selection.customer_result is not None
                    else None
                ),
                "candidate_count": len(analysis.selection.selected_candidates),
            },
            artifact_reference,
        ),
        CompetitiveAiEvidence(
            "CE-CUSTOMER",
            "CUSTOMER_PAGE_FEATURES",
            analysis.customer_page.final_url or analysis.customer_page.requested_url,
            _page_observed_value(analysis.customer_page),
            artifact_reference,
        ),
    ]
    for index, page in enumerate(analysis.competitor_pages, 1):
        if page.status.value != "OBSERVED":
            continue
        evidence.append(
            CompetitiveAiEvidence(
                f"CE-COMP-{index:03d}",
                "OBSERVED_LEADER_PAGE_FEATURES",
                page.final_url or page.requested_url,
                _page_observed_value(page),
                artifact_reference,
            )
        )
    for index, gap in enumerate(analysis.gaps, 1):
        evidence.append(
            CompetitiveAiEvidence(
                f"CE-GAP-{index:03d}",
                "DETERMINISTIC_CONTENT_DIFFERENCE",
                "RASAI_DETERMINISTIC_COMPARISON",
                {
                    "code": gap.code,
                    "severity": gap.severity,
                    "message": gap.message,
                    "customer_value": gap.customer_value,
                    "leader_reference": gap.leader_reference,
                    "evidence_urls": list(gap.evidence_urls),
                },
                artifact_reference,
            )
        )

    return CompetitiveAiInput(
        observation_id=observation_id,
        query=analysis.selection.query,
        market=market,
        language=language,
        ymyl_mode=mode,
        evidence=tuple(evidence),
    )


def competitive_ai_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query_intent": {"type": "string"},
            "ymyl_assessment": {"type": "string"},
            "summary": {"type": "string"},
            "opportunities": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "enum": [item.value for item in CompetitiveAiCategory],
                        },
                        "priority": {
                            "type": "string",
                            "enum": [item.value for item in CompetitiveAiPriority],
                        },
                        "title": {"type": "string"},
                        "recommendation": {"type": "string"},
                        "rationale": {"type": "string"},
                        "evidence_ids": {
                            "type": "array",
                            "minItems": 1,
                            "items": {"type": "string"},
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "causality_note": {"type": "string"},
                    },
                    "required": [
                        "category",
                        "priority",
                        "title",
                        "recommendation",
                        "rationale",
                        "evidence_ids",
                        "confidence",
                        "causality_note",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["query_intent", "ymyl_assessment", "summary", "opportunities"],
        "additionalProperties": False,
    }


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitiveAiContractError(f"{field} must be a non-empty string")
    return value.strip()


def normalize_competitive_ai_payload(
    payload: Any,
    *,
    allowed_evidence_ids: frozenset[str],
    provider: str,
    model: str | None,
    provider_request_id: str | None = None,
) -> CompetitiveAiAssessment:
    if not isinstance(payload, Mapping):
        raise CompetitiveAiContractError("competitive AI output must be an object")
    expected = {"query_intent", "ymyl_assessment", "summary", "opportunities"}
    if set(payload) != expected:
        raise CompetitiveAiContractError("competitive AI output has missing or unexpected fields")
    raw_opportunities = payload["opportunities"]
    if not isinstance(raw_opportunities, list) or len(raw_opportunities) > 12:
        raise CompetitiveAiContractError("opportunities must be an array with at most 12 items")

    opportunities: list[CompetitiveAiOpportunity] = []
    for raw in raw_opportunities:
        fields = {
            "category",
            "priority",
            "title",
            "recommendation",
            "rationale",
            "evidence_ids",
            "confidence",
            "causality_note",
        }
        if not isinstance(raw, Mapping) or set(raw) != fields:
            raise CompetitiveAiContractError("competitive AI opportunity has invalid fields")
        try:
            category = CompetitiveAiCategory(raw["category"])
            priority = CompetitiveAiPriority(raw["priority"])
        except (TypeError, ValueError) as exc:
            raise CompetitiveAiContractError("invalid opportunity category/priority") from exc
        evidence_ids_raw = raw["evidence_ids"]
        if (
            not isinstance(evidence_ids_raw, list)
            or not evidence_ids_raw
            or any(not isinstance(item, str) for item in evidence_ids_raw)
        ):
            raise CompetitiveAiEvidenceError("every opportunity requires evidence_ids")
        evidence_ids = tuple(dict.fromkeys(evidence_ids_raw))
        unknown = set(evidence_ids) - allowed_evidence_ids
        if unknown:
            raise CompetitiveAiEvidenceError(
                f"provider referenced unknown evidence_ids: {sorted(unknown)}"
            )
        confidence_raw = raw["confidence"]
        if isinstance(confidence_raw, bool) or not isinstance(confidence_raw, (int, float)):
            raise CompetitiveAiContractError("confidence must be numeric")
        confidence = float(confidence_raw)
        if not 0 <= confidence <= 1:
            raise CompetitiveAiContractError("confidence must be between 0 and 1")
        causality_note = _non_empty(raw["causality_note"], "causality_note")
        opportunities.append(
            CompetitiveAiOpportunity(
                category=category,
                priority=priority,
                title=_non_empty(raw["title"], "title"),
                recommendation=_non_empty(raw["recommendation"], "recommendation"),
                rationale=_non_empty(raw["rationale"], "rationale"),
                evidence_ids=evidence_ids,
                confidence=confidence,
                causality_note=causality_note,
            )
        )

    return CompetitiveAiAssessment(
        query_intent=_non_empty(payload["query_intent"], "query_intent"),
        ymyl_assessment=_non_empty(payload["ymyl_assessment"], "ymyl_assessment"),
        summary=_non_empty(payload["summary"], "summary"),
        opportunities=tuple(opportunities),
        provider=provider,
        model=model,
        provider_request_id=provider_request_id,
    )


class NoneCompetitiveAiProvider:
    name = "NONE"

    def analyze(self, competitive_input: CompetitiveAiInput) -> CompetitiveAiResult:
        del competitive_input
        return CompetitiveAiResult(
            CompetitiveAiState.NOT_CONFIGURED,
            reason="COMPETITIVE_AI_DISABLED",
        )


class FixtureCompetitiveAiProvider:
    name = "FIXTURE"

    def __init__(self, payload: Mapping[str, Any] | Path) -> None:
        if isinstance(payload, Path):
            loaded = json.loads(payload.read_text(encoding="utf-8"))
            if not isinstance(loaded, Mapping):
                raise ValueError("competitive AI fixture must contain one JSON object")
            self.payload = dict(loaded)
        else:
            self.payload = dict(payload)

    def analyze(self, competitive_input: CompetitiveAiInput) -> CompetitiveAiResult:
        try:
            assessment = normalize_competitive_ai_payload(
                self.payload,
                allowed_evidence_ids=competitive_input.allowed_evidence_ids,
                provider=self.name,
                model=None,
            )
        except CompetitiveAiContractError as exc:
            return CompetitiveAiResult(
                CompetitiveAiState.UNAVAILABLE,
                reason=f"COMPETITIVE_AI_CONTRACT_ERROR:{type(exc).__name__}:{exc}",
            )
        return CompetitiveAiResult(CompetitiveAiState.AVAILABLE, assessment=assessment)


Transport = Callable[[str, dict[str, str], bytes, float], Mapping[str, Any]]


def _http_transport(
    endpoint: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> Mapping[str, Any]:
    request = Request(endpoint, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise CompetitiveAiContractError("provider response must be a JSON object")
    return decoded


def _response_text(raw: Mapping[str, Any]) -> str:
    direct = raw.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    output = raw.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    return text
    raise CompetitiveAiContractError("provider response contains no output text")


class OpenAICompetitiveAiProvider:
    name = "OPENAI"

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        endpoint: str = "https://api.openai.com/v1/responses",
        reasoning_effort: str | None = None,
        timeout: float = 45.0,
        transport: Transport | None = None,
    ) -> None:
        registration = get_provider_registration("openai")
        default_model = registration.default_model if registration is not None else "gpt-5.6-terra"
        model_env = registration.model_env if registration is not None else "RASAI_OPENAI_MODEL"
        reasoning_env = (
            registration.reasoning_env
            if registration is not None and registration.reasoning_env
            else "RASAI_OPENAI_REASONING_EFFORT"
        )
        key_env = registration.key_env if registration is not None else "OPENAI_API_KEY"
        self.model = (model or os.environ.get(model_env) or default_model).strip()
        self.api_key = api_key if api_key is not None else os.environ.get(key_env)
        self.endpoint = endpoint
        self.reasoning_effort = (
            reasoning_effort or os.environ.get(reasoning_env) or "HIGH"
        ).strip().casefold()
        if self.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported OpenAI reasoning effort")
        if timeout <= 0:
            raise ValueError("competitive AI timeout must be > 0")
        self.timeout = timeout
        self._transport = transport or _http_transport
        self.calls = 0

    def _request_payload(self, competitive_input: CompetitiveAiInput) -> dict[str, Any]:
        instructions = (
            "Analyze only the supplied deterministic RASAI Search Intelligence evidence. "
            "Return content/search opportunities, not a ranking score. Never invent evidence_ids, "
            "facts, entities, competitor observations or causes. Every opportunity must cite at "
            "least one supplied evidence_id. Treat differences as correlational observations: "
            "never state or imply that a content difference caused a SERP position. "
            "For YMYL, obey ymyl_mode: ON means apply heightened caution; OFF means do not classify "
            "the page as YMYL; AUTO permits a cautious evidence-bound assessment. "
            "Recommendations may cover query intent, topic/entity coverage, information architecture, "
            "structured data, E-E-A-T/YMYL safeguards and SEO/AEO/GEO discoverability. "
            "Do not recommend deception, keyword stuffing, fake expertise, fake reviews or hidden text."
        )
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Competitive evidence JSON:\n"
                            + json.dumps(
                                competitive_input.provider_payload(),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "rasai_competitive_ai",
                    "strict": True,
                    "schema": competitive_ai_output_schema(),
                }
            },
        }
        if self.reasoning_effort != "none":
            payload["reasoning"] = {"effort": self.reasoning_effort}
        return payload

    def analyze(self, competitive_input: CompetitiveAiInput) -> CompetitiveAiResult:
        if not self.api_key:
            return CompetitiveAiResult(
                CompetitiveAiState.NOT_CONFIGURED,
                reason="COMPETITIVE_AI_NOT_CONFIGURED:OPENAI_API_KEY",
            )
        body = json.dumps(
            self._request_payload(competitive_input),
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            self.calls += 1
            raw = self._transport(
                self.endpoint,
                {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                body,
                self.timeout,
            )
            payload = json.loads(_response_text(raw))
            assessment = normalize_competitive_ai_payload(
                payload,
                allowed_evidence_ids=competitive_input.allowed_evidence_ids,
                provider=self.name,
                model=self.model,
                provider_request_id=(
                    str(raw.get("id")) if raw.get("id") is not None else None
                ),
            )
            return CompetitiveAiResult(CompetitiveAiState.AVAILABLE, assessment=assessment)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            CompetitiveAiContractError,
        ) as exc:
            return CompetitiveAiResult(
                CompetitiveAiState.UNAVAILABLE,
                reason=f"COMPETITIVE_AI_PROVIDER_UNAVAILABLE:{type(exc).__name__}:{str(exc)[:240]}",
            )


def build_competitive_ai_provider(
    provider: str,
    *,
    fixture_path: Path | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    timeout: float = 45.0,
) -> CompetitiveAiProvider:
    normalized = provider.strip().casefold()
    if normalized == "none":
        return NoneCompetitiveAiProvider()
    if normalized == "fixture":
        if fixture_path is None:
            raise ValueError("competitive AI fixture provider requires --ai-fixture")
        return FixtureCompetitiveAiProvider(fixture_path)
    if normalized == "openai":
        return OpenAICompetitiveAiProvider(
            model=model,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
        )
    raise ValueError(f"unsupported competitive AI provider: {provider}")
