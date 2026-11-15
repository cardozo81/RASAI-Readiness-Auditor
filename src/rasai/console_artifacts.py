"""Navigation helpers for artifacts produced by the optional interactive console."""
from __future__ import annotations

import os
import sqlite3
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


def presentation_report_entrypoint(workspace: Path | None) -> Path | None:
    """Inspect the verified presentation available to this audit. Navigation never migrates files."""
    package = _presentation_package(workspace)
    return package[0] if package else None


def _presentation_package(workspace: Path | None) -> tuple[Path, bool] | None:
    from rasai.parallel_report import __version__
    from rasai.parallel_report.artifact_reader import DIRECTORY, confined, inventory
    from rasai.parallel_report.publication import find_package, historical_directories
    from rasai.parallel_report.sqlite_reader import quiescent

    if workspace is None:
        return None
    base = workspace / DIRECTORY
    if not base.is_dir():
        return None
    try:
        from rasai.catalog_report_site import _sqlite_logical_digest
        database = confined(workspace, "audit.db")
        quiescent(database)
        historical = historical_directories(base)
        package = find_package(base, historical, inventory(workspace),
                               _sqlite_logical_digest(database), historical_version=True)
    except (OSError, ValueError, sqlite3.Error):
        return None
    if package is None:
        return None
    directory, manifest = package
    migrate = bool(historical) or manifest["generator_version"] != __version__
    return (directory / "index.html").resolve(), migrate


def materialize_presentation_report_on_demand(
    workspace: Path | None,
) -> tuple[Path | None, str]:
    """Resolve the canonical presentation, publishing only on explicit open."""
    if workspace is None:
        return None, "workspace da auditoria indisponível"
    package = _presentation_package(workspace)
    if package is not None:
        existing, migrate = package
        if not migrate:
            return existing, "EXISTING"
        from rasai.parallel_report.generator import generate
        try:
            # This also migrates dated trees and upgrades older renderers.
            # The generator reuses a valid canonical package in place.
            return generate(workspace) / "index.html", "MIGRATED"
        except Exception as exc:
            return None, f"publicação da apresentação falhou ({type(exc).__name__})"
    if report_entrypoint(workspace) is None:
        return None, "relatório canônico ausente ou inválido"
    database = workspace / "audit.db"
    if not database.is_file() or database.is_symlink():
        return None, "audit.db ausente ou inseguro"
    try:
        from rasai.catalog_report_site import (
            _sqlite_logical_digest,
            catalog_report_is_fresh,
        )
        from rasai.persistence import AuditWorkspace

        canonical_workspace = AuditWorkspace.open(workspace)
        logical_before = _sqlite_logical_digest(database)
        canonical_fresh = catalog_report_is_fresh(
            audit_id=workspace.name,
            workspace=canonical_workspace,
        )
        if not canonical_fresh:
            from rasai import entrypoint
            from rasai.report_completion import materialize_catalog_report_projection
            from rasai.report_rematerialization import _check_composition, _forbid_network

            entrypoint._install_audit_runtime()
            _check_composition()
            with _forbid_network():
                replay = materialize_catalog_report_projection(
                    audit_id=workspace.name,
                    workspace=canonical_workspace,
                    read_only=True,
                )
            logical_after_replay = _sqlite_logical_digest(database)
            if logical_after_replay != logical_before:
                return None, "rematerialização read-only alterou o audit.db"
            if replay.renderer_errors:
                return None, "não foi possível rematerializar o relatório canônico em modo read-only"
            if not catalog_report_is_fresh(
                audit_id=workspace.name,
                workspace=canonical_workspace,
            ):
                return None, "relatório canônico permaneceu desatualizado após rematerialização read-only"

        from rasai.parallel_report.generator import generate

        generate(workspace)
        logical_after_generation = _sqlite_logical_digest(database)
        if logical_after_generation != logical_before:
            return None, "geração da apresentação alterou o audit.db"
    except Exception as exc:
        return None, f"geração da apresentação falhou ({type(exc).__name__})"
    generated = presentation_report_entrypoint(workspace)
    if generated is None:
        return None, "apresentação gerada não passou no gate de integridade/freshness"
    return generated, "MATERIALIZED"


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


def open_presentation_report(state: State) -> tuple[bool, str]:
    return open_workspace_presentation(audit_workspace(state))


def open_workspace_presentation(workspace: Path | None) -> tuple[bool, str]:
    report, detail = materialize_presentation_report_on_demand(workspace)
    if report is None:
        return False, detail
    return open_external_path(report)


def artifact_status(state: State) -> tuple[Path | None, Path | None]:
    workspace = audit_workspace(state)
    return workspace, report_entrypoint(workspace)