from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from rasai import external_sari


def test_common_crawl_zero_rows_with_provider_errors_is_retryable(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "artifacts" / "observability" / "common.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text(json.dumps({"errors": ["CC-MAIN:test:RuntimeError"], "observations": []}), encoding="utf-8")
    monkeypatch.setattr(external_sari, "_dataset_row", lambda workspace, dataset_id: {
        "metadata": json.dumps({"rows": 0, "errors": 1}),
        "artifact_path": str(artifact.relative_to(tmp_path)),
    })
    state, errors = external_sari.common_crawl_dataset_health(SimpleNamespace(root=tmp_path), "OBS-TEST", row_count=0)
    assert state == "FAILED_RETRYABLE"
    assert errors == ("CC-MAIN:test:RuntimeError",)


def test_clean_common_crawl_zero_rows_is_no_data(tmp_path: Path, monkeypatch) -> None:
    artifact = tmp_path / "common.json"
    artifact.write_text(json.dumps({"errors": [], "observations": []}), encoding="utf-8")
    monkeypatch.setattr(external_sari, "_dataset_row", lambda workspace, dataset_id: {
        "metadata": json.dumps({"rows": 0, "errors": 0}),
        "artifact_path": str(artifact),
    })
    state, errors = external_sari.common_crawl_dataset_health(SimpleNamespace(root=tmp_path), "OBS-TEST", row_count=0)
    assert state == "NO_DATA"
    assert errors == ()
