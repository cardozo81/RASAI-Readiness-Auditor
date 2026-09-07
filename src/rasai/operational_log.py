"""Persistent, secret-safe operational log for one audit workspace.

The log is JSON Lines so it remains human-readable while also being easy to parse.
It is intentionally separate from audit evidence/scoring and from the process
console logger. Callers must never pass credential values as event fields.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from rasai.persistence import AuditWorkspace


LOG_DIRECTORY = "logs"
LOG_FILE = "audit.log"
_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
)


def operational_log_path(workspace: AuditWorkspace) -> Path:
    """Return the stable operational-log path for an audit workspace."""
    return workspace.root / LOG_DIRECTORY / LOG_FILE


def append_operational_event(
    workspace: AuditWorkspace,
    event: str,
    *,
    level: str = "INFO",
    **details: Any,
) -> Path:
    """Append one sanitized JSONL event and return the log path.

    The writer redacts values whose field name looks credential-bearing. It does
    not log environment variables, HTTP request URLs containing API keys, or
    authorization headers. External-service callers should log the audited URL,
    service name, status and sanitized error metadata instead.
    """
    path = operational_log_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": str(level).upper(),
        "event": str(event),
        **_sanitize_mapping(details),
    }
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        stream.write("\n")
    return path


def try_append_operational_event(
    workspace: AuditWorkspace,
    event: str,
    *,
    level: str = "INFO",
    **details: Any,
) -> Path | None:
    """Best-effort wrapper that never changes the audit result on log I/O failure."""
    try:
        return append_operational_event(workspace, event, level=level, **details)
    except OSError:
        return None


def _sanitize_mapping(values: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _sanitize_value(str(key), value) for key, value in values.items()}


def _sanitize_value(key: str, value: Any) -> Any:
    normalized = key.casefold().replace("-", "_")
    if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return _REDACTED
    if isinstance(value, dict):
        return _sanitize_mapping({str(item_key): item_value for item_key, item_value in value.items()})
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize_value(key, item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
