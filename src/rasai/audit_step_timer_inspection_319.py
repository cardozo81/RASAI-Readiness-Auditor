"""#319: non-authoritative, read-only physical wrapper timer evidence.

The audit progress runtime records monotonic time in AUDIT_PIPELINE_STEP_FINISHED
events. Operational JSONL is not sealed evidence, and wrapper intervals can
overlap, nest, fail, or belong to continuation/replay. Never sum as phase
wall clock or promote to a calibrated timing forecast.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any

_MAX_BYTES = 8 * 1024 * 1024
_MAX_EVENTS = 4000
_MAX_DURATION_MS = 48 * 60 * 60 * 1000
_KEY = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _epoch_ms(raw: object) -> float | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return None
        ms = instant.astimezone(timezone.utc).timestamp() * 1000
        return ms if math.isfinite(ms) else None
    except (TypeError, ValueError, OverflowError):
        return None


def inspect_pipeline_step_timers(
    audit_dir: Path,
    audit_id: str,
    verified_console_window: tuple[float, float, float] | None,
) -> dict[str, Any]:
    """Read only audited-ID-matched, bounded JSONL timers, never modify AUD."""
    result = {
        "contract_version": "RASAI-PIPELINE-STEP-TIMERS-319-001",
        "status": "NOT_AVAILABLE",
        "source": "logs/audit.log",
        "physical_wrapper_timer_observed": False,
        "exclusive_stage_wall_clock_proven": False,
        "operational_log_sealed_evidence": False,
        "stage_forecast_calibrated": False,
        "by_step": [],
        "provider_requests": 0,
        "audit_writes": 0,
        "limitations": (
            "Duracoes monotônicas observadas por wrapper do pipeline, nunca "
            "temporizadores exclusivos por etapa nem partes aditivas da AUD. "
            "O audit.log operacional não foi selado como evidência de "
            "cronômetros físicos; continuacoes e reprocessos podem coexistir. "
            "Nao somar durations para prever tempo total ou inferir custo."
        ),
    }
    root = Path(audit_dir)
    log_dir = root / "logs"
    path = log_dir / "audit.log"
    if root.is_symlink() or log_dir.is_symlink() or path.is_symlink():
        result["status"] = "UNTRUSTED_LOG_PATH"
        return result
    if not path.is_file():
        return result
    try:
        if path.stat().st_size > _MAX_BYTES:
            result["status"] = "LOG_TOO_LARGE"
            return result
        with path.open("rb") as stream:
            data = stream.read(_MAX_BYTES + 1)
    except OSError:
        result["status"] = "LOG_READ_UNAVAILABLE"
        return result
    if len(data) > _MAX_BYTES:
        result["status"] = "LOG_TOO_LARGE"
        return result
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError:
        result["status"] = "LOG_ENCODING_INVALID"
        return result
    if len(lines) > 200000:
        result["status"] = "LOG_TOO_MANY_LINES"
        return result
    steps = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except (TypeError, ValueError):
            # A partially written JSONL log cannot be used to assert the
            # completeness of timers; refuse to publish partial results.
            result["status"] = "LOG_JSON_INVALID"
            return result
        if not isinstance(item, dict):
            result["status"] = "LOG_JSON_INVALID"
            return result
        if item.get("event") != "AUDIT_PIPELINE_STEP_FINISHED":
            continue
        if item.get("audit_id") != audit_id:
            continue
        if len(steps) >= _MAX_EVENTS:
            result["status"] = "STEP_LIMIT_EXCEEDED"
            return result
        duration = item.get("duration_ms")
        finish = _epoch_ms(item.get("timestamp"))
        phase = item.get("phase")
        step_key = item.get("step_key")
        status = item.get("status")
        if (
            type(duration) is not int or not 0 <= duration <= _MAX_DURATION_MS
            or finish is None
            or not isinstance(phase, str) or not _KEY.fullmatch(phase)
            or not isinstance(step_key, str) or not _KEY.fullmatch(step_key)
            or status not in ("SUCCESS", "ERROR")
        ):
            result["status"] = "STEP_EVIDENCE_INVALID"
            return result
        # The log timestamp is the wrapper finish. Placement can be
        # indicative only; the monotonic clock is not UTC and no verified
        # execution_id exists in the JSONL event.
        attributed = (
            verified_console_window is not None
            and verified_console_window[1] <= finish - duration
            and finish <= verified_console_window[2]
        )
        steps.append({
            "phase": phase,
            "step_key": step_key,
            "operation_status": status,
            "observed_monotonic_wrapper_ms": duration,
            "recorded_at_utc": item["timestamp"],
            "console_window_placement": (
                "WITHIN_VERIFIED_WINDOW_UNSEALED"
                if attributed else "NOT_PROVEN_IN_INITIAL_WINDOW"
            ),
        })
    if steps:
        result["status"] = "OBSERVED_UNSEALED_WRAPPER_TIMERS"
        result["physical_wrapper_timer_observed"] = True
        result["by_step"] = steps
    else:
        result["status"] = "NO_PIPELINE_STEP_TIMERS"
    return result
