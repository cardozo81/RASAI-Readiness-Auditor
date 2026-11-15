"""Final execution-boundary projection for the pre-production report contract.

The catalog report is rebuilt only after the complete console wrapper chain returns,
so late fulfillment/cost persistence is already committed before a report is marked
FINAL. M25 sample timestamps are owned directly by the canonical measurement model.
"""
from __future__ import annotations

import json
from pathlib import Path
from time import sleep
from typing import Any


def _verified_preliminary_projection(workspace: Any) -> bool:
    """Accept an incomplete AUD projection only when its package is self-consistent."""
    from rasai.catalog_report_site import CATALOG_REPORT_DIR, verify_catalog_report_package

    report_dir = Path(workspace.root) / CATALOG_REPORT_DIR
    manifest_path = report_dir / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if str(manifest.get("freshness") or "").upper() != "PRELIMINARY":
        return False
    valid, _errors = verify_catalog_report_package(report_dir)
    return bool(valid)


def _is_transient_probe_dependency_drift(error: RuntimeError) -> bool:
    """Only retry a concurrent change to the network-probe directory.

    A changed source is never promoted: the catalog builder rejects the
    candidate and the next attempt reads and validates a fresh projection.
    """
    message = str(error)
    if message == (
        "catalog source dependency changed during materialization: "
        "artifacts/network/probes"
    ):
        return True
    return message in {
        "catalog report source dependency changed during materialization: "
        "source_dependency divergente: artifacts/network/probes",
        "catalog report source dependency changed before promotion: "
        "source_dependency divergente: artifacts/network/probes",
    }


def finalize_catalog_projection(state: Any) -> Path | None:
    """Rebuild report-catalog after every late persistence owner has returned."""
    audit_id = str(getattr(state, "audit_id", "") or "").strip()
    if not audit_id:
        return None
    if str(getattr(state, "operation", "") or "").upper() in {
        "LOCAL:COST_DECLINED",
        "LOCAL:AI_CONFIGURATION",
    }:
        return None

    from rasai.catalog_report_site import catalog_report_is_fresh, materialize_catalog_report_site
    from rasai.console_artifacts import artifact_status
    from rasai.persistence import AuditWorkspace

    root, _artifact = artifact_status(state)
    if root is None:
        return None
    workspace = AuditWorkspace(Path(root))
    if not workspace.database.is_file():
        return None

    # An authorized probe may be sealed concurrently with the final HTML
    # projection. Retry only that verified sidecar race; never weaken the
    # source-dependency or package-integrity gates.
    for attempt in range(3):
        try:
            path = materialize_catalog_report_site(audit_id=audit_id, workspace=workspace)
            break
        except RuntimeError as error:
            if attempt == 2 or not _is_transient_probe_dependency_drift(error):
                raise
            sleep(0.25 * (attempt + 1))
    if not catalog_report_is_fresh(audit_id=audit_id, workspace=workspace):
        if not _verified_preliminary_projection(workspace):
            raise RuntimeError(
                "report-catalog não permaneceu aderente ao audit.db após a finalização da execução"
            )
    return path


def finalize_after_console_run(state: Any, code: int) -> int:
    """Final execution boundary used by the outermost AI configuration wrapper."""
    finalize_catalog_projection(state)
    return int(code)


__all__ = [
    "finalize_after_console_run",
    "finalize_catalog_projection",
]
