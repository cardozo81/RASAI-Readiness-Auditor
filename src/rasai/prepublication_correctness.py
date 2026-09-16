"""Pre-publication correctness contracts for execution and fulfillment.

RASAi has not been published yet, so these rules intentionally define the current
canonical behaviour rather than preserving obsolete result shapes.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request

_INSTALLED = False


def _install_web_performance_contract() -> None:
    from rasai import m21_web_performance as m21

    def assess_cwv(field: Mapping[str, Any] | None) -> dict[str, str | None]:
        if not field:
            return {
                "lcp_assessment": None,
                "inp_assessment": None,
                "cls_assessment": None,
                "cwv_assessment": "UNAVAILABLE",
            }

        def assess(value: Any, good_max: float, needs_improvement_max: float) -> str | None:
            if value is None:
                return None
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if numeric <= good_max:
                return "GOOD"
            if numeric <= needs_improvement_max:
                return "NEEDS_IMPROVEMENT"
            return "POOR"

        lcp = assess(field.get("lcp_p75_ms"), 2500.0, 4000.0)
        inp = assess(field.get("inp_p75_ms"), 200.0, 500.0)
        cls = assess(field.get("cls_p75"), 0.1, 0.25)
        components = (lcp, inp, cls)
        if any(value is None for value in components):
            overall = "INCOMPLETE"
        else:
            overall = "PASS" if all(value == "GOOD" for value in components) else "FAIL"
        return {
            "lcp_assessment": lcp,
            "inp_assessment": inp,
            "cls_assessment": cls,
            "cwv_assessment": overall,
        }

    assess_cwv._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    m21._assess_cwv = assess_cwv

    current_run = m21.PageSpeedInsightsClient.run
    if getattr(current_run, "_rasai_pt_br_locale", False):
        return

    def run_pt_br(
        self: Any,
        *,
        url: str,
        strategy: str,
        categories: tuple[str, ...],
        timeout_seconds: float,
    ) -> Any:
        query: list[tuple[str, str]] = [("url", url), ("strategy", strategy), ("locale", "pt-BR")]
        query.extend(("category", category) for category in categories)
        if getattr(self, "_api_key", None):
            query.append(("key", str(self._api_key)))
        endpoint = f"{m21.PAGESPEED_ENDPOINT}?{urlencode(query)}"
        request = Request(endpoint, headers={"Accept": "application/json"})
        last_error: Exception | None = None
        for attempt in range(1, m21._PAGESPEED_MAX_ATTEMPTS + 1):
            try:
                return m21._request_json(
                    service="PAGESPEED_INSIGHTS",
                    request=request,
                    timeout_seconds=timeout_seconds,
                )
            except m21.ExternalServiceError as exc:
                last_error = exc
                transient = exc.http_status in m21._TRANSIENT_HTTP_STATUSES or exc.error_code in {"TIMEOUTERROR", "URLERROR"}
                if attempt >= m21._PAGESPEED_MAX_ATTEMPTS or not transient:
                    raise
                time.sleep(0.75)
        assert last_error is not None
        raise last_error

    run_pt_br._rasai_pt_br_locale = True  # type: ignore[attr-defined]
    run_pt_br._rasai_original = current_run  # type: ignore[attr-defined]
    m21.PageSpeedInsightsClient.run = run_pt_br


def _install_experience_apdex_contract() -> None:
    from rasai import m25_apdex_experience as m25

    def qualifying_error(item: Any, scope: str) -> bool:
        """Return only errors that belong to the configured responsibility scope.

        Browser console/page errors do not carry a reliable first-party origin in the
        current measurement contract. They therefore remain diagnostic in
        ``first-party`` mode and may force frustration only in ``all`` mode.
        """
        if str(getattr(item, "status", "")) == "APPLICATION_ERROR":
            return True
        normalized = str(scope or "").strip().casefold()
        if normalized == "navigation":
            return False
        if normalized == "first-party":
            return (
                int(getattr(item, "first_party_request_failed_count", 0) or 0) > 0
                or int(getattr(item, "first_party_http_error_count", 0) or 0) > 0
            )
        return (
            int(getattr(item, "javascript_error_count", 0) or 0) > 0
            or int(getattr(item, "console_error_count", 0) or 0) > 0
            or int(getattr(item, "request_failed_count", 0) or 0) > 0
            or int(getattr(item, "http_error_count", 0) or 0) > 0
        )

    qualifying_error._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    m25._qualifying_error = qualifying_error


def _improvement_run(workspace: Any, audit_id: str) -> dict[str, Any] | None:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_intelligence_runs'"
        ).fetchone()
        if exists is None:
            return None
        row = connection.execute(
            "SELECT * FROM improvement_intelligence_runs WHERE audit_id=? ORDER BY rowid DESC LIMIT 1",
            (audit_id,),
        ).fetchone()
        return dict(row) if row is not None else None
    finally:
        connection.close()


def _install_improvement_fulfillment_contract() -> None:
    """Keep CAT-08 mandatory fulfillment visible even while the console isolates env vars."""
    from rasai import fulfillment_execution_contract as contract
    from rasai.audit_fulfillment import (
        FAILED_RETRYABLE,
        REPLAY_SAFE,
        SUCCESS,
        register_work_item,
        set_work_item_status,
    )
    from rasai.improvement_intelligence import ENABLED_ENV

    current = contract._reconcile_requested_improvement
    if getattr(current, "_rasai_prepublication_correctness", False):
        return

    def reconcile_improvement(workspace: Any, audit_id: str) -> None:
        if contract._truthy(os.environ.get(ENABLED_ENV)):
            current(workspace, audit_id)
            return

        run = _improvement_run(workspace, audit_id)
        if run is None:
            return

        raw_domains = run.get("domains_json")
        try:
            domains = json.loads(str(raw_domains)) if raw_domains else []
        except (TypeError, ValueError, json.JSONDecodeError):
            domains = []
        configuration = {
            "requested": True,
            "provider": str(run.get("provider") or ""),
            "model": str(run.get("model") or ""),
            "reasoning": str(run.get("reasoning") or ""),
            "domains": domains if isinstance(domains, list) else [],
            "max_recommendations": run.get("max_recommendations"),
            "language": run.get("analysis_language"),
        }
        register_work_item(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            required=True,
            temporal_mode=REPLAY_SAFE,
            retryable=True,
            configuration=configuration,
        )
        run_status = str(run.get("status") or "").strip().upper()
        if run_status == "COMPLETE":
            set_work_item_status(
                workspace,
                audit_id=audit_id,
                component="IMPROVEMENT_INTELLIGENCE",
                status=SUCCESS,
                result_ref="improvement-intelligence:effective",
                retryable=False,
            )
            return

        reason = str(run.get("reason") or "Improvement Intelligence não concluiu sem limitações")
        set_work_item_status(
            workspace,
            audit_id=audit_id,
            component="IMPROVEMENT_INTELLIGENCE",
            status=FAILED_RETRYABLE,
            error_class="AI_ANALYSIS",
            error_code=run_status or "IMPROVEMENT_INCOMPLETE",
            error_message=contract._safe_detail(reason),
            retryable=True,
        )

    reconcile_improvement._rasai_prepublication_correctness = True  # type: ignore[attr-defined]
    reconcile_improvement._rasai_original = current  # type: ignore[attr-defined]
    contract._reconcile_requested_improvement = reconcile_improvement


def install() -> None:
    """Install canonical pre-publication execution contracts exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return
    _install_web_performance_contract()
    _install_experience_apdex_contract()
    _install_improvement_fulfillment_contract()
    _INSTALLED = True


__all__ = ["install"]
