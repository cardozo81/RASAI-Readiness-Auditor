"""Isolated regression of the supported report-only path (#141).

No collector, provider, network request, scoring or reprocessing is exercised.
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sqlite3
from types import SimpleNamespace

import pytest

from rasai import report_rematerialization as remat
from rasai import catalog_report_site as site


AUD = "AUD-141-ISOLATED"


def _source(tmp_path: Path) -> Path:
    root = tmp_path / "original" / AUD
    (root / "artifacts").mkdir(parents=True)
    connection = sqlite3.connect(root / "audit.db")
    connection.executescript(
        """
        CREATE TABLE audits(audit_id TEXT, status TEXT, completion_status TEXT);
        CREATE TABLE audit_fulfillment_contracts(
            audit_id TEXT, processing_status TEXT, score_status TEXT,
            report_status TEXT, consolidation_eligible INTEGER
        );
        INSERT INTO audits VALUES ('AUD-141-ISOLATED','COMPLETED','COMPLETE_WITH_LIMITATIONS');
        INSERT INTO audit_fulfillment_contracts VALUES (
            'AUD-141-ISOLATED','PARTIAL_RETRYABLE','PENDING','PRELIMINARY',0
        );
        """
    )
    connection.commit()
    connection.close()
    (root / "artifacts" / "evidence.txt").write_text("untouched", encoding="utf-8")
    (root / "report-catalog").mkdir()
    (root / "report-catalog" / "index.html").write_text("historical", encoding="utf-8")
    return root


def _stub_canonical(monkeypatch, *, freshness: str) -> list[str]:
    from rasai import entrypoint, report_completion

    calls: list[str] = []
    monkeypatch.setattr(entrypoint, "_install_audit_runtime", lambda: calls.append("install"))
    monkeypatch.setattr(remat, "_check_composition", lambda: calls.append("composed"))
    monkeypatch.setattr(site, "verify_catalog_report_package", lambda root: (True, ()))

    def fake_projection(*, audit_id, workspace):
        calls.append("project")
        assert audit_id == AUD
        report = workspace.root / "report-catalog"
        (report / "index.html").write_text("new canonical report", encoding="utf-8")
        manifest = {
            "freshness": freshness,
            "audit_id": audit_id,
            "source_fingerprint": site._source_fingerprint(workspace.database),
            "source_dependencies": [],
            "audit_snapshot": {
                "source_logical_sha256": site._sqlite_logical_digest(workspace.database),
            },
        }
        (report / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8",
        )
        # Report projection cannot initiate live collectors.
        with pytest.raises(RuntimeError, match="Coleta/rede proibida"):
            socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        return SimpleNamespace(renderer_errors=())

    monkeypatch.setattr(
        report_completion, "materialize_catalog_report_projection", fake_projection,
    )
    return calls


def test_isolated_rematerialization_preserves_source_and_partial_finality(
    tmp_path: Path, monkeypatch,
) -> None:
    root = _source(tmp_path)
    calls = _stub_canonical(monkeypatch, freshness="PRELIMINARY")
    before = remat._input_files(root)
    entry = remat.rematerialize(
        audit_dir=root, output_root=tmp_path / "new-reports",
    )
    assert calls == ["install", "composed", "project"]
    assert entry.read_text(encoding="utf-8") == "new canonical report"
    assert (root / "report-catalog" / "index.html").read_text() == "historical"
    assert before == remat._input_files(root)
    assert before == remat._input_files(entry.parent.parent)
    assert json.loads((entry.parent / "manifest.json").read_text())["freshness"] == "PRELIMINARY"


def test_rejects_false_final_and_does_not_publish_or_modify_original(
    tmp_path: Path, monkeypatch,
) -> None:
    root = _source(tmp_path)
    _stub_canonical(monkeypatch, freshness="FINAL")
    before = remat._input_files(root)
    output = tmp_path / "new-reports"
    with pytest.raises(RuntimeError, match="Estado publicado diverge"):
        remat.rematerialize(audit_dir=root, output_root=output)
    assert not (output / AUD).exists()
    assert before == remat._input_files(root)


def test_rejects_output_inside_audit_and_rejects_existing_destination(
    tmp_path: Path, monkeypatch,
) -> None:
    root = _source(tmp_path)
    with pytest.raises(ValueError, match="Saida nao pode"):
        remat.rematerialize(audit_dir=root, output_root=root / "reports")
    output = tmp_path / "new-reports"
    (output / AUD).mkdir(parents=True)
    with pytest.raises(FileExistsError, match="Saida ja existe"):
        remat.rematerialize(audit_dir=root, output_root=output)


def test_canonical_runtime_installation_binds_the_report_renderers() -> None:
    """Only installs entrypoint hooks; no audit/reprocess or I/O is run."""
    from rasai.entrypoint import _install_audit_runtime

    _install_audit_runtime()
    remat._check_composition()
