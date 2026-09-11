"""Shared physical acquisition for the two independent synthetic Apdex methods.

The contract is deliberately narrow:

* Synthetic User Experience Apdex (M25) remains the source of its own population,
  KPM, thresholds and error policy.
* Synthetic Navigation Apdex (M23) remains the source of its own sample targets,
  T/4T classification and validity rules.
* A physical browser navigation may be reused by M23 only when M25 produced a
  cold-context acquisition for the exact same URL, device and synthetic profile.
* Only the load-boundary duration captured around ``page.goto(..., wait_until='load')``
  is projected into M23. Post-load observation continues exclusively for M25.
* Timeout/navigation-error acquisitions are not reused because the two methods may
  have different timeout budgets.

This reduces traffic without deriving one score from the other. The persisted ledger
is traceability only and never participates in SCORE-GEO/SARI.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import math
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable

from rasai.domain import new_id
from rasai.operational_log import try_append_operational_event
from rasai.persistence import AuditWorkspace

ACQUISITION_MODE_ENV = "RASAI_APDEX_ACQUISITION_MODE"
DEFAULT_ACQUISITION_MODE = "auto"
_ALLOWED_MODES = frozenset({"auto", "isolated"})

_MANAGED_START = "<!-- RASAI_SHARED_APDEX_ACQUISITION_START -->"
_MANAGED_END = "<!-- RASAI_SHARED_APDEX_ACQUISITION_END -->"


@dataclass(frozen=True, slots=True)
class SharedNavigationAcquisition:
    acquisition_id: str
    audit_id: str
    url: str
    device: str
    profile_id: str
    load_duration_ms: float
    status: str
    http_status: int | None
    final_url: str | None
    cpu_method: str | None
    network_method: str | None
    created_at: str


_lock = threading.RLock()
_pool: dict[tuple[str, str, str, str], deque[SharedNavigationAcquisition]] = defaultdict(deque)
_INSTALLED = False


def acquisition_mode(environment: dict[str, str] | os._Environ[str] | None = None) -> str:
    env = environment if environment is not None else os.environ
    value = (env.get(ACQUISITION_MODE_ENV) or DEFAULT_ACQUISITION_MODE).strip().casefold()
    return value if value in _ALLOWED_MODES else "isolated"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(audit_id: str, url: str, device: str, profile_id: str) -> tuple[str, str, str, str]:
    return (str(audit_id), str(url), str(device).upper(), str(profile_id))


def _connect(workspace: AuditWorkspace) -> sqlite3.Connection:
    connection = sqlite3.connect(workspace.database)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS synthetic_apdex_acquisition_runs(
            audit_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            reason TEXT,
            eligible_acquisitions INTEGER NOT NULL DEFAULT 0,
            reused_by_navigation INTEGER NOT NULL DEFAULT 0,
            timeout_incompatible INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS synthetic_apdex_acquisitions(
            acquisition_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            url TEXT NOT NULL,
            device TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_status TEXT NOT NULL,
            load_duration_ms REAL NOT NULL,
            http_status INTEGER,
            final_url TEXT,
            cpu_method TEXT,
            network_method TEXT,
            consumed_by_navigation INTEGER NOT NULL DEFAULT 0,
            consumed_at TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_synthetic_apdex_acquisition_lookup "
        "ON synthetic_apdex_acquisitions(audit_id,url,device,profile_id,created_at)"
    )
    connection.commit()
    return connection


def prepare_acquisition_run(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    mode: str,
    reason: str | None = None,
) -> None:
    with _lock:
        for key in [item for item in _pool if item[0] == audit_id]:
            _pool.pop(key, None)
    try:
        connection = _connect(workspace)
        try:
            connection.execute("DELETE FROM synthetic_apdex_acquisitions WHERE audit_id=?", (audit_id,))
            connection.execute(
                """
                INSERT INTO synthetic_apdex_acquisition_runs(
                    audit_id,mode,reason,eligible_acquisitions,reused_by_navigation,
                    timeout_incompatible,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(audit_id) DO UPDATE SET
                    mode=excluded.mode,reason=excluded.reason,
                    eligible_acquisitions=0,reused_by_navigation=0,
                    timeout_incompatible=0,updated_at=excluded.updated_at
                """,
                (audit_id, mode, reason, 0, 0, 0, _utc_now()),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        # The sharing optimization must never make the audit fail. In-memory reuse
        # remains available even if the optional traceability table cannot be written.
        pass


def _update_run_counter(workspace: AuditWorkspace, audit_id: str, column: str, increment: int = 1) -> None:
    if column not in {"eligible_acquisitions", "reused_by_navigation", "timeout_incompatible"}:
        return
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                f"UPDATE synthetic_apdex_acquisition_runs SET {column}={column}+?,updated_at=? WHERE audit_id=?",
                (int(increment), _utc_now(), audit_id),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass


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
) -> SharedNavigationAcquisition | None:
    """Publish an M25 load boundary only when it is safe for M23 reuse."""
    if acquisition_mode() != "auto" or str(session_mode).casefold() != "cold":
        return None
    if not bool(getattr(measurement, "profile_applied", False)):
        return None
    status = str(getattr(measurement, "status", ""))
    if status not in {"SUCCESS", "APPLICATION_ERROR"}:
        return None
    try:
        duration = float(load_duration_ms) if load_duration_ms is not None else math.nan
    except (TypeError, ValueError):
        return None
    if not math.isfinite(duration) or duration < 0:
        return None
    profile_id = str(getattr(profile, "profile_id", "") or "")
    if not profile_id:
        return None
    item = SharedNavigationAcquisition(
        acquisition_id=new_id("SYN"),
        audit_id=audit_id,
        url=str(url),
        device=str(device).upper(),
        profile_id=profile_id,
        load_duration_ms=duration,
        status=status,
        http_status=_optional_int(getattr(measurement, "http_status", None)),
        final_url=_optional_text(getattr(measurement, "final_url", None)),
        cpu_method=_optional_text(getattr(measurement, "cpu_method", None)),
        network_method=_optional_text(getattr(measurement, "network_method", None)),
        created_at=_utc_now(),
    )
    with _lock:
        _pool[_key(audit_id, item.url, item.device, item.profile_id)].append(item)
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO synthetic_apdex_acquisitions(
                    acquisition_id,audit_id,url,device,profile_id,source,source_status,
                    load_duration_ms,http_status,final_url,cpu_method,network_method,
                    consumed_by_navigation,consumed_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.acquisition_id,item.audit_id,item.url,item.device,item.profile_id,
                    "SYNTHETIC_USER_EXPERIENCE_APDEX",item.status,item.load_duration_ms,
                    item.http_status,item.final_url,item.cpu_method,item.network_method,
                    0,None,item.created_at,
                ),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass
    _update_run_counter(workspace, audit_id, "eligible_acquisitions")
    return item


def consume_navigation_acquisition(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile_id: str,
    timeout_seconds: float,
) -> SharedNavigationAcquisition | None:
    if acquisition_mode() != "auto":
        return None
    key = _key(audit_id, url, device, profile_id)
    selected: SharedNavigationAcquisition | None = None
    timed_out: list[SharedNavigationAcquisition] = []
    with _lock:
        queue = _pool.get(key)
        while queue:
            candidate = queue.popleft()
            if candidate.load_duration_ms <= float(timeout_seconds) * 1000.0:
                selected = candidate
                break
            timed_out.append(candidate)
        if queue is not None and not queue:
            _pool.pop(key, None)
    if timed_out:
        _update_run_counter(workspace, audit_id, "timeout_incompatible", len(timed_out))
    if selected is None:
        return None
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                "UPDATE synthetic_apdex_acquisitions SET consumed_by_navigation=1,consumed_at=? WHERE acquisition_id=?",
                (_utc_now(), selected.acquisition_id),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass
    _update_run_counter(workspace, audit_id, "reused_by_navigation")
    return selected


class _TimedPageProxy:
    def __init__(self, page: Any, capture: dict[str, float]) -> None:
        self._raw_page = page
        self._capture = capture

    def goto(self, *args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        try:
            return self._raw_page.goto(*args, **kwargs)
        finally:
            self._capture["load_duration_ms"] = max((time.monotonic() - started) * 1000.0, 0.0)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw_page, name)


class _TimedContextProxy:
    def __init__(self, context: Any, capture: dict[str, float]) -> None:
        self._raw_context = context
        self._capture = capture

    def new_page(self) -> _TimedPageProxy:
        return _TimedPageProxy(self._raw_context.new_page(), self._capture)

    def new_cdp_session(self, page: Any) -> Any:
        raw = getattr(page, "_raw_page", page)
        return self._raw_context.new_cdp_session(raw)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw_context, name)


def _shared_ux_gateway_class(ux: Any) -> type:
    original = ux.PlaywrightSyntheticUxGateway

    class SharedCaptureSyntheticUxGateway(original):
        def __init__(self, *, audit_id: str, workspace: AuditWorkspace, session_mode: str = "cold", executable_path: str | None = None) -> None:
            super().__init__(session_mode=session_mode, executable_path=executable_path)
            self._rasai_audit_id = audit_id
            self._rasai_workspace = workspace
            self._rasai_capture_local = threading.local()

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
                )
                return result
            finally:
                self._rasai_capture_local.capture = None

    SharedCaptureSyntheticUxGateway.__name__ = "SharedCaptureSyntheticUxGateway"
    return SharedCaptureSyntheticUxGateway


class SharedAwareNavigationGateway:
    def __init__(self, *, audit_id: str, workspace: AuditWorkspace, delegate: Any) -> None:
        self.audit_id = audit_id
        self.workspace = workspace
        self.delegate = delegate

    def environment(self) -> dict[str, Any]:
        value = dict(self.delegate.environment())
        value["apdex_acquisition_mode"] = acquisition_mode()
        value["shared_acquisition_enabled"] = acquisition_mode() == "auto"
        return value

    def close(self) -> None:
        self.delegate.close()

    def measure(self, *, url: str, profile: Any, timeout_seconds: float) -> Any:
        from rasai.m23_apdex_profiles import NavigationMeasurement

        device = str(getattr(getattr(profile, "device", None), "value", getattr(profile, "device", ""))).upper()
        item = consume_navigation_acquisition(
            audit_id=self.audit_id,
            workspace=self.workspace,
            url=url,
            device=device,
            profile_id=str(getattr(profile, "profile_id", "")),
            timeout_seconds=timeout_seconds,
        )
        if item is None:
            return self.delegate.measure(url=url, profile=profile, timeout_seconds=timeout_seconds)
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
                    "type": "SHARED_ACQUISITION",
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
        "physical_without_sharing": 0,
        "physical_with_sharing": 0,
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
    result["physical_without_sharing"] = int(result["m25_attempted"]) + int(result["m23_attempted"])
    result["physical_with_sharing"] = int(result["m25_attempted"]) + int(result["m23_physical"])
    return result


def _report_block(stats: dict[str, Any]) -> str:
    baseline = int(stats["physical_without_sharing"])
    physical = int(stats["physical_with_sharing"])
    avoided = int(stats["avoided"])
    reduction = (avoided / baseline * 100.0) if baseline else 0.0
    reason = str(stats.get("reason") or "")
    reason_html = f"<p><strong>Fallback/estado:</strong> {escape(reason)}</p>" if reason else ""
    return (
        _MANAGED_START
        + "<section class='panel rasai-shared-apdex-acquisition'>"
        + "<div class='kicker'>Aquisição sintética</div><h2>Uma navegação física, avaliações Apdex independentes</h2>"
        + "<p>Quando URL, dispositivo, perfil sintético e sessão <code>cold</code> são compatíveis, "
          "a mesma navegação física pode fornecer a fronteira de <code>load</code> ao Synthetic Navigation Apdex "
          "e continuar aberta para a observação pós-load do Synthetic User Experience Apdex. "
          "Targets, device mix, thresholds, KPM, política de erros e classificações continuam independentes.</p>"
        + "<div class='metric-grid'>"
        + f"<article class='metric'><span>Modo</span><strong>{escape(str(stats['mode']).upper())}</strong></article>"
        + f"<article class='metric'><span>Aquisições Experience elegíveis</span><strong>{int(stats['eligible'])}</strong></article>"
        + f"<article class='metric'><span>Reutilizadas no Navigation</span><strong>{int(stats['reused'])}</strong></article>"
        + f"<article class='metric'><span>Navegações físicas evitadas</span><strong>{avoided}</strong></article>"
        + f"<article class='metric'><span>Baseline sem compartilhamento</span><strong>{baseline}</strong></article>"
        + f"<article class='metric'><span>Navegações físicas efetivas</span><strong>{physical}</strong></article>"
        + f"<article class='metric'><span>Redução de navegações</span><strong>{reduction:.1f}%</strong></article>"
        + f"<article class='metric'><span>Incompatíveis por timeout M23</span><strong>{int(stats['timeout_incompatible'])}</strong></article>"
        + "</div>"
        + reason_html
        + "<p><strong>Importante:</strong> compartilhamento de aquisição não significa compartilhamento de score. "
          "Uma amostra reaproveitada é reclassificada integralmente pelas regras próprias de cada método.</p>"
        + "</section>"
        + _MANAGED_END
    )


def _remove_managed(html: str) -> str:
    while _MANAGED_START in html:
        start = html.find(_MANAGED_START)
        end = html.find(_MANAGED_END, start)
        if end < 0:
            return html[:start]
        html = html[:start] + html[end + len(_MANAGED_END):]
    return html


def enrich_shared_acquisition_reports(*, audit_id: str, workspace: AuditWorkspace) -> None:
    stats = acquisition_stats(audit_id=audit_id, workspace=workspace)
    if not stats["m23_attempted"] and not stats["m25_attempted"]:
        return
    block = _report_block(stats)
    for filename in ("apdex.html", "apdex-experience.html"):
        path = workspace.root / "report" / filename
        if not path.is_file():
            continue
        try:
            html = _remove_managed(path.read_text(encoding="utf-8"))
            if "</main>" in html:
                html = html.replace("</main>", block + "</main>", 1)
            elif "</body>" in html:
                html = html.replace("</body>", block + "</body>", 1)
            else:
                html += block
            path.write_text(html, encoding="utf-8", newline="\n")
        except (OSError, UnicodeError):
            continue


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def install() -> None:
    """Install the shared-acquisition adapter on the canonical public runtime path."""
    global _INSTALLED
    if _INSTALLED:
        return

    from rasai import cli_extensions
    from rasai import m23_apdex as m23
    from rasai import m23_apdex_profiles as profiles
    from rasai import m25_apdex_experience as ux
    from rasai import m25_runtime
    from rasai import synthetic_profile_reporting

    shared_ux_gateway = _shared_ux_gateway_class(ux)

    original_m25_execute = m25_runtime.execute_m25_experience
    if not getattr(original_m25_execute, "_rasai_shared_acquisition", False):
        def execute_m25_with_shared_acquisition(*, audit_id: str, workspace: AuditWorkspace, config: Any, gateway: Any = None, gateway_factory: Callable[[], Any] | None = None):
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
                factory = lambda: shared_ux_gateway(
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
                "SYNTHETIC_APDEX_ACQUISITION_SOURCE_COMPLETED",
                audit_id=audit_id,
                mode=stats["mode"],
                eligible_acquisitions=stats["eligible"],
                reason=stats.get("reason"),
                scoring_impact="NONE",
            )
            return result

        execute_m25_with_shared_acquisition._rasai_shared_acquisition = True
        execute_m25_with_shared_acquisition._rasai_original = original_m25_execute
        m25_runtime.execute_m25_experience = execute_m25_with_shared_acquisition

    original_m23_execute = cli_extensions.execute_m23_apdex
    if not getattr(original_m23_execute, "_rasai_shared_acquisition", False):
        def execute_m23_with_shared_acquisition(*, audit_id: str, workspace: AuditWorkspace, config: Any = None, gateway: Any = None, gateway_factory: Callable[[], Any] | None = None):
            if gateway is not None or gateway_factory is not None or acquisition_mode() != "auto":
                return original_m23_execute(
                    audit_id=audit_id,
                    workspace=workspace,
                    config=config,
                    gateway=gateway,
                    gateway_factory=gateway_factory,
                )
            factory = lambda: SharedAwareNavigationGateway(
                audit_id=audit_id,
                workspace=workspace,
                delegate=profiles.PlaywrightSyntheticNavigationGateway(),
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
                "SYNTHETIC_APDEX_SHARED_ACQUISITION_COMPLETED",
                audit_id=audit_id,
                mode=stats["mode"],
                experience_eligible=stats["eligible"],
                navigation_reused=stats["reused"],
                navigation_physical=stats["m23_physical"],
                physical_requests_avoided=stats["avoided"],
                scoring_impact="NONE",
            )
            return result

        execute_m23_with_shared_acquisition._rasai_shared_acquisition = True
        execute_m23_with_shared_acquisition._rasai_original = original_m23_execute
        cli_extensions.execute_m23_apdex = execute_m23_with_shared_acquisition
        if m23.execute_m23_apdex is original_m23_execute:
            m23.execute_m23_apdex = execute_m23_with_shared_acquisition

    original_enrich = synthetic_profile_reporting.enrich_synthetic_profile_reports
    if not getattr(original_enrich, "_rasai_shared_acquisition", False):
        def enrich_with_shared_acquisition(*, audit_id: str, workspace: AuditWorkspace):
            result = original_enrich(audit_id=audit_id, workspace=workspace)
            enrich_shared_acquisition_reports(audit_id=audit_id, workspace=workspace)
            return result

        enrich_with_shared_acquisition._rasai_shared_acquisition = True
        enrich_with_shared_acquisition._rasai_original = original_enrich
        synthetic_profile_reporting.enrich_synthetic_profile_reports = enrich_with_shared_acquisition

    _INSTALLED = True
