from __future__ import annotations

from pathlib import Path

from rasai.persistence import AuditWorkspace
from rasai import report_completion



def _base_finalizer():
    return report_completion._BASE_FINALIZE_AUDIT_REPORT_SITE


def test_data_finalization_does_not_create_non_catalog_html(tmp_path: Path) -> None:
    workspace = AuditWorkspace.create(tmp_path, "AUD-CATALOG-ONLY")

    result = _base_finalizer()(
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
    from rasai.parallel_report import generator as parallel_generator
    monkeypatch.setattr(
        parallel_generator,
        "generate",
        lambda root: calls.append("presentation") or (Path(root) / "report-presentation"),
    )

    data_result = _base_finalizer()(
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
    assert calls == ["materialize:AUD-CATALOG-SEPARATION", "presentation"]
    assert (workspace.root / "report-catalog" / "index.html").is_file()
    assert not (workspace.root / "report").exists()


def test_read_only_catalog_projection_does_not_generate_presentation_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = AuditWorkspace.create(tmp_path, "AUD-READ-ONLY-PROJECTION")
    calls: list[str] = []

    from rasai import catalog_report_site
    from rasai.parallel_report import generator as parallel_generator

    def materialize(*, audit_id: str, workspace: AuditWorkspace):
        root = workspace.root / "report-catalog"
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text("catalog", encoding="utf-8")

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", materialize)
    monkeypatch.setattr(catalog_report_site, "catalog_report_is_fresh", lambda **_: True)
    monkeypatch.setattr(parallel_generator, "generate", lambda root: calls.append("presentation"))

    result = report_completion.materialize_catalog_report_projection(
        audit_id="AUD-READ-ONLY-PROJECTION",
        workspace=workspace,
        read_only=True,
    )

    assert result.renderer_errors == ()
    assert calls == []
