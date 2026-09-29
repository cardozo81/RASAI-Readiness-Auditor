"""Importação opcional e sanitizada de calibração Dynatrace para M25.

A integração lê apenas configuração. O token é obtido de DYNATRACE_API_TOKEN,
nunca é retornado, persistido ou incluído em mensagens de erro.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

DYNATRACE_API_TOKEN_ENV = "DYNATRACE_API_TOKEN"

_KPM_MAP = {
    "ACTION_DURATION": "USER_ACTION_DURATION",
    "USER_ACTION_DURATION": "USER_ACTION_DURATION",
    "DOM_INTERACTIVE": "DOM_INTERACTIVE",
    "LOAD_EVENT_START": "LOAD_EVENT_START",
    "LOAD_EVENT_END": "LOAD_EVENT_END",
    "RESPONSE_START": "RESPONSE_START",
    "RESPONSE_END": "RESPONSE_END",
    "LARGEST_CONTENTFUL_PAINT": "LARGEST_CONTENTFUL_PAINT",
    "LCP": "LARGEST_CONTENTFUL_PAINT",
    "VISUALLY_COMPLETE": "VISUALLY_COMPLETE",
    "SPEED_INDEX": "SPEED_INDEX",
    "CUMULATIVE_LAYOUT_SHIFT": "CUMULATIVE_LAYOUT_SHIFT",
    "FIRST_INPUT_DELAY": "FIRST_INPUT_DELAY",
}

SUPPORTED_TIME_KPMS = frozenset({
    "USER_ACTION_DURATION",
    "DOM_INTERACTIVE",
    "LOAD_EVENT_START",
    "LOAD_EVENT_END",
    "RESPONSE_START",
    "RESPONSE_END",
    "LARGEST_CONTENTFUL_PAINT",
})


@dataclass(frozen=True, slots=True)
class DynatraceCalibration:
    source: str
    kpm: str
    satisfied_threshold_seconds: float
    frustrated_threshold_seconds: float
    errors_affect_apdex: bool | None
    metadata: dict[str, Any]


def load_dynatrace_calibration(
    *,
    base_url: str | None,
    application_id: str | None,
    config_json_path: str | None,
    timeout_seconds: float = 20.0,
) -> DynatraceCalibration:
    """Load calibration from exported JSON or the Dynatrace configuration API.

    Exported JSON is preferred for reproducible/offline audits. Live import uses
    GET /api/config/v1/applications/web/{id}; an additional error-rules GET is
    best-effort and only contributes sanitized metadata.
    """
    if config_json_path:
        path = Path(config_json_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Dynatrace config JSON inválido: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Dynatrace config JSON deve conter um objeto JSON")
        return parse_dynatrace_configuration(payload, source="DYNATRACE_EXPORTED_JSON")

    if not base_url or not application_id:
        raise ValueError("importação Dynatrace exige base URL e application ID")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Dynatrace base URL deve ser HTTPS e conter host válido")
    token = (os.environ.get(DYNATRACE_API_TOKEN_ENV) or "").strip()
    if not token:
        raise ValueError(f"{DYNATRACE_API_TOKEN_ENV} não configurado")

    normalized = base_url.rstrip("/")
    app_path = f"/api/config/v1/applications/web/{quote(application_id, safe='')}"
    payload = _get_json(normalized + app_path, token=token, timeout_seconds=timeout_seconds)
    if not isinstance(payload, dict):
        raise ValueError("Dynatrace retornou configuração de aplicação em formato inesperado")
    calibration = parse_dynatrace_configuration(payload, source="DYNATRACE_CONFIG_API")

    error_rules_summary: dict[str, Any]
    try:
        rules = _get_json(
            normalized + app_path + "/errorRules",
            token=token,
            timeout_seconds=timeout_seconds,
        )
        error_rules_summary = _summarize_error_rules(rules)
    except (ValueError, OSError):
        error_rules_summary = {"retrieved": False, "rule_count": None}

    metadata = dict(calibration.metadata)
    metadata["application_id"] = application_id
    metadata["error_rules"] = error_rules_summary
    metadata["error_policy"] = _error_policy_from_summary(
        error_rules_summary,
        fallback=metadata.get("error_policy"),
    )
    if isinstance(error_rules_summary.get("http_error_rules"), list):
        metadata["http_error_rules"] = error_rules_summary["http_error_rules"]
    metadata["token_persisted"] = False
    return DynatraceCalibration(
        source=calibration.source,
        kpm=calibration.kpm,
        satisfied_threshold_seconds=calibration.satisfied_threshold_seconds,
        frustrated_threshold_seconds=calibration.frustrated_threshold_seconds,
        errors_affect_apdex=calibration.errors_affect_apdex,
        metadata=metadata,
    )


def parse_dynatrace_configuration(payload: dict[str, Any], *, source: str) -> DynatraceCalibration:
    """Parse the complete web Apdex contract while executing only load semantics.

    RASAi M25 is a synthetic load-action envelope. XHR/custom action settings are
    retained as sanitized metadata for auditability, but are not executed as
    standalone actions because that would require a scripted clickpath/action
    definition. When Dynatrace selects a KPM not measurable by M25 and exposes
    fallback thresholds, M25 transparently uses User Action Duration, matching
    Dynatrace's documented fallback metric semantics without claiming to measure
    the unavailable primary KPM.
    """
    load = _action_contract(payload, "loadActionApdexSettings", "loadActionKeyPerformanceMetric")
    xhr = _action_contract(payload, "xhrActionApdexSettings", "xhrActionKeyPerformanceMetric")
    custom = _action_contract(payload, "customActionApdexSettings", None, fixed_kpm="USER_ACTION_DURATION")

    raw_kpm = load.get("raw_kpm") or "ACTION_DURATION"
    kpm = _normalize_kpm(raw_kpm)
    satisfied = load.get("satisfied_threshold_seconds")
    frustrated = load.get("frustrated_threshold_seconds")
    if satisfied is None or frustrated is None:
        raise ValueError("configuração Dynatrace não contém thresholds de Load Action suficientes")
    if satisfied <= 0 or frustrated <= satisfied:
        raise ValueError("thresholds Dynatrace inválidos: Frustrated deve ser maior que Satisfied/Tolerating")

    metadata = {
        "raw_kpm": raw_kpm,
        "requested_kpm": kpm,
        "kpm_supported_by_m25": kpm in SUPPORTED_TIME_KPMS,
        "satisfied_threshold_source": load.get("satisfied_threshold_source"),
        "frustrated_threshold_source": load.get("frustrated_threshold_source"),
        "fallback_satisfied_threshold_source": load.get("fallback_satisfied_threshold_source"),
        "fallback_frustrated_threshold_source": load.get("fallback_frustrated_threshold_source"),
        "errors_affect_apdex_observed": False,
        "error_policy": _error_policy_from_payload(payload),
        "http_error_rules": _extract_http_error_rules(payload),
        "custom_error_rules_observed": bool(_find_value(payload, "customErrorRules")),
        "dynatrace_capture_contract": {
            "javascript_errors": _find_value(payload, "javaScriptErrors"),
            "max_errors_to_capture": _find_value(payload, "maxErrorsToCapture"),
            "xhr_enabled": _find_value(payload, "xmlHttpRequest"),
            "fetch_enabled": _find_value(payload, "fetchRequests"),
            "console_errors": _custom_configuration_properties(payload).get("cce") in {"1", "true", "yes", "on"},
            "custom_configuration_properties_observed": bool(_find_value(payload, "customConfigurationProperties")),
        },
        "raw_configuration_persisted": False,
        "standalone_action_support": {
            "load": "EXECUTABLE",
            "xhr": "OBSERVED_INSIDE_LOAD_ONLY_NOT_STANDALONE",
            "custom": "NOT_EXECUTABLE_WITHOUT_SCRIPTED_ACTION",
        },
        "dynatrace_apdex_contract": {
            "load": load,
            "xhr": xhr,
            "custom": custom,
        },
    }

    errors = _find_bool(
        payload,
        (
            "frustratingIfReportedOrWebRequestError",
            "errorsAffectApdex",
            "considerErrors",
        ),
    )
    metadata["errors_affect_apdex_observed"] = errors is not None

    if kpm not in SUPPORTED_TIME_KPMS:
        fallback_satisfied = load.get("fallback_satisfied_threshold_seconds")
        fallback_frustrated = load.get("fallback_frustrated_threshold_seconds")
        if fallback_satisfied is None or fallback_frustrated is None:
            raise ValueError(
                f"Dynatrace usa KPM {kpm}, não mensurável com equivalência suficiente no Synthetic User Experience Apdex, "
                "e a configuração não fornece thresholds de fallback para User Action Duration"
            )
        if fallback_satisfied <= 0 or fallback_frustrated <= fallback_satisfied:
            raise ValueError("thresholds Dynatrace de fallback inválidos")
        metadata["rasai_capability_fallback_applied"] = True
        metadata["fallback_reason"] = f"PRIMARY_KPM_NOT_VENDOR_EQUIVALENT:{kpm}"
        metadata["effective_kpm"] = "USER_ACTION_DURATION"
        kpm = "USER_ACTION_DURATION"
        satisfied = float(fallback_satisfied)
        frustrated = float(fallback_frustrated)
        source += "+RASAI_CAPABILITY_FALLBACK"
    else:
        metadata["rasai_capability_fallback_applied"] = False
        metadata["effective_kpm"] = kpm

    return DynatraceCalibration(
        source=source,
        kpm=kpm,
        satisfied_threshold_seconds=float(satisfied),
        frustrated_threshold_seconds=float(frustrated),
        errors_affect_apdex=errors,
        metadata=metadata,
    )


def _action_contract(
    payload: dict[str, Any],
    settings_key: str,
    kpm_key: str | None,
    *,
    fixed_kpm: str | None = None,
) -> dict[str, Any]:
    settings = payload.get(settings_key)
    if not isinstance(settings, dict):
        settings = _find_dict(payload, settings_key) or {}

    raw_kpm: Any = fixed_kpm
    if kpm_key:
        raw_kpm = payload.get(kpm_key)
        if isinstance(raw_kpm, dict):
            raw_kpm = raw_kpm.get("metric") or raw_kpm.get("value") or raw_kpm.get("keyPerformanceMetric")
        if raw_kpm is None:
            raw_kpm = _find_value(payload, kpm_key)

    satisfied, sat_source = _threshold_local(settings, "toleratedThresholdSeconds", "toleratedThreshold")
    frustrated, fr_source = _threshold_local(settings, "frustratingThresholdSeconds", "frustratingThreshold")
    fallback_satisfied, fallback_sat_source = _threshold_local(
        settings, "toleratedFallbackThresholdSeconds", "toleratedFallbackThreshold"
    )
    fallback_frustrated, fallback_fr_source = _threshold_local(
        settings, "frustratingFallbackThresholdSeconds", "frustratingFallbackThreshold"
    )
    return {
        "raw_kpm": raw_kpm,
        "normalized_kpm": _normalize_kpm(raw_kpm) if raw_kpm else None,
        "satisfied_threshold_seconds": satisfied,
        "frustrated_threshold_seconds": frustrated,
        "fallback_kpm": "USER_ACTION_DURATION" if fallback_satisfied is not None or fallback_frustrated is not None else None,
        "fallback_satisfied_threshold_seconds": fallback_satisfied,
        "fallback_frustrated_threshold_seconds": fallback_frustrated,
        "satisfied_threshold_source": sat_source,
        "frustrated_threshold_source": fr_source,
        "fallback_satisfied_threshold_source": fallback_sat_source,
        "fallback_frustrated_threshold_source": fallback_fr_source,
    }


def _normalize_kpm(value: Any) -> str:
    raw = str(value or "ACTION_DURATION").strip().upper()
    return _KPM_MAP.get(raw, raw)


def _threshold_local(
    settings: dict[str, Any],
    seconds_name: str,
    milliseconds_name: str,
) -> tuple[float | None, str | None]:
    value = settings.get(seconds_name)
    if value is not None:
        try:
            return float(value), f"{seconds_name}:seconds"
        except (TypeError, ValueError) as exc:
            raise ValueError(f"threshold Dynatrace {seconds_name} inválido") from exc

    value = settings.get(milliseconds_name)
    if value is None:
        return None, None
    try:
        return float(value) / 1000.0, f"{milliseconds_name}:milliseconds"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"threshold Dynatrace {milliseconds_name} inválido") from exc


def _threshold(
    settings: dict[str, Any],
    payload: dict[str, Any],
    seconds_name: str,
    milliseconds_name: str,
) -> tuple[float | None, str | None]:
    value = settings.get(seconds_name)
    if value is None:
        value = _find_value(payload, seconds_name)
    if value is not None:
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"threshold Dynatrace {seconds_name} inválido") from exc
        return result, f"{seconds_name}:seconds"

    value = settings.get(milliseconds_name)
    if value is None:
        value = _find_value(payload, milliseconds_name)
    if value is None:
        return None, None
    try:
        result = float(value) / 1000.0
    except (TypeError, ValueError) as exc:
        raise ValueError(f"threshold Dynatrace {milliseconds_name} inválido") from exc
    return result, f"{milliseconds_name}:milliseconds"


def _custom_configuration_properties(payload: dict[str, Any]) -> dict[str, str]:
    raw = _find_value(payload, "customConfigurationProperties")
    if not isinstance(raw, str):
        return {}
    pairs: dict[str, str] = {}
    for item in raw.replace(";", "|").split("|"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        pairs[key.strip().casefold()] = value.strip().casefold()
    return pairs


def _error_policy_from_payload(payload: dict[str, Any]) -> dict[str, bool]:
    """Translate only Dynatrace error/capture switches that have direct M25 semantics."""
    summary: dict[str, Any] = {}
    for key in (
        "ignoreJavaScriptErrorsInApdexCalculation",
        "ignoreHttpErrorsInApdexCalculation",
        "ignoreRequestErrorsInApdexCalculation",
    ):
        value = _find_value(payload, key)
        if isinstance(value, bool):
            summary[key] = value

    policy = _error_policy_from_summary(summary)
    javascript_capture = _find_value(payload, "javaScriptErrors")
    if isinstance(javascript_capture, bool) and not javascript_capture:
        policy["javascript_errors_affect_apdex"] = False

    custom_properties = _custom_configuration_properties(payload)
    if custom_properties.get("cce") in {"1", "true", "yes", "on"}:
        policy["console_errors_affect_apdex"] = True

    return policy


def _error_policy_from_summary(
    summary: dict[str, Any],
    *,
    fallback: Any = None,
) -> dict[str, bool]:
    base = dict(fallback) if isinstance(fallback, dict) else {}
    javascript = bool(base.get("javascript_errors_affect_apdex", True))
    request = bool(base.get("request_errors_affect_apdex", True))
    console = bool(base.get("console_errors_affect_apdex", False))

    if isinstance(summary.get("ignoreJavaScriptErrorsInApdexCalculation"), bool):
        javascript = not bool(summary["ignoreJavaScriptErrorsInApdexCalculation"])
    request_ignores = [
        summary.get("ignoreHttpErrorsInApdexCalculation"),
        summary.get("ignoreRequestErrorsInApdexCalculation"),
    ]
    explicit_request = [value for value in request_ignores if isinstance(value, bool)]
    if explicit_request:
        request = not all(explicit_request)

    return {
        "javascript_errors_affect_apdex": javascript,
        "request_errors_affect_apdex": request,
        "console_errors_affect_apdex": console,
    }


def _normalize_matcher(value: Any) -> str:
    matcher = str(value or "").strip().upper()
    return matcher if matcher in {"BEGINS_WITH", "ENDS_WITH", "CONTAINS", "EQUALS"} else ""


def _sanitize_http_error_rule(rule: Any) -> dict[str, Any] | None:
    if not isinstance(rule, dict):
        return None

    # Configuration API (legacy/current compatibility surface).
    if "captureSettings" not in rule:
        return {
            "capture": bool(rule.get("capture", True)),
            "impact_apdex": bool(rule.get("impactApdex", True)),
            "error_codes": str(rule.get("errorCodes") or "").strip()[:256],
            "consider_csp": bool(rule.get("considerBlockedRequests", False)),
            "consider_failed_images": bool(rule.get("considerFailedImages", False)),
            "consider_unknown": bool(rule.get("considerUnknownErrorCode", False)),
            "filter_by_url": bool(rule.get("filterByUrl", False)),
            "url_matcher": _normalize_matcher(rule.get("filter")),
            "url": str(rule.get("url") or "").strip()[:2048],
        }

    # Settings API / exported settings representation.
    capture = rule.get("captureSettings")
    capture = capture if isinstance(capture, dict) else {}
    filter_settings = rule.get("filterSettings")
    filter_settings = filter_settings if isinstance(filter_settings, dict) else {}
    url = str(filter_settings.get("url") or "").strip()[:2048]
    matcher = _normalize_matcher(filter_settings.get("filter"))
    return {
        "capture": bool(capture.get("capture", True)),
        "impact_apdex": bool(capture.get("impactApdex", True)),
        "error_codes": str(rule.get("errorCodes") or "").strip()[:256],
        "consider_csp": bool(rule.get("considerCspViolations", False)),
        "consider_failed_images": bool(rule.get("considerFailedImages", False)),
        "consider_unknown": bool(rule.get("considerUnknownErrorCode", False)),
        "filter_by_url": bool(url),
        "url_matcher": matcher,
        "url": url,
    }


def _extract_http_error_rules(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, (dict, list)):
        return []

    candidates: Any = _find_value(payload, "httpErrorRules")
    if not isinstance(candidates, list):
        generic = _find_value(payload, "errorRules")
        if isinstance(generic, list) and any(
            isinstance(item, dict) and (
                "captureSettings" in item
                or "considerCspViolations" in item
                or "considerFailedImages" in item
            )
            for item in generic
        ):
            candidates = generic

    if not isinstance(candidates, list):
        return []
    result: list[dict[str, Any]] = []
    for raw in candidates[:100]:
        item = _sanitize_http_error_rule(raw)
        if item is not None:
            result.append(item)
    return result


def _summarize_error_rules(rules: Any) -> dict[str, Any]:
    if isinstance(rules, list):
        return {"retrieved": True, "rule_count": len(rules)}
    if not isinstance(rules, dict):
        return {"retrieved": True, "rule_count": None}
    values = rules.get("values") or rules.get("rules") or []
    http_rules = _extract_http_error_rules(rules)
    summary: dict[str, Any] = {
        "retrieved": True,
        "rule_count": len(values) if isinstance(values, list) else (
            len(rules.get("httpErrorRules", [])) if isinstance(rules.get("httpErrorRules"), list) else None
        ),
        "http_error_rules": http_rules,
        "custom_error_rule_count": len(rules.get("customErrorRules", []))
        if isinstance(rules.get("customErrorRules"), list) else 0,
    }
    for key in (
        "ignoreCustomErrorsInApdexCalculation",
        "ignoreHttpErrorsInApdexCalculation",
        "ignoreJavaScriptErrorsInApdexCalculation",
        "ignoreRequestErrorsInApdexCalculation",
    ):
        value = rules.get(key)
        if isinstance(value, bool):
            summary[key] = value
    return summary


def _find_dict(value: Any, key: str) -> dict[str, Any] | None:
    found = _find_value(value, key)
    return found if isinstance(found, dict) else None


def _find_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _find_value(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_value(child, key)
            if found is not None:
                return found
    return None


def _find_bool(value: Any, keys: tuple[str, ...]) -> bool | None:
    for key in keys:
        found = _find_value(value, key)
        if isinstance(found, bool):
            return found
    return None


def _get_json(url: str, *, token: str, timeout_seconds: float) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Api-Token {token}",
            "User-Agent": "RASAI-Readiness-Auditor/M25",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(2_000_000)
    except HTTPError as exc:
        raise ValueError(f"Dynatrace Config API HTTP {exc.code}") from exc
    except URLError as exc:
        raise OSError("Dynatrace Config API indisponível") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Dynatrace Config API retornou JSON inválido") from exc
