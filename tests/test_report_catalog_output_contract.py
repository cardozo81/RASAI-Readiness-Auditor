from __future__ import annotations

from pathlib import Path

from rasai.persistence import AuditWorkspace
from rasai import report_completion


def test_data_finalization_does_not_create_non_catalog_html(tmp_path: Path) -> None:
    workspace = AuditWorkspace.create(tmp_path, "AUD-CATALOG-ONLY")

    result = report_completion.finalize_audit_report_site(
        audit_id="AUD-CATALOG-ONLY",
        workspace=workspace,
    )

    assert result.complete is True
    assert result.expected_pages == ()
    assert result.generated_pages == ()
    assert not (workspace.root / "report").exists()
    assert not (workspace.root / "report.html").exists()
    assert not (workspace.root / "remediation.html").exists()


def test_catalog_projection_is_separate_from_data_finalization(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = AuditWorkspace.create(tmp_path, "AUD-CATALOG-SEPARATION")
    calls: list[str] = []

    from rasai import catalog_report_site

    def materialize(*, audit_id: str, workspace: AuditWorkspace):
        calls.append(f"materialize:{audit_id}")
        root = workspace.root / "report-catalog"
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text("catalog", encoding="utf-8")
        return root / "index.html"

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", materialize)
    monkeypatch.setattr(catalog_report_site, "catalog_report_is_fresh", lambda **_: True)

    data_result = report_completion.finalize_audit_report_site(
        audit_id="AUD-CATALOG-SEPARATION",
        workspace=workspace,
    )
    assert calls == []
    assert not (workspace.root / "report-catalog").exists()

    catalog_result = report_completion.materialize_catalog_report_projection(
        audit_id="AUD-CATALOG-SEPARATION",
        workspace=workspace,
    )

    assert data_result.renderer_errors == ()
    assert catalog_result.renderer_errors == ()
    assert calls == ["materialize:AUD-CATALOG-SEPARATION"]
    assert (workspace.root / "report-catalog" / "index.html").is_file()
    assert not (workspace.root / "report").exists()
