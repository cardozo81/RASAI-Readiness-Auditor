"""Navigation helpers for artifacts produced by the optional interactive console."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from rasai.console_config import State


def audit_workspace(state: State) -> Path | None:
    """Resolve only the workspace belonging to the audit held by this console state."""
    audit_id = state.audit_id.strip()
    if not audit_id or not audit_id.startswith("AUD-"):
        return None
    candidate = Path(state.audits_root).expanduser() / audit_id
    return candidate.resolve() if candidate.is_dir() else None


def report_entrypoint(workspace: Path | None) -> Path | None:
    """Resolve the current report entrypoint with backward-compatible fallbacks."""
    if workspace is None:
        return None
    candidates = (
        workspace / "report" / "index.html",
        workspace / "report.html",
        workspace / "index.html",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def open_external_path(path: Path) -> tuple[bool, str]:
    """Open a file/folder with the operating system's default handler."""
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        return False, f"caminho não existe: {resolved}"
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
