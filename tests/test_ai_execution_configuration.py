from __future__ import annotations

from pathlib import Path
import shutil

from rasai.ai_execution_configuration import (
    current_execution_environment,
    execution_ai_configuration,
)
from rasai.ai_model_catalog import MODEL_FILE_ENV, MODEL_SOURCE_ENV, load_model_catalog
from rasai.ai_pricing_catalog import PRICING_FILE_ENV, PRICING_SOURCE_ENV, load_pricing_catalog
from rasai.ai_task_profiles import PROFILE_FILE_ENV, PROFILE_SOURCE_ENV
from rasai.system_defaults import load_system_defaults


ROOT = Path(__file__).resolve().parents[1]


def test_operator_ai_catalogs_exist_and_are_valid() -> None:
    models = load_model_catalog(path=ROOT / "config" / "ai-models.toml")
    pricing = load_pricing_catalog(path=ROOT / "config" / "ai-pricing.toml")
    assert models.catalog_models()
    assert pricing.catalog_models()
    assert (ROOT / "config" / "ai-task-profiles.toml").is_file()


def test_interactive_console_defaults_point_to_root_config() -> None:
    defaults = load_system_defaults()
    environment = dict(defaults.items("environment", raw=True))
    assert environment[MODEL_SOURCE_ENV] == "auto"
    assert environment[MODEL_FILE_ENV] == "config/ai-models.toml"
    assert environment[PRICING_SOURCE_ENV] == "auto"
    assert environment[PRICING_FILE_ENV] == "config/ai-pricing.toml"
    assert environment[PROFILE_SOURCE_ENV] == "auto"
    assert environment[PROFILE_FILE_ENV] == "config/ai-task-profiles.toml"


def test_execution_snapshot_is_immutable_after_operator_file_changes(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    config.mkdir()
    model_file = config / "ai-models.toml"
    pricing_file = config / "ai-pricing.toml"
    profile_file = config / "ai-task-profiles.toml"
    shutil.copyfile(ROOT / "config" / "ai-models.toml", model_file)
    shutil.copyfile(ROOT / "config" / "ai-pricing.toml", pricing_file)
    shutil.copyfile(ROOT / "config" / "ai-task-profiles.toml", profile_file)

    monkeypatch.setenv(MODEL_SOURCE_ENV, "file")
    monkeypatch.setenv(MODEL_FILE_ENV, str(model_file))
    monkeypatch.setenv(PRICING_SOURCE_ENV, "file")
    monkeypatch.setenv(PRICING_FILE_ENV, str(pricing_file))
    monkeypatch.setenv(PROFILE_SOURCE_ENV, "file")
    monkeypatch.setenv(PROFILE_FILE_ENV, str(profile_file))

    snapshot_model: Path | None = None
    with execution_ai_configuration(cwd=tmp_path):
        child = current_execution_environment()
        assert child is not None
        snapshot_model = Path(child[MODEL_FILE_ENV])
        snapshot_pricing = Path(child[PRICING_FILE_ENV])
        snapshot_profile = Path(child[PROFILE_FILE_ENV])
        assert snapshot_model != model_file.resolve()
        assert snapshot_pricing != pricing_file.resolve()
        assert snapshot_profile != profile_file.resolve()
        assert snapshot_model.is_file() and snapshot_pricing.is_file() and snapshot_profile.is_file()

        before = snapshot_model.read_text(encoding="utf-8")
        model_file.write_text("# changed after execution start\n", encoding="utf-8")
        assert snapshot_model.read_text(encoding="utf-8") == before
        assert load_model_catalog(env=child, cwd=tmp_path).catalog_models()

    assert current_execution_environment() is None
    assert snapshot_model is not None and not snapshot_model.exists()


def test_next_execution_reloads_saved_operator_pricing_without_console_restart(
    tmp_path: Path, monkeypatch
) -> None:
    pricing_file = tmp_path / "ai-pricing.toml"
    shutil.copyfile(ROOT / "config" / "ai-pricing.toml", pricing_file)

    monkeypatch.setenv(MODEL_SOURCE_ENV, "factory")
    monkeypatch.setenv(PRICING_SOURCE_ENV, "file")
    monkeypatch.setenv(PRICING_FILE_ENV, str(pricing_file))
    monkeypatch.setenv(PROFILE_SOURCE_ENV, "factory")

    with execution_ai_configuration(cwd=tmp_path) as first:
        first_version = first.pricing.metadata.catalog_version

    text = pricing_file.read_text(encoding="utf-8")
    pricing_file.write_text(
        text.replace(
            f'catalog_version = "{first_version}"',
            'catalog_version = "operator-pricing-next-aud"',
            1,
        ),
        encoding="utf-8",
    )

    with execution_ai_configuration(cwd=tmp_path) as second:
        assert second.pricing.metadata.catalog_version == "operator-pricing-next-aud"
