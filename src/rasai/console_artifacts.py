"""Navigation helpers for artifacts produced by the optional interactive console."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

from rasai.console_config import State


def audit_workspace(state: State) -> Path | None:
    """Resolve only the workspace belonging to the audit held by this console state."""
    audit_id = state.audit_id.strip()
    if not audit_id or not audit_id.startswith("AUD-"):
        return None
    candidate = Path(state.audits_root).expanduser() / audit_id
    return candidate.resolve() if candidate.is_dir() else None


def report_entrypoint(workspace: Path | None) -> Path | None:
    """Resolve the supported catalog-report entrypoint only."""
    if workspace is None:
        return None
    catalog = workspace / "report-catalog" / "index.html"
    if not catalog.is_file():
        return None
    try:
        from rasai.catalog_report_site import verify_catalog_report_package
        valid, _errors = verify_catalog_report_package(catalog.parent)
    except Exception:
        return None
    return catalog.resolve() if valid else None


# The post-AUD network sidecar runs independently of the sealed AUD. A
# browser opened immediately after the AUD might otherwise retain the older
# (valid, but pre-probe) HTML until the user refreshes it manually.
_NETWORK_REPORT_OPEN_BUDGET_SECONDS = 60.0
_NETWORK_REPORT_RECENT_SECONDS = 120.0


def _synchronize_network_report_before_open(path: Path) -> str:
    """Wait only at explicit report opening; never repeat an active probe.

    A final report is always built by the canonical acceptance worker, not
    by this viewer. Historical stale reports with an already persisted probe
    can be projected read-only, without changing audit.db or calling a socket.
    The bounded wait is a presentation gate, not a pipeline/collector gate.
    """
    if (path.suffix.lower() != ".html" or
            path.name not in {"index.html", "network.html"} or
            path.parent.name != "report-catalog"):
        return "NOT_APPLICABLE"
    root = path.parent.parent
    if not (root / "audit.db").is_file():
        return "NOT_APPLICABLE"

    try:
        from rasai.catalog_report_site import catalog_report_is_fresh
        from rasai.network_active_probe import probe_path, read_authorized_probes
        from rasai.network_auto_probe import _approved_host, _sealed_primary_host
        from rasai.persistence import AuditWorkspace

        audit_id = root.name
        workspace = AuditWorkspace.open(root)
        current_probes = read_authorized_probes(root, audit_id)
        if current_probes and catalog_report_is_fresh(audit_id=audit_id, workspace=workspace):
            return "READY"

        # An older historical AUD is never delayed waiting for a new probe.
        # Only a recent, explicitly authorized, exact-host AUD may have an
        # asynchronous companion still running when the operator opens it.
        manifest = root / "report-catalog" / "manifest.json"
        recent = (manifest.is_file() and
                  0 <= time.time() - manifest.stat().st_mtime <=
                  _NETWORK_REPORT_RECENT_SECONDS)
        host = _approved_host() if recent else None
        pending = bool(host and _sealed_primary_host(root, audit_id) == host)
        if pending:
            expected = probe_path(root, audit_id, host, 443)
            deadline = time.monotonic() + _NETWORK_REPORT_OPEN_BUDGET_SECONDS
            while time.monotonic() < deadline:
                if expected.is_file() and catalog_report_is_fresh(
                        audit_id=audit_id, workspace=workspace):
                    return "READY"
                time.sleep(0.5)
            # Keep the rest of the reports usable if network is unavailable.
            if not expected.is_file():
                return "PENDING_OR_UNAVAILABLE"

        # Only persisted, integrity-checked probes may trigger a read-only
        # projection. The active worker remains the sole network collector.
        if read_authorized_probes(root, audit_id):
            if catalog_report_is_fresh(audit_id=audit_id, workspace=workspace):
                return "READY"
            # Do not compete with a recent worker still staging its tree.
            if not recent:
                from rasai.report_completion import materialize_catalog_report_projection
                result = materialize_catalog_report_projection(
                    audit_id=audit_id, workspace=workspace, read_only=True)
                if not result.renderer_errors and catalog_report_is_fresh(
                        audit_id=audit_id, workspace=workspace):
                    return "READY"
            return "PROJECTION_INCOMPLETE"
    except (OSError, ValueError, TypeError, RuntimeError):
        return "CHECK_UNAVAILABLE"
    return "NOT_APPLICABLE"


def open_external_path(path: Path) -> tuple[bool, str]:
    """Open a file/folder with the operating system's default handler."""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return False, f"caminho não existe: {resolved}"
    network_state = _synchronize_network_report_before_open(resolved)
    if network_state == "PENDING_OR_UNAVAILABLE":
        print("Rede complementar ainda não disponível; o relatório técnico principal permanece acessível.")
    elif network_state in {"PROJECTION_INCOMPLETE", "CHECK_UNAVAILABLE"}:
        print("Rede complementar: não foi possível confirmar a atualização final do HTML.")
    try:
        if os.name == "nt":
            os.startfile(str(resolved))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except (OSError, AttributeError) as exc:
        return False, f"não foi possível abrir {resolved}: {exc}"
    return True, str(resolved)


def open_audit_folder(state: State) -> tuple[bool, str]:
    workspace = audit_workspace(state)
    if workspace is None:
        return False, "nenhuma pasta da auditoria atual está disponível"
    return open_external_path(workspace)


def open_report(state: State) -> tuple[bool, str]:
    workspace = audit_workspace(state)
    report = report_entrypoint(workspace)
    if report is None:
        if workspace is None:
            return False, "nenhuma auditoria concluída está disponível nesta sessão"
        return False, f"entrypoint HTML não encontrado em {workspace}"
    return open_external_path(report)


def artifact_status(state: State) -> tuple[Path | None, Path | None]:
    workspace = audit_workspace(state)
    return workspace, report_entrypoint(workspace)