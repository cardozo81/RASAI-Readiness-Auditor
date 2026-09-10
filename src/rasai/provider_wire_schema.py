"""Provider-specific JSON Schema projection at the external wire boundary.

RASAi keeps its canonical/local validation contracts independent from provider wire
subsets.  This module only transforms schemas embedded in outgoing request payloads;
it never changes deterministic evidence, scoring, or the local validators that
consume a provider response.
"""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Mapping

# Constraint keywords observed to be outside the strict Structured Outputs subset
# used by the OpenAI Responses adapter in the RASAi integration.  Local RASAi
# validators remain responsible for these constraints after the response arrives.
_OPENAI_WIRE_DROPPED_KEYWORDS = frozenset({
    "minLength",
    "maxLength",
    "pattern",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minItems",
    "maxItems",
    "uniqueItems",
    "minProperties",
    "maxProperties",
})


def openai_wire_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Project a canonical schema to the strict OpenAI wire subset used by RASAi.

    Structural constraints (types, object properties, required fields,
    additionalProperties, arrays, enums and nullable type unions) are preserved.
    Value/length/cardinality constraints are enforced by the existing local
    contract validators instead of being sent as unsupported wire keywords.
    """

    def project(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): project(item)
                for key, item in value.items()
                if str(key) not in _OPENAI_WIRE_DROPPED_KEYWORDS
            }
        if isinstance(value, list):
            return [project(item) for item in value]
        if isinstance(value, tuple):
            return [project(item) for item in value]
        return deepcopy(value)

    projected = project(schema)
    if not isinstance(projected, dict):
        raise TypeError("projected OpenAI schema must remain an object")
    return projected


def project_provider_request_payload(provider_name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project structured-output schemas in one outbound provider payload.

    Only known schema-bearing request locations are touched. User/page content is
    not recursively rewritten merely because it happens to contain a key named
    ``schema``.
    """
    output = deepcopy(dict(payload))
    if provider_name.strip().upper() != "OPENAI":
        return output

    text = output.get("text")
    if isinstance(text, dict):
        fmt = text.get("format")
        if isinstance(fmt, dict) and isinstance(fmt.get("schema"), Mapping):
            fmt["schema"] = openai_wire_schema(fmt["schema"])

    response_format = output.get("response_format")
    if isinstance(response_format, dict):
        json_schema = response_format.get("json_schema")
        if isinstance(json_schema, dict) and isinstance(json_schema.get("schema"), Mapping):
            json_schema["schema"] = openai_wire_schema(json_schema["schema"])

    tools = output.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            function = tool.get("function")
            if isinstance(function, dict) and isinstance(function.get("parameters"), Mapping):
                function["parameters"] = openai_wire_schema(function["parameters"])

    return output


def project_provider_request_body(provider_name: str, body: bytes) -> bytes:
    """Return the exact body that should be sent to a provider transport."""
    if provider_name.strip().upper() != "OPENAI":
        return body
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return body
    if not isinstance(decoded, Mapping):
        return body
    projected = project_provider_request_payload(provider_name, decoded)
    if projected == decoded:
        return body
    return json.dumps(projected, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
