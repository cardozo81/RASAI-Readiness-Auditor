"""Explicit Windows Task Scheduler integration for authorized GeoIP maintenance.

This is a user-scoped registration step invoked by maintenance/setup, never AUD.
It does not store MaxMind credentials in the task command.
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

TASK_NAME = "RASAi-GeoIP-Daily"


def install_daily_windows_task(config: Path, *, licensed: bool,
                               authorized: bool) -> dict:
    if not licensed or not authorized:
        return {"state": "NOT_AUTHORIZED", "error": "EXPLICIT_LICENSE_AND_SCHEDULE_CONSENT_REQUIRED"}
    if sys.platform != "win32":
        return {"state": "NOT_APPLICABLE", "error": "WINDOWS_ONLY"}
    path = Path(config)
    if (not path.is_absolute() or not path.is_file() or path.is_symlink()
            or any(char in str(path) for char in '"\r\n\x00')):
        return {"state": "NOT_CONFIGURED", "error": "INVALID_GEOIP_CONFIG"}
    binary = Path(sys.executable)
    if not binary.is_file():
        return {"state": "NOT_CONFIGURED", "error": "INVALID_RASAI_PYTHON"}
    command = (f'"{binary}" -m rasai.network_geoip_maintenance '
               f'--config "{path}" --license-accepted --allow-install')
    try:
        result = subprocess.run(
            ["schtasks", "/Create", "/SC", "DAILY", "/ST", "09:00", "/TN", TASK_NAME,
             "/TR", command, "/F"],
            capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "FAILED", "error": "SCHEDULE_REGISTRATION_FAILED"}
    return {"state": "SCHEDULED" if result.returncode == 0 else "FAILED",
            "error": None if result.returncode == 0 else "SCHEDULE_REGISTRATION_FAILED"}


def remove_daily_windows_task(*, authorized: bool) -> dict:
    if not authorized:
        return {"state": "NOT_AUTHORIZED", "error": "EXPLICIT_REVOCATION_REQUIRED"}
    if sys.platform != "win32":
        return {"state": "NOT_APPLICABLE", "error": "WINDOWS_ONLY"}
    try:
        result = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                                capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"state": "FAILED", "error": "SCHEDULE_REMOVAL_FAILED"}
    return {"state": "REMOVED" if result.returncode == 0 else "FAILED",
            "error": None if result.returncode == 0 else "SCHEDULE_REMOVAL_FAILED"}
