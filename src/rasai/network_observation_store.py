"""Immutable, idempotent network observation sidecar; never touches audit.db."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from rasai.network_observation import snapshots_from_audit, CONTRACT

_SAFETY_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FILE = "network-observations.json"


def sidecar_path(workspace: str | Path) -> Path:
    return Path(workspace) / "artifacts" / "network" / _FILE


def persist_network_observations(workspace: str | Path, audit_id: str) -> Path | None:
    """First write is authoritative; differing future input is a hard conflict.

    No network calls, no modification of sealed AUD, and no silent recapture.
    """
    if not _SAFETY_ID.fullmatch(audit_id):
        raise ValueError("Identificador de auditoria inválido")
    root = Path(workspace)
    if root.is_symlink():
        raise ValueError("Workspace simbólico não permitido")
    db = root / "audit.db"
    if not db.is_file() or db.is_symlink():
        return None
    snapshots = snapshots_from_audit(db, audit_id)
    if not snapshots:
        return None
    dest = sidecar_path(root)
    payload = {"contract": CONTRACT, "audit_id": audit_id, "observations": snapshots}
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2,
                            allow_nan=False) + "\n"
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink() or not dest.is_file():
            raise ValueError("Pacote de rede inválido")
        if dest.read_text(encoding="utf-8") != serialized:
            raise ValueError("Conflito de proveniência: pacote de rede já persistido")
        return dest
    parent = dest.parent
    if parent.is_symlink() or (root / "artifacts").is_symlink():
        raise ValueError("Diretório simbólico não permitido")
    parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create avoids racing with another writer and never overwrites.
    with dest.open("x", encoding="utf-8", newline="\n") as target:
        target.write(serialized)
        target.flush()
        os.fsync(target.fileno())
    return dest


def read_network_observations(workspace: str | Path, audit_id: str) -> list[dict[str, Any]]:
    if not _SAFETY_ID.fullmatch(audit_id):
        return []
    path = sidecar_path(workspace)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 2_000_000:
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return []
    if data.get("contract") != CONTRACT or data.get("audit_id") != audit_id:
        return []
    observations = data.get("observations")
    if not isinstance(observations, list) or len(observations) > 100:
        return []
    return observations
