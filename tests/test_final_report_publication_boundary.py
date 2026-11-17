"""Focused no-network regression tests for the final report publication boundary."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from rasai import (
    catalog_report_site,
    console_artifacts,
    entrypoint,
    execution_adherence_refinement,
    report_completion,
)
from rasai.parallel_report import artifact_reader, generator


def _fake_catalog_stage(root: Path) -> Path:
    stage = root / ".report-catalog.tmp-test"
    stage.mkdir()
    (stage / "index.html").write_text("verified catalog", encoding="utf-8")
    (stage / "manifest.json").write_text('{"test":true}', encoding="utf-8")
    return stage


def _winerror(code: int) -> PermissionError:
    failure = PermissionError(13, "Access is denied")
    failure.winerror = code
    return failure


@pytest.mark.parametrize("code", [5, 32])
def test_windows_locked_catalog_stage_uses_verified_copy(tmp_path, monkeypatch, code):
    stage = _fake_catalog_stage(tmp_path)
    destination = tmp_path / "report-catalog"
    original = Path.replace
    attempted = []

    def locked_replace(self, target):
        if self == stage:
            attempted.append(code)
            raise _winerror(code)
        return original(self, target)

    monkeypatch.setattr(Path, "replace", locked_replace)
    monkeypatch.setattr(
        catalog_report_site, "verify_catalog_report_package", lambda *_: (True, ())
    )
    monkeypatch.setattr(
        catalog_report_site, "catalog_report_is_fresh", lambda **_: True
    )
    catalog_report_site._promote_verified_catalog_staging(
        staging=stage, report_dir=destination,
        audit_id="AUD-TEST", workspace=SimpleNamespace(root=tmp_path),
    )
    assert attempted == [code]
    assert (destination / "index.html").read_text() == "verified catalog"
    assert (stage / "index.html").is_file()
    assert not (tmp_path / ".report-catalog.tmp-test-ready").exists()


def test_windows_catalog_fallback_rejects_copy_tampering(tmp_path, monkeypatch):
    stage = _fake_catalog_stage(tmp_path)
    destination = tmp_path / "report-catalog"
    original_replace = Path.replace
    original_copy = catalog_report_site.shutil.copytree

    def locked_replace(self, target):
        if self == stage:
            raise _winerror(5)
        return original_replace(self, target)

    def tampered_copy(source, target, *args, **kwargs):
        copied = original_copy(source, target, *args, **kwargs)
        (target / "index.html").write_text("changed", encoding="utf-8")
        return copied

    monkeypatch.setattr(Path, "replace", locked_replace)
    monkeypatch.setattr(catalog_report_site.shutil, "copytree", tampered_copy)
    with pytest.raises(RuntimeError, match="diverged"):
        catalog_report_site._promote_verified_catalog_staging(
            staging=stage, report_dir=destination,
            audit_id="AUD-TEST", workspace=SimpleNamespace(root=tmp_path),
        )
    assert not destination.exists()
    assert (stage / "index.html").read_text() == "verified catalog"


def test_windows_catalog_copy_second_denial_fails_closed(tmp_path, monkeypatch):
    stage = _fake_catalog_stage(tmp_path)
    destination = tmp_path / "report-catalog"
    original = Path.replace

    def locked_replace(self, target):
        if self == stage or self.name.endswith("-ready"):
            raise _winerror(5)
        return original(self, target)

    monkeypatch.setattr(Path, "replace", locked_replace)
    monkeypatch.setattr(
        catalog_report_site, "verify_catalog_report_package", lambda *_: (True, ())
    )
    monkeypatch.setattr(
        catalog_report_site, "catalog_report_is_fresh", lambda **_: True
    )
    with pytest.raises(PermissionError):
        catalog_report_site._promote_verified_catalog_staging(
            staging=stage, report_dir=destination,
            audit_id="AUD-TEST", workspace=SimpleNamespace(root=tmp_path),
        )
    assert not destination.exists()
    assert (stage / "index.html").is_file()


def test_presentation_source_inventory_excludes_catalog_and_its_staging(tmp_path):
    (tmp_path / "audit.db").write_bytes(b"source")
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "page.txt").write_text("evidence")
    for name in ("report-catalog", ".report-catalog.tmp-example", ".report-catalog.stale-example"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "index.html").write_text(name)
    original = artifact_reader.inventory(tmp_path)
    assert set(original) == {"audit.db", "artifacts/page.txt"}
    (tmp_path / "report-catalog" / "index.html").write_text("new derived catalog")
    assert artifact_reader.inventory(tmp_path) == original


def test_final_console_gate_publishes_both_and_classifies_catalog_error(monkeypatch):
    calls = []
    state = SimpleNamespace(
        audit_id="AUD-TEST", audits_root="audits", status="COMPLETE", operation="AUDIT",
        error="",
    )

    def broken_catalog(_state):
        calls.append("catalog")
        raise PermissionError("catalog rename refused")

    def valid_presentation(_state):
        calls.append("presentation")
        return Path("report-presentation/index.html")

    monkeypatch.setattr(
        execution_adherence_refinement, "finalize_catalog_projection", broken_catalog,
    )
    monkeypatch.setattr(
        execution_adherence_refinement, "finalize_presentation_projection", valid_presentation,
    )
    result = execution_adherence_refinement.finalize_after_console_run(state, 0)
    assert result == 3
    assert calls == ["catalog", "presentation"]
    assert state.status == "COMPLETE"
    assert state.operation == "AUDIT"
    assert "report-catalog:PermissionError" in state.error
    assert "IA inválida" not in state.error


def test_cli_postflight_refreshes_stale_catalog_then_presentation(tmp_path, monkeypatch):
    workspace = SimpleNamespace(root=tmp_path)
    state = {"fresh": False}
    calls = []

    def fresh(**_kwargs):
        return state["fresh"]

    def refresh(**kwargs):
        assert kwargs["read_only"] is True
        calls.append("catalog-refresh")
        state["fresh"] = True
        return SimpleNamespace(renderer_errors=())

    def generate_presentation(_root):
        calls.append("presentation")
        return tmp_path / "report-presentation"

    monkeypatch.setattr(
        catalog_report_site, "catalog_report_is_fresh", fresh
    )
    monkeypatch.setattr(
        report_completion, "_verified_preliminary_catalog", lambda _workspace: False
    )
    monkeypatch.setattr(
        report_completion, "materialize_catalog_report_projection", refresh
    )
    monkeypatch.setattr(generator, "generate", generate_presentation)
    monkeypatch.setattr(
        console_artifacts, "presentation_report_entrypoint",
        lambda _root: (tmp_path / "report-presentation" / "index.html").resolve(),
    )
    assert entrypoint._final_report_publication_gate(
        audit_id="AUD-TEST", workspace=workspace,
    ) == ()
    assert calls == ["catalog-refresh", "presentation"]


def test_cli_postflight_attempts_presentation_even_after_catalog_failure(
    tmp_path, monkeypatch,
):
    workspace = SimpleNamespace(root=tmp_path)
    calls = []
    monkeypatch.setattr(
        catalog_report_site, "catalog_report_is_fresh", lambda **_: False
    )
    monkeypatch.setattr(
        report_completion, "_verified_preliminary_catalog", lambda _workspace: False
    )

    def broken_catalog(**_kwargs):
        calls.append("catalog")
        raise PermissionError("catalog publication denied")

    def valid_presentation(_root):
        calls.append("presentation")
        return tmp_path / "report-presentation"

    monkeypatch.setattr(
        report_completion, "materialize_catalog_report_projection", broken_catalog
    )
    monkeypatch.setattr(generator, "generate", valid_presentation)
    monkeypatch.setattr(
        console_artifacts, "presentation_report_entrypoint",
        lambda _root: (tmp_path / "report-presentation" / "index.html").resolve(),
    )
    errors = entrypoint._final_report_publication_gate(
        audit_id="AUD-TEST", workspace=workspace,
    )
    assert calls == ["catalog", "presentation"]
    assert "report-catalog:PermissionError" in errors
    assert not any(error.startswith("report-presentation:") for error in errors)
