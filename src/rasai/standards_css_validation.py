"""Bounded W3C CSS Validation Service integration.

The public W3C service documents a SOAP 1.2 programmatic interface and asks automated
clients validating a set of documents to sleep at least one second between requests.
This collector follows that constraint, is fail-open, and never fabricates a W3C score.
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from rasai.persistence import AuditWorkspace
from rasai.standards_metrics import _record, _service_run
from rasai.standards_service_registry import (
    DEFAULT_STANDARDS_MAX_URLS,
    DEFAULT_STANDARDS_TIMEOUT_SECONDS,
    STANDARDS_MAX_URLS_ENV,
    STANDARDS_TIMEOUT_ENV,
    service,
    service_state,
)

CSS_VALIDATOR_ENDPOINT = "https://jigsaw.w3.org/css-validator/validator"
CSS_PROFILE = "css3"
PUBLIC_MIN_INTERVAL_SECONDS = 1.0
_CSS_NS = "http://www.w3.org/2005/07/css-validator"


class CssValidationError(RuntimeError):
    pass


def _int_env(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = str(environment.get(name) or "").strip()
    value = default if not raw else int(raw)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _float_env(environment: Mapping[str, str], name: str, default: float) -> float:
    raw = str(environment.get(name) or "").strip()
    value = default if not raw else float(raw)
    if value <= 0 or value >= 3600:
        raise ValueError(f"{name} must be > 0 and < 3600")
    return value


def parse_css_validation_soap(payload: bytes) -> dict[str, Any]:
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise CssValidationError("W3C CSS validator returned invalid SOAP XML") from exc

    def text(local: str) -> str | None:
        node = root.find(f".//{{{_CSS_NS}}}{local}")
        if node is None or node.text is None:
            return None
        value = node.text.strip()
        return value or None

    validity_text = (text("validity") or "").casefold()
    if validity_text not in {"true", "false"}:
        raise CssValidationError("W3C CSS validator SOAP response has no determinate validity")

    def count(local: str) -> int:
        raw = text(local)
        if raw is None:
            return 0
        try:
            return max(0, int(raw))
        except ValueError:
            return 0

    return {
        "valid": validity_text == "true",
        "errors": count("errorcount"),
        "warnings": count("warningcount"),
        "css_level": text("csslevel"),
        "checked_by": text("checkedby"),
        "validated_at": text("date"),
    }


def _request(url: str, timeout: float, opener: Callable[..., Any]) -> bytes:
    endpoint = CSS_VALIDATOR_ENDPOINT + "?" + urlencode(
        {
            "uri": url,
            "output": "soap12",
            "profile": CSS_PROFILE,
            "warning": "0",
            "lang": "en",
        }
    )
    request = Request(
        endpoint,
        headers={
            "Accept": "application/soap+xml, application/xml;q=0.9",
            "User-Agent": "RASAi-Readiness-Auditor/0.1",
        },
    )
    try:
        response = opener(request, timeout=timeout)
        return response.read()
    except HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            detail = ""
        raise CssValidationError(f"HTTP {exc.code}: {detail}".strip()) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CssValidationError(f"{type(exc).__name__}: {exc}") from exc


def collect_css_validation(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    env: Mapping[str, str] | None = None,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], Any] = time.sleep,
) -> dict[str, Any]:
    environment = env if env is not None else os.environ
    item = service("w3c-css-validator")
    state_info = service_state(item, environment)
    result: dict[str, Any] = {
        "state_info": state_info,
        "attempted": 0,
        "succeeded": 0,
        "errors": [],
    }
    if not bool(state_info["effective_enabled"]):
        return result

    max_urls = _int_env(environment, STANDARDS_MAX_URLS_ENV, DEFAULT_STANDARDS_MAX_URLS)
    timeout = _float_env(environment, STANDARDS_TIMEOUT_ENV, DEFAULT_STANDARDS_TIMEOUT_SECONDS)
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT normalized_url FROM pages WHERE audit_id=? ORDER BY rowid",
            (audit_id,),
        ).fetchall()
        urls = [str(row[0]) for row in rows]
        if max_urls:
            urls = urls[:max_urls]

        with connection:
            for index, url in enumerate(urls):
                if index:
                    sleeper(PUBLIC_MIN_INTERVAL_SECONDS)
                result["attempted"] += 1
                try:
                    parsed = parse_css_validation_soap(_request(url, timeout, opener))
                    result["succeeded"] += 1
                    _record(
                        connection,
                        audit_id=audit_id,
                        metric_id="w3c_css_conformance",
                        label="W3C CSS Conformance",
                        scope="URL",
                        target=url,
                        state="PASS" if parsed["valid"] else "FAIL",
                        value=float(parsed["errors"]),
                        unit="error_count",
                        source="W3C CSS Validation Service",
                        methodology=f"W3C CSS Validator SOAP 1.2; profile={CSS_PROFILE}; warning=0",
                        relation_degree=item.relation_degree,
                        details={
                            **parsed,
                            "profile_requested": CSS_PROFILE,
                            "public_min_interval_seconds": PUBLIC_MIN_INTERVAL_SECONDS,
                            "endpoint": CSS_VALIDATOR_ENDPOINT,
                        },
                    )
                except CssValidationError as exc:
                    message = f"{type(exc).__name__}: {str(exc)[:400]}"
                    result["errors"].append(message)
                    _record(
                        connection,
                        audit_id=audit_id,
                        metric_id="w3c_css_conformance",
                        label="W3C CSS Conformance",
                        scope="URL",
                        target=url,
                        state="ERROR",
                        source="W3C CSS Validation Service",
                        methodology=f"W3C CSS Validator SOAP 1.2; profile={CSS_PROFILE}; warning=0",
                        relation_degree=item.relation_degree,
                        details={"error": message},
                    )

            attempted = int(result["attempted"])
            succeeded = int(result["succeeded"])
            if attempted == 0:
                run_state = "NO_DATA"
            elif succeeded == attempted:
                run_state = "SUCCESS"
            elif succeeded:
                run_state = "PARTIAL"
            else:
                run_state = "ERROR"
            _service_run(
                connection,
                audit_id=audit_id,
                service_id="w3c-css-validator",
                state_info=state_info,
                state=run_state,
                attempted=attempted,
                succeeded=succeeded,
                details={
                    "endpoint": CSS_VALIDATOR_ENDPOINT,
                    "profile": CSS_PROFILE,
                    "public_min_interval_seconds": PUBLIC_MIN_INTERVAL_SECONDS,
                    "errors": result["errors"][:20],
                },
            )
            result["collection_state"] = run_state
    finally:
        connection.close()
    return result


def install() -> None:
    """Collect CSS conformance after base standards tables exist, then refresh reports."""
    from rasai import report_completion, report_navigation
    from rasai.report_manifest import write_report_manifest
    from rasai.report_scale_ux import enhance_report_directory
    from rasai.standards_metrics import enrich_existing_reports, write_standards_report

    if getattr(report_completion, "_rasai_css_validation_runtime", False):
        return
    original = report_completion.finalize_audit_report_site

    def finalize_with_css(*, audit_id: str, workspace: Any, context_interpretations=(), routing_snapshot=None):
        base = original(
            audit_id=audit_id,
            workspace=workspace,
            context_interpretations=context_interpretations,
            routing_snapshot=routing_snapshot,
        )
        errors = list(base.renderer_errors)
        try:
            result = collect_css_validation(audit_id=audit_id, workspace=workspace)
            if bool(result.get("state_info", {}).get("effective_enabled")):
                write_standards_report(audit_id=audit_id, workspace=workspace)
                enrich_existing_reports(audit_id=audit_id, workspace=workspace)
                report_dir = workspace.root / "report"
                report_navigation.normalize_report_navigation(report_dir)
                enhance_report_directory(report_dir)
                write_report_manifest(report_dir)
        except Exception as exc:
            # CSS conformance is optional external evidence. Runtime/configuration bugs
            # are visible as repairable renderer diagnostics, provider failures are
            # already materialized as service/metric ERROR states by the collector.
            errors.append(f"w3c-css:{type(exc).__name__}:{str(exc)[:400]}")
        inspected = report_completion.inspect_audit_report_site(audit_id=audit_id, workspace=workspace)
        return report_completion.AuditReportCompletion(
            expected_pages=inspected.expected_pages,
            generated_pages=inspected.generated_pages,
            missing_pages=inspected.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_css
    report_completion._rasai_css_validation_runtime = True
