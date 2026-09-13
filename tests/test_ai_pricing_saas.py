from __future__ import annotations

from pathlib import Path
import tomllib

from rasai.ai_pricing_catalog import load_pricing_catalog
from rasai.ai_pricing_saas import (
    build_pricing_job_snapshot,
    materialize_pricing_job_snapshot,
    pricing_worker_environment,
)

ROOT = Path(__file__).resolve().parents[1]


def _factory_document() -> dict:
    path = ROOT / "src" / "rasai" / "config" / "ai-pricing-defaults.toml"
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_saas_snapshot_round_trip_uses_same_catalog_contract(tmp_path: Path) -> None:
    snapshot = build_pricing_job_snapshot(_factory_document())
    assert snapshot.catalog_version == "RASAI-PRICING-2026-09-13"
    assert snapshot.reference_date == "2026-09-13"
    assert len(snapshot.sha256) == 64

    path = materialize_pricing_job_snapshot(snapshot, tmp_path, job_id="JOB-123")
    loaded = load_pricing_catalog(path=path)

    assert loaded.metadata.catalog_version == snapshot.catalog_version
    assert loaded.metadata.reference_date == snapshot.reference_date
    assert loaded.catalog_models() == load_pricing_catalog(
        path=ROOT / "src" / "rasai" / "config" / "ai-pricing-defaults.toml"
    ).catalog_models()

    env = pricing_worker_environment(path)
    assert env["RASAI_AI_PRICING_SOURCE"] == "file"
    assert env["RASAI_AI_PRICING_FILE"] == str(path.resolve())


def test_same_job_snapshot_is_idempotent(tmp_path: Path) -> None:
    snapshot = build_pricing_job_snapshot(_factory_document())
    first = materialize_pricing_job_snapshot(snapshot, tmp_path, job_id="JOB/unsafe")
    second = materialize_pricing_job_snapshot(snapshot, tmp_path, job_id="JOB/unsafe")
    assert first == second
    assert "JOB_unsafe" in first.name
    assert first.read_text(encoding="utf-8") == snapshot.toml
