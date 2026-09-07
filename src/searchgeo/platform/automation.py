"""Safe local scheduler primitives for RASAI Windows/CLI operation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import subprocess
import sys
from typing import Sequence

from .models import Schedule
from .store import PlatformStore, utc_now


@dataclass(frozen=True, slots=True)
class ScheduleRunResult:
    schedule_id: str
    started_at: str
    completed_at: str
    return_code: int
    status: str
    stdout: str
    stderr: str
    next_run_at: str | None


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compute_next_run(schedule: Schedule, *, after: datetime | None = None) -> str | None:
    now = after or datetime.now().astimezone()
    if schedule.kind == "INTERVAL":
        minutes = schedule.interval_minutes or 0
        if minutes < 1:
            raise ValueError("INTERVAL schedule requires interval_minutes >= 1")
        return (now + timedelta(minutes=minutes)).isoformat()
    if schedule.kind == "DAILY":
        if not schedule.daily_time or ":" not in schedule.daily_time:
            raise ValueError("DAILY schedule requires daily_time HH:MM")
        hour_text, minute_text = schedule.daily_time.split(":", 1)
        candidate = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.isoformat()
    if schedule.kind in {"MANUAL", "DEPLOYMENT_TRIGGERED", "API_TRIGGERED"}:
        return None
    raise ValueError(f"unsupported schedule kind: {schedule.kind}")


def run_schedule(
    store: PlatformStore,
    schedule: Schedule,
    *,
    timeout_seconds: int = 60 * 60,
    extra_env: dict[str, str] | None = None,
) -> ScheduleRunResult:
    """Execute only the RASAI Python module, never an arbitrary shell string."""
    if not schedule.enabled:
        raise ValueError(f"schedule is disabled: {schedule.schedule_id}")
    started = utc_now()
    argv = [sys.executable, "-m", "searchgeo", *schedule.command_argv]
    env = None
    if extra_env:
        import os
        env = dict(os.environ)
        env.update(extra_env)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
            shell=False,
            env=env,
            check=False,
        )
        code = int(completed.returncode)
        status = "SUCCESS" if code == 0 else "FAILED"
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        code = 124
        status = "TIMEOUT"
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
    completed_at = utc_now()
    next_run = compute_next_run(schedule, after=_parse(completed_at))
    store.update_schedule_run(
        schedule.schedule_id,
        last_run_at=completed_at,
        last_status=status,
        next_run_at=next_run,
    )
    return ScheduleRunResult(
        schedule.schedule_id,
        started,
        completed_at,
        code,
        status,
        stdout,
        stderr,
        next_run,
    )


def run_due_schedules(
    store: PlatformStore,
    *,
    now: str | None = None,
    timeout_seconds: int = 60 * 60,
) -> tuple[ScheduleRunResult, ...]:
    cutoff = now or utc_now()
    schedules = store.list_schedules(due_before=cutoff, enabled_only=True)
    return tuple(run_schedule(store, item, timeout_seconds=timeout_seconds) for item in schedules)
