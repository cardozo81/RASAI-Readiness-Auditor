"""Machine-readable CI/CD outputs for RASAi release gates."""
from __future__ import annotations

from dataclasses import asdict
from html import escape
import json
from pathlib import Path
from typing import Any

from searchgeo.monitoring.models import ComparisonResult, GateResult


def _write(path: str | Path, content: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return target


def write_gate_json(path: str | Path, result: ComparisonResult, gate: GateResult) -> Path:
    payload = {
        "schema": "RASAI-RELEASE-GATE-001",
        "passed": gate.passed,
        "reason": gate.reason,
        "baseline_audit_id": result.baseline.audit_id,
        "current_audit_id": result.current.audit_id,
        "comparable": result.comparable,
        "compatibility_notes": list(result.compatibility_notes),
        "counts": result.counts,
        "material_counts": result.material_counts,
        "policy": asdict(gate.policy),
        "blocking_events": [asdict(event) for event in gate.blocking_events],
        "warnings": [asdict(event) for event in gate.warnings],
    }
    return _write(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def write_gate_junit(path: str | Path, result: ComparisonResult, gate: GateResult) -> Path:
    failures = len(gate.blocking_events)
    cases: list[str] = []
    if not gate.blocking_events:
        cases.append(
            f"<testcase classname='RASAi.ReleaseGate' name='{escape(result.baseline.audit_id)} to {escape(result.current.audit_id)}'/>"
        )
    else:
        for event in gate.blocking_events:
            name = escape(event.rule_id or event.label)
            detail = escape(
                f"{event.status} {event.severity} {event.device or '-'} {event.url or '-'}: {event.before!r} -> {event.after!r}; {event.reason or ''}"
            )
            cases.append(
                f"<testcase classname='RASAi.ReleaseGate' name='{name}'><failure message='{escape(gate.reason)}'>{detail}</failure></testcase>"
            )
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        f"<testsuite name='RASAi Release Gate' tests='{max(1, len(cases))}' failures='{failures}'>"
        + "".join(cases)
        + "</testsuite>"
    )
    return _write(path, xml)


def write_gate_sarif(path: str | Path, result: ComparisonResult, gate: GateResult) -> Path:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for event in gate.blocking_events:
        rule_id = event.rule_id or f"RASAI-{event.domain}-{event.label}".replace(" ", "-")
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "name": event.label,
                "shortDescription": {"text": event.reason or event.label},
                "defaultConfiguration": {"level": _sarif_level(event.severity)},
            },
        )
        item: dict[str, Any] = {
            "ruleId": rule_id,
            "level": _sarif_level(event.severity),
            "message": {
                "text": f"{event.status}: {event.before!r} -> {event.after!r}. {event.reason or ''}".strip()
            },
            "properties": {
                "baselineAuditId": result.baseline.audit_id,
                "currentAuditId": result.current.audit_id,
                "device": event.device,
                "domain": event.domain,
            },
        }
        if event.url:
            item["locations"] = [
                {"physicalLocation": {"artifactLocation": {"uri": event.url}}}
            ]
        results.append(item)
    payload = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "RASAi Release Gate",
                        "informationUri": "https://github.com/cardozo81/SearchGEO-Readiness-Auditor",
                        "rules": list(rules.values()),
                    }
                },
                "results": results,
                "properties": {
                    "passed": gate.passed,
                    "reason": gate.reason,
                    "comparable": result.comparable,
                },
            }
        ],
    }
    return _write(path, json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _sarif_level(severity: str) -> str:
    value = severity.upper()
    if value in {"CRITICAL", "HIGH"}:
        return "error"
    if value == "MEDIUM":
        return "warning"
    return "note"
