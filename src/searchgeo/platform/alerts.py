"""Deterministic alert evaluation and local/webhook delivery for RASAi."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from searchgeo.monitoring.models import ChangeEvent, ComparisonResult

from .models import AlertRule
from .store import PlatformStore, utc_now

_SEVERITY = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True, slots=True)
class AlertMatch:
    rule: AlertRule
    events: tuple[ChangeEvent, ...]


@dataclass(frozen=True, slots=True)
class AlertDelivery:
    alert_rule_id: str
    status: str
    destination: str
    notification_id: str
    error: str | None = None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


def match_alert_rules(
    result: ComparisonResult,
    rules: list[AlertRule],
) -> tuple[AlertMatch, ...]:
    matches: list[AlertMatch] = []
    for rule in rules:
        if not rule.enabled:
            continue
        minimum = _SEVERITY.get(rule.min_severity.upper(), 3)
        statuses = {item.upper() for item in rule.event_statuses}
        events = tuple(
            event
            for event in result.events
            if event.material
            and event.status.upper() in statuses
            and _SEVERITY.get(event.severity.upper(), 0) >= minimum
        )
        if events:
            matches.append(AlertMatch(rule, events))
    return tuple(matches)


def _payload(match: AlertMatch, result: ComparisonResult) -> dict[str, Any]:
    return {
        "schema": "RASAI-ALERT-001",
        "generated_at": utc_now(),
        "baseline_audit_id": result.baseline.audit_id,
        "current_audit_id": result.current.audit_id,
        "rule": {
            "alert_rule_id": match.rule.alert_rule_id,
            "name": match.rule.name,
            "min_severity": match.rule.min_severity,
            "event_statuses": list(match.rule.event_statuses),
        },
        "events": [asdict(event) for event in match.events],
    }


def _validate_webhook(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise ValueError("webhook URL must be absolute HTTP(S)")
    if parts.username or parts.password:
        raise ValueError("webhook URL must not embed credentials")
    if parts.scheme != "https" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("non-local webhook URL must use HTTPS")


def deliver_alert_match(
    store: PlatformStore,
    match: AlertMatch,
    result: ComparisonResult,
    *,
    comparison_id: str | None = None,
    milestone_id: str | None = None,
    timeout_seconds: int = 15,
) -> AlertDelivery:
    payload = _payload(match, result)
    destination = match.rule.destination.upper()
    if destination in {"NONE", "JSON"}:
        notification_id = store.add_notification(
            alert_rule_id=match.rule.alert_rule_id,
            comparison_id=comparison_id,
            milestone_id=milestone_id,
            status="RECORDED",
            payload=payload,
            destination=destination,
            delivered_at=utc_now(),
        )
        return AlertDelivery(match.rule.alert_rule_id, "RECORDED", destination, notification_id)
    if destination != "WEBHOOK":
        notification_id = store.add_notification(
            alert_rule_id=match.rule.alert_rule_id,
            comparison_id=comparison_id,
            milestone_id=milestone_id,
            status="FAILED",
            payload=payload,
            destination=destination,
            delivery_error="unsupported alert destination",
        )
        return AlertDelivery(match.rule.alert_rule_id, "FAILED", destination, notification_id, "unsupported alert destination")
    env_name = match.rule.destination_env
    if not env_name:
        error = "WEBHOOK alert requires destination_env"
        notification_id = store.add_notification(
            alert_rule_id=match.rule.alert_rule_id,
            comparison_id=comparison_id,
            milestone_id=milestone_id,
            status="FAILED",
            payload=payload,
            destination=destination,
            delivery_error=error,
        )
        return AlertDelivery(match.rule.alert_rule_id, "FAILED", destination, notification_id, error)
    url = os.environ.get(env_name, "").strip()
    try:
        if not url:
            raise ValueError(f"environment variable {env_name} is empty")
        _validate_webhook(url)
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": "RASAi/PlatformAlert"},
        )
        opener = build_opener(_NoRedirect())
        with opener.open(request, timeout=max(1, timeout_seconds)) as response:
            code = int(getattr(response, "status", 200))
            if not 200 <= code < 300:
                raise RuntimeError(f"webhook returned HTTP {code}")
        notification_id = store.add_notification(
            alert_rule_id=match.rule.alert_rule_id,
            comparison_id=comparison_id,
            milestone_id=milestone_id,
            status="DELIVERED",
            payload=payload,
            destination=destination,
            delivered_at=utc_now(),
        )
        return AlertDelivery(match.rule.alert_rule_id, "DELIVERED", destination, notification_id)
    except (OSError, ValueError, RuntimeError) as exc:
        error = str(exc)
        notification_id = store.add_notification(
            alert_rule_id=match.rule.alert_rule_id,
            comparison_id=comparison_id,
            milestone_id=milestone_id,
            status="FAILED",
            payload=payload,
            destination=destination,
            delivery_error=error,
        )
        return AlertDelivery(match.rule.alert_rule_id, "FAILED", destination, notification_id, error)


def evaluate_and_deliver(
    store: PlatformStore,
    result: ComparisonResult,
    *,
    property_id: str,
    comparison_id: str | None = None,
    milestone_id: str | None = None,
) -> tuple[AlertDelivery, ...]:
    rules = store.list_alert_rules(property_id=property_id, enabled_only=True)
    matches = match_alert_rules(result, rules)
    return tuple(
        deliver_alert_match(
            store,
            match,
            result,
            comparison_id=comparison_id,
            milestone_id=milestone_id,
        )
        for match in matches
    )
