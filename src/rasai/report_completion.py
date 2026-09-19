"""Final materialization gate for audit-owned catalog HTML.

The conventional <AUD>/report/ mini-site was retired. This module keeps the
historical finalizer API so runtime composition and reprocessing can continue to
materialize and verify report-catalog/ without creating any non-catalog HTML.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from rasai.persistence import AuditWorkspace


# Compatibility surface for callers that previously extended the conventional report
# contract. No conventional AUD HTML pages are expected or generated anymore.
AUDIT_ALWAYS_PAGES: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuditReportCompletion:
    expected_pages: tuple[str, ...]
    generated_pages: tuple[str, ...]
    missing_pages: tuple[str, ...]
    renderer_errors: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing_pages


def expected_audit_report_pages(*, audit_id: str, workspace: AuditWorkspace) -> tuple[str, ...]:
    """Return the retired conventional AUD HTML surface set (always empty)."""
    del audit_id, workspace
    return ()


def inspect_audit_report_site(*, audit_id: str, workspace: AuditWorkspace) -> AuditReportCompletion:
    """Compatibility inspection for the retired conventional AUD report family."""
    del audit_id, workspace
    return AuditReportCompletion((), (), ())


def _verified_preliminary_catalog(workspace: AuditWorkspace) -> bool:
    """Return True only for a self-consistent non-final catalog projection."""
    from rasai.catalog_report_site import CATALOG_REPORT_DIR, verify_catalog_report_package

    root = workspace.root / CATALOG_REPORT_DIR
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if str(manifest.get("freshness") or "").upper() != "PRELIMINARY":
        return False
    valid, _errors = verify_catalog_report_package(root)
    return bool(valid)


def finalize_audit_report_site(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
    context_interpretations: Sequence[Any] = (),
    routing_snapshot: Mapping[str, Any] | None = None,
) -> AuditReportCompletion:
    """Materialize only the supported catalog report projection.

    context_interpretations and routing_snapshot remain accepted for runtime
    compatibility; they belonged to the removed conventional HTML projection and are
    intentionally ignored here. Catalog generation continues to read the canonical
    persisted audit state exactly as before.
    """
    del context_interpretations, routing_snapshot

    from rasai.catalog_report_site import catalog_report_is_fresh, materialize_catalog_report_site

    errors: list[str] = []
    try:
        materialize_catalog_report_site(audit_id=audit_id, workspace=workspace)
    except Exception as exc:
        errors.append(f"catalog-report:{type(exc).__name__}:{str(exc)[:240]}")

    if not any(error.startswith("catalog-report:") for error in errors):
        try:
            fresh = catalog_report_is_fresh(audit_id=audit_id, workspace=workspace)
        except Exception as exc:
            errors.append(f"catalog-report-freshness:{type(exc).__name__}:{str(exc)[:240]}")
        else:
            if not fresh and not _verified_preliminary_catalog(workspace):
                errors.append(
                    "catalog-report-freshness:RuntimeError:published catalog report does not match persisted audit"
                )

    return AuditReportCompletion(
        expected_pages=(),
        generated_pages=(),
        missing_pages=(),
        renderer_errors=tuple(errors),
    )
