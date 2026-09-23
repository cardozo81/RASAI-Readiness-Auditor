from __future__ import annotations

from types import SimpleNamespace

from rasai.report_completion import (
    AUDIT_ALWAYS_PAGES,
    expected_audit_report_pages,
    inspect_audit_report_site,
)


def test_non_catalog_audit_html_surface_is_empty_by_contract() -> None:
    workspace = SimpleNamespace()
    assert AUDIT_ALWAYS_PAGES == ()
    assert expected_audit_report_pages(audit_id="AUD-1", workspace=workspace) == ()
    inspection = inspect_audit_report_site(audit_id="AUD-1", workspace=workspace)
    assert inspection.expected_pages == ()
    assert inspection.generated_pages == ()
    assert inspection.missing_pages == ()
    assert inspection.complete is True
