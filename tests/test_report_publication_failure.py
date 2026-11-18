"""#715 — synthetic, offline tests for dual-report publication and diagnostics.

This does NOT attribute the historic AUD-CD169 outage to these conditions.
Source evidence is synthetic; no providers, collectors, HTTP or real AUD files.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
import sys
from types import ModuleType

import pytest

from rasai import catalog_report_site, report_completion
from rasai.parallel_report import generator
from rasai.persistence import AuditWorkspace


@pytest.fixture(autouse=True)
def forbid_mutable_advisory_writers(monkeypatch: pytest.MonkeyPatch):
    """Stub optional late writers so the only source mutation is test-controlled."""
    for module_name, operation in (
        ("rasai.network_observation_store", "persist_network_observations"),
        ("rasai.geo_observation", "materialize_geo_observation"),
        ("rasai.geo_extraction_quality", "materialize_extraction_quality"),
    ):
        dummy = ModuleType(module_name)
        setattr(dummy, operation, lambda *args, **kwargs: None)
        monkeypatch.setitem(sys.modules, module_name, dummy)


def _workspace(tmp_path: Path) -> AuditWorkspace:
    return AuditWorkspace.create(tmp_path, "AUD-715-SYNTHETIC")


def test_catalog_and_presentation_both_read_latest_committed_synthetic_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    """A late committed source must be observed by both independent projections."""
    workspace = _workspace(tmp_path)
    with sqlite3.connect(workspace.database) as db:
        db.execute("CREATE TABLE diagnostic_last_writer(marker TEXT NOT NULL)")
        db.execute("INSERT INTO diagnostic_last_writer VALUES ('BEFORE_FINALIZATION')")
    # Simulate the late persistence owner completing before final reporting.
    with sqlite3.connect(workspace.database) as db:
        db.execute("UPDATE diagnostic_last_writer SET marker='AFTER_COMMITTED_FLUSH'")
    sha_before = sha256(workspace.database.read_bytes()).hexdigest()
    called = []

    def persisted_marker() -> str:
        connection = sqlite3.connect(
            f"file:{workspace.database.as_posix()}?mode=ro", uri=True
        )
        try:
            return connection.execute(
                "SELECT marker FROM diagnostic_last_writer"
            ).fetchone()[0]
        finally:
            connection.close()

    def catalog(*, audit_id, workspace):
        value = persisted_marker()
        called.append(("catalog", value))
        target = workspace.root / "report-catalog"
        target.mkdir()
        (target / "index.html").write_text(value, encoding="utf-8")
        return target / "index.html"

    def presentation(root):
        value = persisted_marker()
        called.append(("presentation", value))
        target = Path(root) / "report-presentation"
        target.mkdir()
        (target / "index.html").write_text(value, encoding="utf-8")
        return target

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", catalog)
    monkeypatch.setattr(catalog_report_site, "catalog_report_is_fresh", lambda **_: True)
    monkeypatch.setattr(generator, "generate", presentation)

    receipt = report_completion.materialize_catalog_report_projection(
        audit_id="AUD-715-SYNTHETIC", workspace=workspace,
    )
    assert receipt.renderer_errors == ()
    assert called == [
        ("catalog", "AFTER_COMMITTED_FLUSH"),
        ("presentation", "AFTER_COMMITTED_FLUSH"),
    ]
    assert sha256(workspace.database.read_bytes()).hexdigest() == sha_before


def test_presentation_failure_is_not_silent_success_or_sensitive_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
):
    """Before this fix, RPR receives empty renderer_errors despite no presentation."""
    workspace = _workspace(tmp_path)
    called = []

    def catalog(*, audit_id, workspace):
        called.append("catalog")
        return workspace.root / "report-catalog" / "index.html"

    def inaccessible_presentation(_root):
        called.append("presentation")
        raise PermissionError("private-user-home/secret=NEVER_LOG_THIS")

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", catalog)
    monkeypatch.setattr(catalog_report_site, "catalog_report_is_fresh", lambda **_: True)
    monkeypatch.setattr(generator, "generate", inaccessible_presentation)

    receipt = report_completion.materialize_catalog_report_projection(
        audit_id="AUD-715-SYNTHETIC", workspace=workspace,
    )
    assert called == ["catalog", "presentation"]
    assert receipt.renderer_errors == ("report-presentation:unavailable",)
    assert not (workspace.root / "report-presentation").exists()
    assert "NEVER_LOG_THIS" not in str(receipt.renderer_errors)
    assert "NEVER_LOG_THIS" not in caplog.text
    # Do not conflate derivative report availability with logical audit status:
    assert receipt.missing_pages == ()


def test_two_independent_publication_failures_are_classified_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
):
    workspace = _workspace(tmp_path)
    called = []

    def invalid_catalog(*, audit_id, workspace):
        called.append("catalog")
        raise PermissionError("catalog source unavailable: internal path")

    def invalid_presentation(root):
        called.append("presentation")
        raise OSError("presentation source unavailable: secret")

    monkeypatch.setattr(catalog_report_site, "materialize_catalog_report_site", invalid_catalog)
    monkeypatch.setattr(generator, "generate", invalid_presentation)
    receipt = report_completion.materialize_catalog_report_projection(
        audit_id="AUD-715-SYNTHETIC", workspace=workspace,
    )
    assert called == ["catalog", "presentation"]
    assert len(receipt.renderer_errors) == 2
    assert receipt.renderer_errors[0].startswith("catalog-report:PermissionError:")
    assert receipt.renderer_errors[1] == "report-presentation:unavailable"
    assert all("internal path" not in e and "secret" not in e
               for e in receipt.renderer_errors)
