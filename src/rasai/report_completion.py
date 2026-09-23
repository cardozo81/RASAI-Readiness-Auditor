"""Catalog-only audit finalization boundary.

Late functional finalizers persist audit data through ``finalize_audit_report_site``.
The supported HTML projection is materialized separately in ``report-catalog/`` after
those data finalizers complete. No ``<AUD>/report/`` projection is part of this contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from rasai.persistence import AuditWorkspace


# No non-catalog AUD HTML pages are part of the current output contract.
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
    """Return the non-catalog AUD HTML surface set, which is empty by contract."""
    del audit_id, workspace
    return ()


def inspect_audit_report_site(*, audit_id: str, workspace: AuditWorkspace) -> AuditReportCompletion:
    """Inspect the non-catalog AUD HTML surface set, which is empty by contract."""
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
    """Run composed late data finalizers without materializing HTML.

    The base implementation is intentionally a no-op. Composed runtime finalizers may
    persist required audit data; ``report-catalog/`` is materialized afterwards through
    the separate catalog projection boundary.
    """
    del audit_id, workspace, context_interpretations, routing_snapshot
    return AuditReportCompletion((), (), ())


# Stable reference to the catalog-only base boundary before runtime installers
# compose late data finalizers around finalize_audit_report_site.
_BASE_FINALIZE_AUDIT_REPORT_SITE = finalize_audit_report_site


def materialize_catalog_report_projection(
    *,
    audit_id: str,
    workspace: AuditWorkspace,
) -> AuditReportCompletion:
    """Materialize and verify only the supported ``report-catalog/`` projection."""
    from rasai.catalog_report_site import catalog_report_is_fresh, materialize_catalog_report_site

    errors: list[str] = []
    try:
        materialize_catalog_report_site(audit_id=audit_id, workspace=workspace)
    except Exception as exc:
        errors.append(f"catalog-report:{type(exc).__name__}:{str(exc)[:240]}")

    if not errors:
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
