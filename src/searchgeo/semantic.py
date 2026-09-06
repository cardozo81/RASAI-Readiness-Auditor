"""Provider-independent semantic analysis contracts and OpenAI adapter for M7."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
import os
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from searchgeo.domain import RuleResult


SEMANTIC_RULE_IDS = tuple(f"BR-GEO-{number:03d}" for number in range(28, 50))


class EntityType(StrEnum):
    ORGANIZATION = "ORGANIZATION"
    PERSON = "PERSON"
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"
    PLACE = "PLACE"
    BRAND = "BRAND"
    TOPIC = "TOPIC"
    OTHER = "OTHER"


class ProviderState(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNAVAILABLE = "UNAVAILABLE"


class SemanticProviderError(RuntimeError):
    pass


class SemanticSchemaError(ValueError):
    pass


class SemanticEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticEvidenceInput:
    evidence_id: str
    evidence_type: str
    source: str
    observed_value: Any
    artifact_reference: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticInput:
    snapshot_id: str
    page_url: str
    title: str | None
    main_content: str
    structured_data: Any
    primary_language: str
    market: str
    evidence: tuple[SemanticEvidenceInput, ...]

    @property
    def allowed_evidence_ids(self) -> frozenset[str]:
        return frozenset(item.evidence_id for item in self.evidence)

    def provider_payload(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "page_url": self.page_url,
            "title": self.title,
            "main_content": self.main_content,
            "structured_data": self.structured_data,
            "primary_language": self.primary_language,
            "market": self.market,
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
class SemanticRuleAssessment:
    rule_id: str
    result: RuleResult
    confidence: float
    evidence_ids: tuple[str, ...]
    reasoning_summary: str
    observed_value: Any = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EntityCandidate:
    name: str
    entity_type: EntityType
    confidence: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SemanticProviderResponse:
    assessments: tuple[SemanticRuleAssessment, ...]
    entities: tuple[EntityCandidate, ...]
    primary_intent: str | None
    secondary_intents: tuple[str, ...]
    provider: str
    model: str | None
    configuration_version: str
    prompt_id: str
    prompt_version: str


@dataclass(frozen=True, slots=True)
class ProviderCallResult:
    state: ProviderState
    response: SemanticProviderResponse | None = None
    reason: str | None = None


class SemanticAnalysisProvider(Protocol):
    name: str

    def analyze(self, semantic_input: SemanticInput) -> ProviderCallResult:
        ...


class NoneProvider:
    """Mandatory provider used when semantic AI is not configured."""

    name = "NONE"

    def analyze(self, semantic_input: SemanticInput) -> ProviderCallResult:
        del semantic_input
        return ProviderCallResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED")


Transport = Callable[[str, dict[str, str], bytes, float], dict[str, Any]]


class OpenAIProvider:
    """OpenAI Responses API adapter with injectable transport and strict normalization."""

    name = "OPENAI"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        endpoint: str = "https://api.openai.com/v1/responses",
        timeout: float = 45.0,
        configuration_version: str = "1",
        prompt_id: str = "searchgeo-semantic-v1",
        prompt_version: str = "1",
        transport: Transport | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("OpenAI model must be configured")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.model = model.strip()
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.endpoint = endpoint
        self.timeout = timeout
        self.configuration_version = configuration_version
        self.prompt_id = prompt_id
        self.prompt_version = prompt_version
        self._transport = transport or _http_transport

    def analyze(self, semantic_input: SemanticInput) -> ProviderCallResult:
        if not self.api_key:
            return ProviderCallResult(ProviderState.NOT_CONFIGURED, reason="AI_NOT_CONFIGURED")
        body = json.dumps(self._request_payload(semantic_input), ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            raw = self._transport(self.endpoint, headers, body, self.timeout)
            payload = _extract_json_payload(raw)
            normalized = normalize_provider_payload(
                payload,
                semantic_input.allowed_evidence_ids,
                provider=self.name,
                model=self.model,
                configuration_version=self.configuration_version,
                prompt_id=self.prompt_id,
                prompt_version=self.prompt_version,
            )
            return ProviderCallResult(ProviderState.AVAILABLE, response=normalized)
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            SemanticProviderError,
            SemanticSchemaError,
            SemanticEvidenceError,
            json.JSONDecodeError,
            UnicodeError,
        ) as exc:
            return ProviderCallResult(
                ProviderState.UNAVAILABLE,
                reason=f"AI_PROVIDER_UNAVAILABLE:{type(exc).__name__}",
            )

    def _request_payload(self, semantic_input: SemanticInput) -> dict[str, Any]:
        instructions = (
            "Evaluate only the supplied page evidence for Search/GEO readiness. "
            "Return JSON matching the schema. Never invent evidence_ids. "
            "Use UNKNOWN when the supplied evidence is insufficient. "
            "Do not infer hidden facts or score the website."
        )
        return {
            "model": self.model,
            "instructions": instructions,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "JSON page evidence:\n"
                            + json.dumps(semantic_input.provider_payload(), ensure_ascii=False),
                        }
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "searchgeo_semantic_assessment",
                    "strict": True,
                    "schema": semantic_output_schema(),
                }
            },
        }


def semantic_output_schema() -> dict[str, Any]:
    result_values = [
        RuleResult.PASS.value,
        RuleResult.FAIL.value,
        RuleResult.WARNING.value,
        RuleResult.UNKNOWN.value,
        RuleResult.NOT_APPLICABLE.value,
    ]
    entity_values = [item.value for item in EntityType]
    observed_value_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "details": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["summary", "details"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rule_id": {"type": "string", "enum": list(SEMANTIC_RULE_IDS)},
                        "result": {"type": "string", "enum": result_values},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "reasoning_summary": {"type": "string"},
                        "observed_value": observed_value_schema,
                    },
                    "required": [
                        "rule_id",
                        "result",
                        "confidence",
                        "evidence_ids",
                        "reasoning_summary",
                        "observed_value",
                    ],
                    "additionalProperties": False,
                },
            },
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "entity_type": {"type": "string", "enum": entity_values},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "evidence_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["name", "entity_type", "confidence", "evidence_ids"],
                    "additionalProperties": False,
                },
            },
            "primary_intent": {"type": ["string", "null"]},
            "secondary_intents": {
                "type": "array",
                "maxItems": 5,
                "items": {"type": "string"},
            },
        },
        "required": [
            "assessments",
            "entities",
            "primary_intent",
            "secondary_intents",
        ],
        "additionalProperties": False,
    }


def normalize_provider_payload(
    payload: Any,
    allowed_evidence_ids: frozenset[str],
    *,
    provider: str,
    model: str | None,
    configuration_version: str,
    prompt_id: str,
    prompt_version: str,
) -> SemanticProviderResponse:
    if not isinstance(payload, dict):
        raise SemanticSchemaError("provider output must be an object")
    expected = {"assessments", "entities", "primary_intent", "secondary_intents"}
    if set(payload) != expected:
        raise SemanticSchemaError("provider output has missing or unexpected top-level fields")
    raw_assessments = payload["assessments"]
    raw_entities = payload["entities"]
    primary_intent = payload["primary_intent"]
    secondary = payload["secondary_intents"]
    if not isinstance(raw_assessments, list) or not isinstance(raw_entities, list):
        raise SemanticSchemaError("assessments and entities must be arrays")
    if primary_intent is not None and (
        not isinstance(primary_intent, str) or not primary_intent.strip()
    ):
        raise SemanticSchemaError("primary_intent must be a non-empty string or null")
    if (
        not isinstance(secondary, list)
        or len(secondary) > 5
        or any(not isinstance(item, str) or not item.strip() for item in secondary)
    ):
        raise SemanticSchemaError(
            "secondary_intents must contain at most five non-empty strings"
        )

    assessments: list[SemanticRuleAssessment] = []
    seen_rules: set[str] = set()
    for raw in raw_assessments:
        if not isinstance(raw, dict):
            raise SemanticSchemaError("assessment must be an object")
        required = {
            "rule_id",
            "result",
            "confidence",
            "evidence_ids",
            "reasoning_summary",
            "observed_value",
        }
        if set(raw) != required:
            raise SemanticSchemaError("assessment has missing or unexpected fields")
        rule_id = raw["rule_id"]
        if rule_id not in SEMANTIC_RULE_IDS or rule_id in seen_rules:
            raise SemanticSchemaError(f"invalid or duplicate semantic rule: {rule_id}")
        seen_rules.add(rule_id)
        try:
            result = RuleResult(raw["result"])
        except (TypeError, ValueError) as exc:
            raise SemanticSchemaError(f"invalid result for {rule_id}") from exc
        if result is RuleResult.ERROR:
            raise SemanticSchemaError("provider cannot publish ERROR as website assessment")
        confidence = _confidence(raw["confidence"])
        evidence_ids = _evidence_ids(raw["evidence_ids"], allowed_evidence_ids)
        if (
            result not in {RuleResult.UNKNOWN, RuleResult.NOT_APPLICABLE}
            and not evidence_ids
        ):
            raise SemanticEvidenceError(
                f"{rule_id} requires source evidence for {result.value}"
            )
        summary = raw["reasoning_summary"]
        if not isinstance(summary, str):
            raise SemanticSchemaError("reasoning_summary must be a string")
        observed_value = _observed_value(raw["observed_value"])
        assessments.append(
            SemanticRuleAssessment(
                rule_id=rule_id,
                result=result,
                confidence=confidence,
                evidence_ids=evidence_ids,
                reasoning_summary=summary.strip(),
                observed_value=observed_value,
            )
        )

    entities: list[EntityCandidate] = []
    for raw in raw_entities:
        if (
            not isinstance(raw, dict)
            or set(raw) != {"name", "entity_type", "confidence", "evidence_ids"}
        ):
            raise SemanticSchemaError("entity has invalid fields")
        name = raw["name"]
        if not isinstance(name, str) or not name.strip():
            raise SemanticSchemaError("entity name must be non-empty")
        try:
            entity_type = EntityType(raw["entity_type"])
        except (TypeError, ValueError) as exc:
            raise SemanticSchemaError("invalid entity_type") from exc
        evidence_ids = _evidence_ids(raw["evidence_ids"], allowed_evidence_ids)
        if not evidence_ids:
            raise SemanticEvidenceError("entity observations require source evidence")
        entities.append(
            EntityCandidate(
                name.strip(),
                entity_type,
                _confidence(raw["confidence"]),
                evidence_ids,
            )
        )

    return SemanticProviderResponse(
        assessments=tuple(assessments),
        entities=tuple(entities),
        primary_intent=primary_intent.strip() if isinstance(primary_intent, str) else None,
        secondary_intents=tuple(item.strip() for item in secondary),
        provider=provider,
        model=model,
        configuration_version=configuration_version,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
    )


def _confidence(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SemanticSchemaError("confidence must be numeric")
    confidence = float(value)
    if not 0 <= confidence <= 1:
        raise SemanticSchemaError("confidence must be between 0 and 1")
    return confidence


def _evidence_ids(value: Any, allowed: frozenset[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise SemanticSchemaError("evidence_ids must be an array of strings")
    ids = tuple(dict.fromkeys(value))
    unknown = set(ids) - allowed
    if unknown:
        raise SemanticEvidenceError(
            f"provider referenced unknown evidence_ids: {sorted(unknown)}"
        )
    return ids


def _observed_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"summary", "details"}:
        raise SemanticSchemaError(
            "observed_value must contain exactly summary and details"
        )
    summary = value["summary"]
    details = value["details"]
    if not isinstance(summary, str):
        raise SemanticSchemaError("observed_value.summary must be a string")
    if not isinstance(details, list) or any(not isinstance(item, str) for item in details):
        raise SemanticSchemaError(
            "observed_value.details must be an array of strings"
        )
    return {
        "summary": summary.strip(),
        "details": [item.strip() for item in details],
    }


def _decode_json_text(text: str) -> Any:
    candidate = text.strip().lstrip("\ufeff")
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as first_error:
        lines = candidate.splitlines()
        if len(lines) < 3:
            raise first_error
        opening = lines[0].strip().casefold()
        closing = lines[-1].strip()
        if opening not in {"```", "```json"} or closing != "```":
            raise first_error
        return json.loads("\n".join(lines[1:-1]).strip())


def _extract_json_payload(response: dict[str, Any]) -> Any:
    if not isinstance(response, dict):
        raise SemanticProviderError("provider response envelope must be an object")
    if isinstance(response.get("output_text"), str):
        return _decode_json_text(response["output_text"])
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if (
                isinstance(content, dict)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                return _decode_json_text(content["text"])
    raise SemanticProviderError("OpenAI response contained no output_text")


def _http_transport(
    url: str,
    headers: dict[str, str],
    body: bytes,
    timeout: float,
) -> dict[str, Any]:
    request = Request(url, data=body, headers=headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise SemanticProviderError("OpenAI response envelope must be an object")
    return decoded
