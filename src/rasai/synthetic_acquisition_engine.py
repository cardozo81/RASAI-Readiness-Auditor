"""Neutral physical acquisition owner for synthetic measurement consumers.

This module owns raw synthetic acquisition envelopes and their traceability.  It has
no dependency on CAT-06/M23 or CAT-07/M25 evaluators and never calculates Apdex.
Consumers may project the same compatible raw occurrence into independent methods.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import sqlite3
import threading
import time
from typing import Any, Mapping

from rasai.domain import new_id
from rasai.persistence import AuditWorkspace

LOAD_ONLY = "LOAD_ONLY"
FULL_EXPERIENCE = "FULL_EXPERIENCE"
_ALLOWED_ENVELOPES = frozenset({LOAD_ONLY, FULL_EXPERIENCE})


@dataclass(frozen=True, slots=True)
class SyntheticAcquisitionEnvelope:
    acquisition_id: str
    audit_id: str
    url: str
    device: str
    profile_id: str
    envelope_kind: str
    session_mode: str
    load_duration_ms: float
    status: str
    http_status: int | None
    final_url: str | None
    cpu_method: str | None
    network_method: str | None
    full_observables: Mapping[str, Any] | None
    planning_ordinal: int | None
    captured_at: str

    @property
    def created_at(self) -> str:
        """Compatibility alias for the pre-engine shared-acquisition contract."""
        return self.captured_at


_lock = threading.RLock()
_pool: dict[tuple[str, str, str, str], deque[SyntheticAcquisitionEnvelope]] = defaultdict(deque)


@dataclass(frozen=True, slots=True)
class SyntheticAcquisitionPlan:
    navigation_samples: int
    experience_samples: int
    full_experience: int
    load_only: int
    total_physical: int
    navigation_ordinals: tuple[int, ...]


def uniform_ordinals(select_count: int, population_count: int) -> tuple[int, ...]:
    """Select deterministic zero-based ordinals across the whole planned population."""
    select = max(int(select_count), 0)
    population = max(int(population_count), 0)
    if select <= 0 or population <= 0:
        return ()
    if select >= population:
        return tuple(range(population))
    if select == 1:
        return ((population - 1) // 2,)
    values = tuple(
        int(round(index * (population - 1) / (select - 1)))
        for index in range(select)
    )
    if len(set(values)) != select:
        # This should not occur when select < population, but preserve determinism
        # if integer rounding behavior ever changes.
        values = tuple((index * population) // select for index in range(select))
    return values


def plan_acquisitions(
    navigation_samples: int,
    experience_samples: int,
) -> SyntheticAcquisitionPlan:
    navigation = max(int(navigation_samples), 0)
    experience = max(int(experience_samples), 0)
    full = experience
    load_only = max(navigation - experience, 0)
    total = max(navigation, experience)
    reused = min(navigation, experience)
    ordinals = uniform_ordinals(reused, experience)
    return SyntheticAcquisitionPlan(
        navigation_samples=navigation,
        experience_samples=experience,
        full_experience=full,
        load_only=load_only,
        total_physical=total,
        navigation_ordinals=ordinals,
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def acquisition_key(
    audit_id: str,
    url: str,
    device: str,
    profile_id: str,
) -> tuple[str, str, str, str]:
    return (str(audit_id), str(url), str(device).upper(), str(profile_id))


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


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
            created_at TEXT NOT NULL,
            envelope_kind TEXT,
            session_mode TEXT,
            full_observables_json TEXT,
            planning_ordinal INTEGER,
            captured_at TEXT
        )
        """
    )
    columns = _columns(connection, "synthetic_apdex_acquisitions")
    for name, definition in (
        ("envelope_kind", "TEXT"),
        ("session_mode", "TEXT"),
        ("full_observables_json", "TEXT"),
        ("planning_ordinal", "INTEGER"),
        ("captured_at", "TEXT"),
    ):
        if name not in columns:
            connection.execute(
                f"ALTER TABLE synthetic_apdex_acquisitions ADD COLUMN {name} {definition}"
            )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_synthetic_apdex_acquisition_lookup "
        "ON synthetic_apdex_acquisitions(audit_id,url,device,profile_id,created_at)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS synthetic_acquisition_replay_links(
            link_id TEXT PRIMARY KEY,
            audit_id TEXT NOT NULL,
            acquisition_id TEXT NOT NULL,
            consumer TEXT NOT NULL,
            sample_id TEXT NOT NULL,
            phase TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            UNIQUE(audit_id,acquisition_id,consumer)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_synthetic_acquisition_replay_lookup "
        "ON synthetic_acquisition_replay_links(audit_id,consumer,acquisition_id)"
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
    """Start a fresh acquisition ledger for an initial synthetic collection run."""
    with _lock:
        for key in [item for item in _pool if item[0] == audit_id]:
            _pool.pop(key, None)
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                "DELETE FROM synthetic_acquisition_replay_links WHERE audit_id=?",
                (audit_id,),
            )
            connection.execute(
                "DELETE FROM synthetic_apdex_acquisitions WHERE audit_id=?",
                (audit_id,),
            )
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
                (audit_id, mode, reason, 0, 0, 0, utc_now()),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        # Traceability is additive. Failure to persist this optional ledger must not
        # turn an otherwise valid synthetic evaluator execution into an audit failure.
        pass


def ensure_acquisition_run(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    mode: str,
    reason: str | None = None,
) -> None:
    """Materialize a run row without clearing envelopes already produced by another consumer."""
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                """
                INSERT OR IGNORE INTO synthetic_apdex_acquisition_runs(
                    audit_id,mode,reason,eligible_acquisitions,reused_by_navigation,
                    timeout_incompatible,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (audit_id, mode, reason, 0, 0, 0, utc_now()),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass


def _update_run_counter(
    workspace: AuditWorkspace,
    audit_id: str,
    column: str,
    increment: int = 1,
) -> None:
    if column not in {"eligible_acquisitions", "reused_by_navigation", "timeout_incompatible"}:
        return
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                f"UPDATE synthetic_apdex_acquisition_runs "
                f"SET {column}={column}+?,updated_at=? WHERE audit_id=?",
                (int(increment), utc_now(), audit_id),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass


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


def full_observables_from_measurement(measurement: Any) -> dict[str, Any]:
    """Project raw post-load facts without applying any CAT-07 classification."""
    scalar_fields = (
        "user_action_duration_ms",
        "navigation_duration_ms",
        "response_start_ms",
        "response_end_ms",
        "dom_interactive_ms",
        "load_event_start_ms",
        "load_event_end_ms",
        "lcp_ms",
        "cls",
        "xhr_fetch_count",
        "dynamic_resource_count",
        "javascript_error_count",
        "console_error_count",
        "request_failed_count",
        "first_party_request_failed_count",
        "http_error_count",
        "first_party_http_error_count",
        "csp_violation_count",
        "first_party_csp_violation_count",
        "failed_image_request_count",
        "first_party_failed_image_request_count",
        "network_settled",
        "error_code",
        "error_message",
    )
    result = {name: getattr(measurement, name, None) for name in scalar_fields}
    result["csp_violation_details"] = list(
        getattr(measurement, "csp_violation_details", ()) or ()
    )
    result["request_error_events"] = list(
        getattr(measurement, "request_error_events", ()) or ()
    )
    return result


def record_acquisition(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile_id: str,
    envelope_kind: str,
    session_mode: str,
    load_duration_ms: float,
    status: str,
    http_status: Any = None,
    final_url: Any = None,
    cpu_method: Any = None,
    network_method: Any = None,
    full_observables: Mapping[str, Any] | None = None,
    source: str,
    reusable_for_load: bool = False,
    consumed_by_navigation: bool = False,
    planning_ordinal: int | None = None,
    captured_at: str | None = None,
) -> SyntheticAcquisitionEnvelope | None:
    kind = str(envelope_kind).upper()
    if kind not in _ALLOWED_ENVELOPES:
        raise ValueError(f"unsupported synthetic acquisition envelope: {envelope_kind}")
    try:
        duration = float(load_duration_ms)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(duration) or duration < 0:
        return None
    profile = str(profile_id or "").strip()
    if not profile:
        return None
    if kind == LOAD_ONLY and full_observables:
        raise ValueError("LOAD_ONLY acquisition cannot contain post-load observables")

    item = SyntheticAcquisitionEnvelope(
        acquisition_id=new_id("SYN"),
        audit_id=str(audit_id),
        url=str(url),
        device=str(device).upper(),
        profile_id=profile,
        envelope_kind=kind,
        session_mode=str(session_mode or "cold").casefold(),
        load_duration_ms=duration,
        status=str(status),
        http_status=_optional_int(http_status),
        final_url=_optional_text(final_url),
        cpu_method=_optional_text(cpu_method),
        network_method=_optional_text(network_method),
        full_observables=dict(full_observables) if full_observables is not None else None,
        planning_ordinal=int(planning_ordinal) if planning_ordinal is not None else None,
        captured_at=str(captured_at or utc_now()),
    )
    if reusable_for_load:
        with _lock:
            _pool[acquisition_key(audit_id, item.url, item.device, item.profile_id)].append(item)
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                """
                INSERT OR REPLACE INTO synthetic_apdex_acquisitions(
                    acquisition_id,audit_id,url,device,profile_id,source,source_status,
                    load_duration_ms,http_status,final_url,cpu_method,network_method,
                    consumed_by_navigation,consumed_at,created_at,
                    envelope_kind,session_mode,full_observables_json,planning_ordinal,captured_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.acquisition_id,item.audit_id,item.url,item.device,item.profile_id,
                    str(source),item.status,item.load_duration_ms,item.http_status,item.final_url,
                    item.cpu_method,item.network_method,int(bool(consumed_by_navigation)),
                    item.captured_at if consumed_by_navigation else None,
                    item.captured_at,item.envelope_kind,
                    item.session_mode,
                    json.dumps(item.full_observables, ensure_ascii=False, sort_keys=True)
                    if item.full_observables is not None else None,
                    item.planning_ordinal,
                    item.captured_at,
                ),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass
    if reusable_for_load:
        _update_run_counter(workspace, audit_id, "eligible_acquisitions")
    return item


def prepare_navigation_claims(
    *,
    audit_id: str,
    url: str,
    device: str,
    profile_id: str,
    navigation_samples: int,
) -> SyntheticAcquisitionPlan:
    """Restrict claim candidates using pre-start ordinals, never completion order."""
    key = acquisition_key(audit_id, url, device, profile_id)
    with _lock:
        current = list(_pool.get(key, ()))
        ordered = sorted(
            current,
            key=lambda item: (
                item.planning_ordinal is None,
                item.planning_ordinal if item.planning_ordinal is not None else 2**31,
                item.captured_at,
                item.acquisition_id,
            ),
        )
        plan = plan_acquisitions(navigation_samples, len(ordered))
        selected = [ordered[index] for index in plan.navigation_ordinals]
        _pool[key] = deque(selected)
    return plan


def claim_load_boundary(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile_id: str,
    timeout_seconds: float,
) -> SyntheticAcquisitionEnvelope | None:
    key = acquisition_key(audit_id, url, device, profile_id)
    selected: SyntheticAcquisitionEnvelope | None = None
    timed_out: list[SyntheticAcquisitionEnvelope] = []
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
                "UPDATE synthetic_apdex_acquisitions "
                "SET consumed_by_navigation=1,consumed_at=? WHERE acquisition_id=?",
                (utc_now(), selected.acquisition_id),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        pass
    _update_run_counter(workspace, audit_id, "reused_by_navigation")
    return selected



def claim_persisted_load_boundary(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile_id: str,
    timeout_seconds: float,
) -> SyntheticAcquisitionEnvelope | None:
    """Claim an unconsumed persisted load boundary after process restart."""
    try:
        connection = _connect(workspace)
        try:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT * FROM synthetic_apdex_acquisitions
                WHERE audit_id=? AND url=? AND device=? AND profile_id=?
                  AND consumed_by_navigation=0
                ORDER BY
                  CASE WHEN planning_ordinal IS NULL THEN 1 ELSE 0 END,
                  planning_ordinal,
                  COALESCE(captured_at,created_at),
                  acquisition_id
                """,
                (
                    str(audit_id),
                    str(url),
                    str(device).upper(),
                    str(profile_id),
                ),
            ).fetchall()
            selected = None
            incompatible = 0
            for row in rows:
                duration = float(row["load_duration_ms"])
                if duration <= float(timeout_seconds) * 1000.0:
                    selected = row
                    break
                incompatible += 1
            if incompatible:
                _update_run_counter(workspace, audit_id, "timeout_incompatible", incompatible)
            if selected is None:
                return None
            connection.execute(
                "UPDATE synthetic_apdex_acquisitions "
                "SET consumed_by_navigation=1,consumed_at=? WHERE acquisition_id=?",
                (utc_now(), str(selected["acquisition_id"])),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    _update_run_counter(workspace, audit_id, "reused_by_navigation")
    return _envelope_from_row(selected)


def available_full_envelopes(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    url: str,
    device: str,
    profile_id: str,
) -> tuple[SyntheticAcquisitionEnvelope, ...]:
    """Return persisted FULL envelopes eligible for evaluator-local offline replay."""
    try:
        connection = _connect(workspace)
        try:
            rows = connection.execute(
                """
                SELECT * FROM synthetic_apdex_acquisitions
                WHERE audit_id=? AND url=? AND device=? AND profile_id=?
                  AND envelope_kind=? AND full_observables_json IS NOT NULL
                ORDER BY
                  CASE WHEN planning_ordinal IS NULL THEN 1 ELSE 0 END,
                  planning_ordinal,
                  COALESCE(captured_at,created_at),
                  acquisition_id
                """,
                (
                    str(audit_id),
                    str(url),
                    str(device).upper(),
                    str(profile_id),
                    FULL_EXPERIENCE,
                ),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return ()
    return tuple(_envelope_from_row(row) for row in rows)


def record_replay_link(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    acquisition_id: str,
    consumer: str,
    sample_id: str,
    phase: str = "RPR",
) -> bool:
    """Persist acquisition->sample provenance without changing evaluator state."""
    try:
        connection = _connect(workspace)
        try:
            connection.execute(
                """
                INSERT INTO synthetic_acquisition_replay_links(
                    link_id,audit_id,acquisition_id,consumer,sample_id,phase,linked_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    new_id("SRL"),
                    str(audit_id),
                    str(acquisition_id),
                    str(consumer),
                    str(sample_id),
                    str(phase),
                    utc_now(),
                ),
            )
            connection.commit()
            return True
        finally:
            connection.close()
    except sqlite3.IntegrityError:
        return False
    except sqlite3.Error:
        return False


def replay_linked_acquisition_ids(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    consumer: str,
) -> frozenset[str]:
    try:
        connection = _connect(workspace)
        try:
            rows = connection.execute(
                "SELECT acquisition_id FROM synthetic_acquisition_replay_links "
                "WHERE audit_id=? AND consumer=?",
                (str(audit_id), str(consumer)),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return frozenset()
    return frozenset(str(row[0]) for row in rows)


def _envelope_from_row(row: sqlite3.Row) -> SyntheticAcquisitionEnvelope:
    raw = row["full_observables_json"] if "full_observables_json" in row.keys() else None
    try:
        full = json.loads(raw) if raw else None
    except (TypeError, ValueError, json.JSONDecodeError):
        full = None
    return SyntheticAcquisitionEnvelope(
        acquisition_id=str(row["acquisition_id"]),
        audit_id=str(row["audit_id"]),
        url=str(row["url"]),
        device=str(row["device"]),
        profile_id=str(row["profile_id"]),
        envelope_kind=str(row["envelope_kind"] or LOAD_ONLY),
        session_mode=str(row["session_mode"] or "cold"),
        load_duration_ms=float(row["load_duration_ms"]),
        status=str(row["source_status"]),
        http_status=_optional_int(row["http_status"]),
        final_url=_optional_text(row["final_url"]),
        cpu_method=_optional_text(row["cpu_method"]),
        network_method=_optional_text(row["network_method"]),
        full_observables=full if isinstance(full, Mapping) else None,
        planning_ordinal=(
            int(row["planning_ordinal"])
            if "planning_ordinal" in row.keys() and row["planning_ordinal"] is not None
            else None
        ),
        captured_at=str(row["captured_at"] or row["created_at"]),
    )


def persisted_envelopes(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
) -> tuple[SyntheticAcquisitionEnvelope, ...]:
    """Read neutral envelopes from SQLite for replay/inspection without evaluator imports."""
    try:
        connection = _connect(workspace)
        try:
            rows = connection.execute(
                "SELECT * FROM synthetic_apdex_acquisitions WHERE audit_id=? "
                "ORDER BY COALESCE(captured_at,created_at),acquisition_id",
                (audit_id,),
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return ()
    return tuple(_envelope_from_row(row) for row in rows)


class TimedPageProxy:
    """Freeze the load boundary while allowing the caller to continue post-load work."""

    def __init__(self, page: Any, capture: dict[str, float]) -> None:
        self._raw_page = page
        self._capture = capture

    def goto(self, *args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        try:
            return self._raw_page.goto(*args, **kwargs)
        finally:
            self._capture["load_duration_ms"] = max(
                (time.monotonic() - started) * 1000.0,
                0.0,
            )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw_page, name)


class TimedContextProxy:
    def __init__(self, context: Any, capture: dict[str, float]) -> None:
        self._raw_context = context
        self._capture = capture

    def new_page(self) -> TimedPageProxy:
        return TimedPageProxy(self._raw_context.new_page(), self._capture)

    def new_cdp_session(self, page: Any) -> Any:
        raw = getattr(page, "_raw_page", page)
        return self._raw_context.new_cdp_session(raw)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw_context, name)


__all__ = [
    "LOAD_ONLY",
    "FULL_EXPERIENCE",
    "SyntheticAcquisitionEnvelope",
    "SyntheticAcquisitionPlan",
    "TimedContextProxy",
    "TimedPageProxy",
    "available_full_envelopes",
    "claim_load_boundary",
    "claim_persisted_load_boundary",
    "ensure_acquisition_run",
    "full_observables_from_measurement",
    "persisted_envelopes",
    "plan_acquisitions",
    "prepare_acquisition_run",
    "prepare_navigation_claims",
    "record_acquisition",
    "record_replay_link",
    "replay_linked_acquisition_ids",
    "uniform_ordinals",
]
