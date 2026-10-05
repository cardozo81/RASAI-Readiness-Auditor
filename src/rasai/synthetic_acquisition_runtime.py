"""Canonical runtime integration for neutral synthetic physical acquisition.

The acquisition engine owns physical facts. CAT-06 and CAT-07 remain independent
evaluators. Compatible physical occurrences may be reused in auto mode; isolated
mode remains available for comparison and troubleshooting.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import Any, Callable

from rasai import synthetic_acquisition_engine as acquisition_engine
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace

ACQUISITION_MODE_ENV = "RASAI_APDEX_ACQUISITION_MODE"
DEFAULT_ACQUISITION_MODE = "auto"
_ALLOWED_MODES = frozenset({"auto", "isolated"})


_INSTALLED = False


def acquisition_mode(environment: dict[str, str] | os._Environ[str] | None = None) -> str:
    env = environment if environment is not None else os.environ
    value = (env.get(ACQUISITION_MODE_ENV) or DEFAULT_ACQUISITION_MODE).strip().casefold()
    return value if value in _ALLOWED_MODES else "isolated"


def prepare_acquisition_run(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    mode: str,
    reason: str | None = None,
) -> None:
    """Compatibility adapter; neutral engine owns the acquisition ledger."""
    acquisition_engine.prepare_acquisition_run(
        audit_id=audit_id,
        workspace=workspace,
        mode=mode,
        reason=reason,
    )


def publish_experience_acquisition(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile: Any,
    session_mode: str,
    measurement: Any,
    load_duration_ms: float | None,
    planning_ordinal: int | None = None,
) -> acquisition_engine.SyntheticAcquisitionEnvelope | None:
    """Publish an Experience FULL envelope through the neutral acquisition owner."""
    if acquisition_mode() != "auto" or str(session_mode).casefold() != "cold":
        return None
    if not bool(getattr(measurement, "profile_applied", False)):
        return None
    status = str(getattr(measurement, "status", ""))
    if status not in {"SUCCESS", "APPLICATION_ERROR"}:
        return None
    profile_id = str(getattr(profile, "profile_id", "") or "")
    if not profile_id:
        return None
    return acquisition_engine.record_acquisition(
        audit_id=audit_id,
        workspace=workspace,
        url=str(url),
        device=str(device).upper(),
        profile_id=profile_id,
        envelope_kind=acquisition_engine.FULL_EXPERIENCE,
        session_mode=session_mode,
        load_duration_ms=load_duration_ms,
        status=status,
        http_status=getattr(measurement, "http_status", None),
        final_url=getattr(measurement, "final_url", None),
        cpu_method=getattr(measurement, "cpu_method", None),
        network_method=getattr(measurement, "network_method", None),
        full_observables=acquisition_engine.full_observables_from_measurement(measurement),
        source="SYNTHETIC_USER_EXPERIENCE_APDEX",
        reusable_for_load=True,
        planning_ordinal=planning_ordinal,
    )


def consume_navigation_acquisition(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile_id: str,
    timeout_seconds: float,
) -> acquisition_engine.SyntheticAcquisitionEnvelope | None:
    """Claim only the persisted load boundary; CAT-06 still classifies independently."""
    if acquisition_mode() != "auto":
        return None
    item = acquisition_engine.claim_load_boundary(
        audit_id=audit_id,
        workspace=workspace,
        url=url,
        device=device,
        profile_id=profile_id,
        timeout_seconds=timeout_seconds,
    )
    if item is not None:
        return item
    return acquisition_engine.claim_persisted_load_boundary(
        audit_id=audit_id,
        workspace=workspace,
        url=url,
        device=device,
        profile_id=profile_id,
        timeout_seconds=timeout_seconds,
    )


_TimedPageProxy = acquisition_engine.TimedPageProxy
_TimedContextProxy = acquisition_engine.TimedContextProxy


def _canonical_ux_gateway_class(ux: Any) -> type:
    original = ux.PlaywrightSyntheticUxGateway

    class CanonicalCaptureSyntheticUxGateway(original):
        def __init__(self, *, audit_id: str, workspace: AuditWorkspace, session_mode: str = "cold", executable_path: str | None = None) -> None:
            super().__init__(session_mode=session_mode, executable_path=executable_path)
            self._rasai_audit_id = audit_id
            self._rasai_workspace = workspace
            self._rasai_capture_local = threading.local()

        def set_planning_ordinal(self, value: int) -> None:
            self._rasai_capture_local.planning_ordinal = int(value)

        def _context(self, *, device: str, profile: Any) -> tuple[Any, bool]:
            context, close_context = super()._context(device=device, profile=profile)
            capture = getattr(self._rasai_capture_local, "capture", None)
            if self.session_mode == "cold" and isinstance(capture, dict):
                return _TimedContextProxy(context, capture), close_context
            return context, close_context

        def measure(self, *, url: str, device: str, profile: Any, timeout_seconds: float, settle_seconds: float) -> Any:
            capture: dict[str, float] = {}
            self._rasai_capture_local.capture = capture
            try:
                result = super().measure(
                    url=url,
                    device=device,
                    profile=profile,
                    timeout_seconds=timeout_seconds,
                    settle_seconds=settle_seconds,
                )
                publish_experience_acquisition(
                    audit_id=self._rasai_audit_id,
                    workspace=self._rasai_workspace,
                    url=url,
                    device=device,
                    profile=profile,
                    session_mode=self.session_mode,
                    measurement=result,
                    load_duration_ms=capture.get("load_duration_ms"),
                    planning_ordinal=getattr(
                        self._rasai_capture_local,
                        "planning_ordinal",
                        None,
                    ),
                )
                return result
            finally:
                self._rasai_capture_local.capture = None

    CanonicalCaptureSyntheticUxGateway.__name__ = "CanonicalCaptureSyntheticUxGateway"
    return CanonicalCaptureSyntheticUxGateway


class CanonicalNavigationGateway:
    def __init__(
        self,
        *,
        audit_id: str,
        workspace: AuditWorkspace,
        delegate: Any,
        navigation_target_samples: int,
    ) -> None:
        self.audit_id = audit_id
        self.workspace = workspace
        self.delegate = delegate
        self.navigation_target_samples = max(int(navigation_target_samples), 0)
        self._prepared_keys: set[tuple[str, str, str]] = set()

    def environment(self) -> dict[str, Any]:
        value = dict(self.delegate.environment())
        value["apdex_acquisition_mode"] = acquisition_mode()
        value["canonical_acquisition_enabled"] = acquisition_mode() == "auto"
        return value

    def close(self) -> None:
        self.delegate.close()

    def measure(self, *, url: str, profile: Any, timeout_seconds: float) -> Any:
        from rasai.m23_apdex_profiles import NavigationMeasurement

        device = str(getattr(getattr(profile, "device", None), "value", getattr(profile, "device", ""))).upper()
        key = (url, device, str(getattr(profile, "profile_id", "")))
        if key not in self._prepared_keys:
            acquisition_engine.prepare_navigation_claims(
                audit_id=self.audit_id,
                url=url,
                device=device,
                profile_id=key[2],
                navigation_samples=self.navigation_target_samples,
            )
            self._prepared_keys.add(key)
        item = consume_navigation_acquisition(
            audit_id=self.audit_id,
            workspace=self.workspace,
            url=url,
            device=device,
            profile_id=str(getattr(profile, "profile_id", "")),
            timeout_seconds=timeout_seconds,
        )
        if item is None:
            measured = self.delegate.measure(
                url=url,
                profile=profile,
                timeout_seconds=timeout_seconds,
            )
            duration = getattr(measured, "duration_ms", None)
            if bool(getattr(measured, "profile_applied", False)) and duration is not None:
                acquisition_engine.record_acquisition(
                    audit_id=self.audit_id,
                    workspace=self.workspace,
                    url=url,
                    device=device,
                    profile_id=str(getattr(profile, "profile_id", "")),
                    envelope_kind=acquisition_engine.LOAD_ONLY,
                    session_mode="cold",
                    load_duration_ms=float(duration),
                    status=str(getattr(measured, "status", "")),
                    http_status=getattr(measured, "http_status", None),
                    final_url=getattr(measured, "final_url", None),
                    cpu_method=getattr(measured, "cpu_method", None),
                    network_method=getattr(measured, "network_method", None),
                    source="SYNTHETIC_NAVIGATION_APDEX",
                    reusable_for_load=False,
                    consumed_by_navigation=True,
                )
            return measured
        return NavigationMeasurement(
            status=item.status,
            duration_ms=int(round(item.load_duration_ms)),
            http_status=item.http_status,
            final_url=item.final_url,
            error_code=None,
            error_message=None,
            profile_applied=True,
            cpu_method=item.cpu_method,
            network_method=item.network_method,
            browser_diagnostics=(
                {
                    "type": "CANONICAL_ACQUISITION_REUSE",
                    "message": item.acquisition_id,
                    "url": item.url,
                },
            ),
        )


def _table_value(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
    try:
        row = connection.execute(sql, params).fetchone()
    except sqlite3.OperationalError:
        return 0
    if row is None or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def acquisition_stats(*, audit_id: str, workspace: AuditWorkspace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "mode": acquisition_mode(),
        "reason": None,
        "eligible": 0,
        "reused": 0,
        "timeout_incompatible": 0,
        "m25_attempted": 0,
        "m23_attempted": 0,
        "m23_physical": 0,
        "physical_isolated": 0,
        "physical_canonical": 0,
        "avoided": 0,
    }
    try:
        connection = sqlite3.connect(workspace.database)
        connection.row_factory = sqlite3.Row
        try:
            try:
                row = connection.execute(
                    "SELECT * FROM synthetic_apdex_acquisition_runs WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
            if row is not None:
                result.update(
                    mode=str(row["mode"]),
                    reason=row["reason"],
                    eligible=int(row["eligible_acquisitions"] or 0),
                    reused=int(row["reused_by_navigation"] or 0),
                    timeout_incompatible=int(row["timeout_incompatible"] or 0),
                )
            result["m25_attempted"] = _table_value(
                connection,
                "SELECT attempted_samples FROM synthetic_ux_apdex_runs WHERE audit_id=?",
                (audit_id,),
            )
            result["m23_attempted"] = _table_value(
                connection,
                "SELECT attempted_samples FROM synthetic_apdex_runs WHERE audit_id=?",
                (audit_id,),
            )
        finally:
            connection.close()
    except sqlite3.Error:
        pass
    result["avoided"] = min(int(result["reused"]), int(result["m23_attempted"]))
    result["m23_physical"] = max(int(result["m23_attempted"]) - int(result["avoided"]), 0)
    result["physical_isolated"] = int(result["m25_attempted"]) + int(result["m23_attempted"])
    result["physical_canonical"] = int(result["m25_attempted"]) + int(result["m23_physical"])
    return result


def install() -> None:
    """Install canonical acquisition adapters on the public M23/M25 runtime paths."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import cli_extensions
    from rasai import m23_apdex as m23
    from rasai import m23_apdex_profiles as profiles
    from rasai import m25_apdex_experience as ux
    from rasai import m25_runtime

    canonical_ux_gateway = _canonical_ux_gateway_class(ux)

    original_m25_execute = m25_runtime.execute_m25_experience
    if not getattr(original_m25_execute, "_rasai_canonical_acquisition", False):
        def execute_m25_with_canonical_acquisition(*, audit_id: str, workspace: AuditWorkspace, config: Any, gateway: Any = None, gateway_factory: Callable[[], Any] | None = None):
            mode = acquisition_mode()
            reason = None
            if mode != "auto":
                reason = "ISOLATED_BY_CONFIGURATION"
            elif str(getattr(config, "session_mode", "cold")).casefold() != "cold":
                reason = "EXPERIENCE_SESSION_WARM_REQUIRES_ISOLATED_ACQUISITION"
            elif gateway is not None or gateway_factory is not None:
                reason = "INJECTED_GATEWAY_REQUIRES_ISOLATED_ACQUISITION"
            prepare_acquisition_run(audit_id=audit_id, workspace=workspace, mode=mode, reason=reason)

            if reason is None:
                factory = lambda: canonical_ux_gateway(
                    audit_id=audit_id,
                    workspace=workspace,
                    session_mode=str(getattr(config, "session_mode", "cold")),
                )
                result = original_m25_execute(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=config,
                    gateway_factory=factory,
                )
            else:
                result = original_m25_execute(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=config,
                    gateway=gateway,
                    gateway_factory=gateway_factory,
                )
            stats = acquisition_stats(audit_id=audit_id, workspace=workspace)
            try_append_operational_event(
                workspace,
                "SYNTHETIC_ACQUISITION_SOURCE_COMPLETED",
                audit_id=audit_id,
                mode=stats["mode"],
                eligible_acquisitions=stats["eligible"],
                reason=stats.get("reason"),
                scoring_impact="NONE",
            )
            return result

        execute_m25_with_canonical_acquisition._rasai_canonical_acquisition = True
        execute_m25_with_canonical_acquisition._rasai_original = original_m25_execute
        m25_runtime.execute_m25_experience = execute_m25_with_canonical_acquisition

    original_m23_execute = cli_extensions.execute_m23_apdex
    if not getattr(original_m23_execute, "_rasai_canonical_acquisition", False):
        def execute_m23_with_canonical_acquisition(*, audit_id: str, workspace: AuditWorkspace, config: Any = None, gateway: Any = None, gateway_factory: Callable[[], Any] | None = None):
            if gateway is not None or gateway_factory is not None or acquisition_mode() != "auto":
                return original_m23_execute(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=config,
                    gateway=gateway,
                    gateway_factory=gateway_factory,
                )
            target_samples = int(
                getattr(config, "target_valid_samples", 2**31 - 1)
                if config is not None
                else 2**31 - 1
            )
            factory = lambda: CanonicalNavigationGateway(
                audit_id=audit_id,
                workspace=workspace,
                delegate=profiles.PlaywrightSyntheticNavigationGateway(),
                navigation_target_samples=target_samples,
            )
            result = original_m23_execute(
                audit_id=audit_id,
                workspace=workspace,
                config=config,
                gateway_factory=factory,
            )
            stats = acquisition_stats(audit_id=audit_id, workspace=workspace)
            try_append_operational_event(
                workspace,
                "SYNTHETIC_ACQUISITION_COMPLETED",
                audit_id=audit_id,
                mode=stats["mode"],
                experience_eligible=stats["eligible"],
                navigation_reused=stats["reused"],
                navigation_physical=stats["m23_physical"],
                physical_requests_avoided=stats["avoided"],
                scoring_impact="NONE",
            )
            return result

        execute_m23_with_canonical_acquisition._rasai_canonical_acquisition = True
        execute_m23_with_canonical_acquisition._rasai_original = original_m23_execute
        cli_extensions.execute_m23_apdex = execute_m23_with_canonical_acquisition
        if m23.execute_m23_apdex is original_m23_execute:
            m23.execute_m23_apdex = execute_m23_with_canonical_acquisition

    _INSTALLED = True
