"""#355: offline adapter for exported Dynatrace Settings 2.0 effectiveValues JSON.

Only the official RUM web Apdex schema values are translated. This adapter
neither authenticates against Dynatrace nor proves the scope or real action
population of an operator-supplied export. Missing or paginated data abstain.
No HTTP, tokens, persistence, engine changes, or new numeric thresholds.
"""
from __future__ import annotations

from typing import Any, Mapping

VERSION = "RASAI-DYNATRACE-EFFECTIVE-VALUES-ADAPTER-001"
SCHEMA_TO_ACTION = {
    "builtin:rum.web.key-performance-metric-load-actions": "load_actions",
    "builtin:rum.web.key-performance-metric-xhr-actions": "xhr_actions",
    "builtin:rum.web.key-performance-metric-custom-actions": "custom_actions",
}


def extract_apdex_from_effective_values(
    payload: Mapping[str, Any], *, declared_application_scope: str,
) -> dict[str, Any]:
    """Map an exported *complete single response*; never presume verified RUM.

    The Settings API effectiveValues response has items, schemaId and value,
    but does not authenticate its own file or show which app was queried.
    The operator-declared scope is metadata only, NOT independently verified.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("effectiveValues JSON must be an object")
    if (
        not isinstance(declared_application_scope, str)
        or not declared_application_scope.startswith("APPLICATION-")
        or not 12 <= len(declared_application_scope) <= 100
        or not all(x.isalnum() or x == "-" for x in declared_application_scope)
    ):
        raise ValueError("expected a declared APPLICATION-... scope")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > 100:
        raise ValueError("missing or oversized Settings API items list")
    # Paged / incomplete results cannot be interpreted as action absence.
    if payload.get("nextPageKey") not in (None, ""):
        raise ValueError("paginated effectiveValues export is incomplete")
    if (
        "totalCount" in payload
        and (type(payload["totalCount"]) is not int
             or payload["totalCount"] != len(items))
    ):
        raise ValueError("effectiveValues totalCount inconsistent with items")
    result: dict[str, Any] = {}
    versions: dict[str, str] = {}
    origins: dict[str, str] = {}
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("invalid Settings API item")
        schema = item.get("schemaId")
        if not isinstance(schema, str) or schema not in SCHEMA_TO_ACTION:
            # A response may contain other scopes/schemas, but its provenance
            # cannot establish RUM action type without a known schema.
            raise ValueError("unexpected schemaId in Apdex effectiveValues export")
        if schema in seen:
            raise ValueError("ambiguous duplicate RUM Apdex schemaId")
        seen.add(schema)
        value = item.get("value")
        if not isinstance(value, Mapping):
            raise ValueError("effectiveValues item lacks a settings value object")
        action = SCHEMA_TO_ACTION[schema]
        allowed = {"kpm", "thresholds", "fallbackThresholds"}
        if action == "custom_actions":
            allowed = {"thresholds"}
        # Only preserve documented values, no arbitrary import of provider
        # metadata into RASAi's execution settings.
        projected = {k: value[k] for k in allowed if k in value}
        if not projected:
            raise ValueError("RUM Apdex settings value is empty")
        result[action] = projected
        version = item.get("schemaVersion")
        origin = item.get("origin")
        if isinstance(version, str) and len(version) <= 60:
            versions[action] = version
        if isinstance(origin, str) and len(origin) <= 100:
            origins[action] = origin
    return {
        "contract_version": VERSION,
        "settings": result,
        "declared_application_scope": declared_application_scope,
        "scope_provenance": "OPERATOR_DECLARED_NOT_VERIFIED_FROM_FILE",
        "settings_provenance": "OPERATOR_SUPPLIED_API_EXPORT_NOT_TENANT_VERIFIED",
        "schema_versions": versions,
        "effective_value_origins": origins,
        "population_measured": False,
        "action_counts_available": False,
        "capture_flags_available": False,
        "dynatrace_provider_requests": 0,
        "rasai_audit_writes": 0,
    }
