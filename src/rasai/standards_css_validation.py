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


def _local_name(tag: Any) -> str:
    return str(tag or "").rsplit("}", 1)[-1]


def _node_text(node: ET.Element, local: str) -> str | None:
    for child in node.iter():
        if _local_name(child.tag) != local or child.text is None:
            continue
        value = child.text.strip()
        if value:
            return value
    return None


def _css_diagnostics(root: ET.Element, kind: str, *, limit: int = 200) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for node in root.iter():
        if _local_name(node.tag) != kind:
            continue
        # Ignore aggregate containers such as <errors> / <warnings>.
        if not any(_local_name(child.tag) in {"line", "message", "context", "errortype", "warningtype"} for child in list(node)):
            continue
        line_raw = _node_text(node, "line")
        try:
            line = int(line_raw) if line_raw is not None else None
        except ValueError:
            line = None
        diagnostics.append({
            "line": line,
            "message": _node_text(node, "message"),
            "context": _node_text(node, "context"),
            "type": _node_text(node, "errortype") or _node_text(node, "warningtype"),
            "subtype": _node_text(node, "errorsubtype"),
            "skipped_string": _node_text(node, "skippedstring"),
            "uri": _node_text(node, "uri"),
        })
        if len(diagnostics) >= max(1, int(limit)):
            break
    return diagnostics


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

    error_details = _css_diagnostics(root, "error")
    warning_details = _css_diagnostics(root, "warning")
    return {
        "valid": validity_text == "true",
        "errors": count("errorcount"),
        "warnings": count("warningcount"),
        "css_level": text("csslevel"),
        "checked_by": text("checkedby"),
        "validated_at": text("date"),
        "error_details": error_details,
        "warning_details": warning_details,
        "approval_criterion": "valid=true and 0 CSS errors from the W3C CSS Validation Service",
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


def _persist_inactive_service_run(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    state_info: Mapping[str, Any],
) -> None:
    connection = sqlite3.connect(workspace.database)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='standards_service_runs'"
        ).fetchone()
        if exists is None:
            return
        with connection:
            _service_run(
                connection,
                audit_id=audit_id,
                service_id="w3c-css-validator",
                state_info=state_info,
                state=str(state_info.get("state") or "DISABLED"),
            )
    finally:
        connection.close()


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
        _persist_inactive_service_run(audit_id=audit_id, workspace=workspace, state_info=state_info)
        result["collection_state"] = str(state_info["state"])
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
    """Collect CSS conformance without rendering the retired conventional report."""
    from rasai import report_completion

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
            collect_css_validation(audit_id=audit_id, workspace=workspace)
        except Exception as exc:
            errors.append(f"w3c-css:{type(exc).__name__}:{str(exc)[:400]}")
        return report_completion.AuditReportCompletion(
            expected_pages=base.expected_pages,
            generated_pages=base.generated_pages,
            missing_pages=base.missing_pages,
            renderer_errors=tuple(errors),
        )

    report_completion.finalize_audit_report_site = finalize_with_css
    report_completion._rasai_css_validation_runtime = True

