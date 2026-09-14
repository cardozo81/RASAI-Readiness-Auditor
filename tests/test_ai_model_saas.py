from __future__ import annotations

from pathlib import Path
import tomllib

from rasai.ai_model_catalog import load_factory_model_catalog
from rasai.ai_model_saas import (
    build_model_job_snapshot,
    materialize_model_job_snapshot,
    model_catalog_to_toml,
    model_worker_environment,
)

ROOT = Path(__file__).resolve().parents[1]


def _factory_document() -> dict:
    path = ROOT / "src" / "rasai" / "config" / "ai-models-defaults.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_model_snapshot_is_deterministic_and_reloads_same_catalog() -> None:
    first = build_model_job_snapshot(_factory_document())
    second = build_model_job_snapshot(_factory_document())
    assert first.sha256 == second.sha256
    assert first.toml == second.toml
    rendered = tomllib.loads(first.toml)
    assert rendered["metadata"]["catalog_version"] == "RASAI-MODELS-2026-09-14"
    assert len(rendered["models"]) == len(load_factory_model_catalog().models)


def test_model_snapshot_materialization_is_job_scoped(tmp_path: Path) -> None:
    snapshot = build_model_job_snapshot(_factory_document())
    path = materialize_model_job_snapshot(snapshot, tmp_path, job_id="job/123")
    assert path.is_file()
    assert path.name.startswith("ai-models-job_123-")
    assert path.read_text(encoding="utf-8") == snapshot.toml
    assert materialize_model_job_snapshot(snapshot, tmp_path, job_id="job/123") == path
    env = model_worker_environment(path)
    assert env["RASAI_AI_MODELS_SOURCE"] == "file"
    assert env["RASAI_AI_MODELS_FILE"] == str(path.resolve())


def test_factory_catalog_round_trips_through_snapshot_toml() -> None:
    catalog = load_factory_model_catalog()
    text = model_catalog_to_toml(catalog)
    document = tomllib.loads(text)
    assert document["metadata"]["schema_version"] == 1
    by_key = {(item["provider"], item["model"]): item for item in document["models"]}
    assert by_key[("OPENAI", "gpt-5.6-luna")]["public_default"] is True
    assert by_key[("COPILOT", "auto")]["auto_eligible"] is False
