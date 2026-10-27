"""Dispatch one approved post-AUD network complement, never during RPR/CONS.

This only invokes the already canonical network_acceptance worker. It does not
probe from report rendering, mutate audit.db or wait for traceroute completion.
"""
from __future__ import annotations

from configparser import ConfigParser, Error as ConfigError
import os
from pathlib import Path
import subprocess
import sys

from rasai.network_active_policy import authorized_hostname
from rasai.console_settings import resolve_config_path


def _approved_host() -> str | None:
    """Only explicit true + exact host from current session or persisted INI."""
    values = {key: os.environ[key] for key in
              ("RASAI_NETWORK_ACTIVE_ENABLED", "RASAI_NETWORK_ACTIVE_HOST")
              if key in os.environ}
    if values:
        return authorized_hostname(values)
    path = resolve_config_path()
    if path.is_symlink() or not path.is_file():
        return None
    try:
        if path.stat().st_size > 500_000:
            return None
        parser = ConfigParser(interpolation=None)
        parser.read(path, encoding="utf-8")
        return authorized_hostname({
            "RASAI_NETWORK_ACTIVE_ENABLED": parser.get(
                "environment", "RASAI_NETWORK_ACTIVE_ENABLED", fallback="false"),
            "RASAI_NETWORK_ACTIVE_HOST": parser.get(
                "environment", "RASAI_NETWORK_ACTIVE_HOST", fallback=""),
        })
    except (OSError, ConfigError, ValueError):
        return None


def _sealed_primary_host(workspace: Path, audit_id: str) -> str | None:
    """Read the one original console target; redirect URLs cannot inherit consent."""
    from rasai.audit_configuration_reuse import (
        KIND_CONSOLE, load_reusable_audit_configuration,
    )
    from rasai.network_active_policy import hostname_from_audit_url

    try:
        snapshot = load_reusable_audit_configuration(
            workspace.parent, audit_id, expected_kind=KIND_CONSOLE,
        )
        targets = snapshot.configuration.get("targets")
        if not isinstance(targets, list) or len(targets) != 1:
            return None
        return hostname_from_audit_url(targets[0])
    except (OSError, ValueError, TypeError):
        return None


def dispatch_for_new_audit(workspace: str | Path, audit_id: str) -> dict:
    """Non-blocking best-effort sidecar dispatch once the initial AUD is sealed."""
    host = _approved_host()
    if host is None:
        return {"state": "NOT_AUTHORIZED"}
    from rasai.network_active_probe import _audit_has_target, probe_path
    root = Path(workspace)
    # A previously authorized host may appear only as a redirect in a new AUD;
    # check the sealed primary URL, not just any observed page/redirect.
    if _sealed_primary_host(root, audit_id) != host:
        return {"state": "OUT_OF_SCOPE"}
    if not _audit_has_target(root, audit_id, host):
        return {"state": "OUT_OF_SCOPE"}
    existing = probe_path(root, audit_id, host, 443)
    if existing.exists() or existing.is_symlink():
        return {"state": "ALREADY_COLLECTED"}
    cmd = [sys.executable, "-m", "rasai.network_acceptance",
           "--workspace", str(root), "--audit-id", audit_id,
           "--host", host, "--permit-exact-host", host,
           "--authorize-active-network", "--include-traceroute"]
    # Do not forward unrelated provider credentials into a network worker.
    allowed = {"PATH", "Path", "SystemRoot", "WINDIR", "LOCALAPPDATA",
               "APPDATA", "USERPROFILE", "HOME", "TEMP", "TMP", "LANG",
               "LC_ALL", "PYTHONIOENCODING", "VIRTUAL_ENV"}
    child_env = {key: value for key, value in os.environ.items() if key in allowed}
    from rasai.network_active_policy import max_hops, validate_network_setting
    child_env["RASAI_NETWORK_MAX_HOPS"] = str(max_hops())
    source = os.environ.get("RASAI_NETWORK_GEOIP_SOURCE", "LOCAL_FIRST")
    try:
        child_env["RASAI_NETWORK_GEOIP_SOURCE"] = validate_network_setting(
            "RASAI_NETWORK_GEOIP_SOURCE", source)
    except ValueError:
        child_env["RASAI_NETWORK_GEOIP_SOURCE"] = "DISABLED"
    options = {"env": child_env}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True, **options)
    except OSError:
        return {"state": "DISPATCH_FAILED"}
    return {"state": "DISPATCHED"}
