from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from rasai import catalog_report_site as site
from rasai.catalog_report_evidence import _artifact_path
from rasai.catalog_report_final_refinements import _source_quality_context_html
from rasai.catalog_report_search_trust import _observability
from rasai.catalog_source_dependencies import (
    begin_source_dependency_capture,
    captured_source_dependencies,
    end_source_dependency_capture,
    record_source_dependency,
    verify_source_dependencies,
)


AUDIT_ID = "AUD-246"


def _database(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    database = root / "audit.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE marker(value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('stable')")
        connection.commit()
    finally:
        connection.close()
    return database


def _capture(root: Path, *paths: Path) -> tuple[dict[str, object], ...]:
    token = begin_source_dependency_capture(root)
    try:
        for path in paths:
            record_source_dependency(path)
        return captured_source_dependencies()
    finally:
        end_source_dependency_capture(token)


def _write_manifest(root: Path, database: Path, dependencies: tuple[dict[str, object], ...]) -> None:
    report = root / "report-catalog"
    report.mkdir(parents=True, exist_ok=True)
    (report / "manifest.json").write_text(
        json.dumps(
            {
                "audit_id": AUDIT_ID,
                "freshness": "FINAL",
                "source_fingerprint": site._source_fingerprint(database),
                "source_dependencies": list(dependencies),
                "audit_snapshot": {
                    "source_logical_sha256": site._sqlite_logical_digest(database),
                },
            }
        ),
        encoding="utf-8",
    )


def test_consumed_external_artifact_change_invalidates_freshness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / AUDIT_ID
    database = _database(root)
    artifact = root / "artifacts" / "source-quality.json"
    artifact.parent.mkdir()
    artifact.write_text('{"version":1}', encoding="utf-8")
    dependencies = _capture(root, artifact)
    _write_manifest(root, database, dependencies)
    monkeypatch.setattr(site, "verify_catalog_report_package", lambda _root: (True, ()))

    workspace = SimpleNamespace(root=root, database=database)
    assert site.catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace) is True

    artifact.write_text('{"version":2}', encoding="utf-8")
    assert site.catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace) is False


def test_unconsumed_artifact_change_does_not_invalidate_freshness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / AUDIT_ID
    database = _database(root)
    consumed = root / "artifacts" / "consumed.json"
    ignored = root / "artifacts" / "not-consumed.json"
    consumed.parent.mkdir()
    consumed.write_text("stable", encoding="utf-8")
    ignored.write_text("v1", encoding="utf-8")
    dependencies = _capture(root, consumed)
    _write_manifest(root, database, dependencies)
    monkeypatch.setattr(site, "verify_catalog_report_package", lambda _root: (True, ()))

    workspace = SimpleNamespace(root=root, database=database)
    ignored.write_text("v2", encoding="utf-8")
    assert site.catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace) is True


def test_consulted_missing_source_becoming_present_invalidates_freshness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / AUDIT_ID
    database = _database(root)
    missing = root / "artifacts" / "source-quality-ai.json"
    dependencies = _capture(root, missing)
    assert dependencies == (
        {"path": "artifacts/source-quality-ai.json", "state": "MISSING"},
    )
    _write_manifest(root, database, dependencies)
    monkeypatch.setattr(site, "verify_catalog_report_package", lambda _root: (True, ()))

    workspace = SimpleNamespace(root=root, database=database)
    assert site.catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace) is True
    missing.parent.mkdir(exist_ok=True)
    missing.write_text("{}", encoding="utf-8")
    assert site.catalog_report_is_fresh(audit_id=AUDIT_ID, workspace=workspace) is False


def test_source_quality_projection_records_present_and_optional_missing_sources(tmp_path: Path) -> None:
    root = tmp_path / AUDIT_ID
    database = _database(root)
    artifact = root / "artifacts" / "source-quality.json"
    artifact.parent.mkdir()
    artifact.write_text(
        json.dumps(
            {
                "issues": [
                    {
                        "requested_url": "https://example.test/",
                        "final_url": "https://example.test/",
                        "classification": "REDIRECT_CHAIN",
                        "severity": "LOW",
                        "deterministic_summary": "Cadeia observada.",
                        "redirects": [],
                        "recommended_actions": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    token = begin_source_dependency_capture(root)
    try:
        html = _source_quality_context_html(database)
        records = captured_source_dependencies()
    finally:
        end_source_dependency_capture(token)

    assert "Cadeia observada" in html
    by_path = {str(row["path"]): row for row in records}
    assert by_path["artifacts/source-quality.json"]["state"] == "PRESENT"
    assert by_path["artifacts/source-quality-ai.json"]["state"] == "MISSING"


def test_visual_reference_and_observability_probe_are_tracked(tmp_path: Path) -> None:
    root = tmp_path / AUDIT_ID
    database = _database(root)
    visual = root / "artifacts" / "visual" / "shot.png"
    visual.parent.mkdir(parents=True)
    visual.write_bytes(b"png")

    token = begin_source_dependency_capture(root)
    try:
        assert _artifact_path(root, "artifacts/visual/shot.png") == visual.resolve()
        datasets, connection = _observability(database)
        if connection is not None:
            connection.close()
        records = captured_source_dependencies()
    finally:
        end_source_dependency_capture(token)

    assert datasets == []
    by_path = {str(row["path"]): row for row in records}
    assert by_path["artifacts/visual/shot.png"]["state"] == "PRESENT"
    assert any(
        row["state"] == "MISSING" and "observability" in str(row["path"]).casefold()
        for row in records
    )


def test_dependency_verifier_rejects_path_escape(tmp_path: Path) -> None:
    ok, errors = verify_source_dependencies(
        tmp_path,
        [{"path": "../outside.json", "state": "MISSING"}],
    )
    assert ok is False
    assert errors
