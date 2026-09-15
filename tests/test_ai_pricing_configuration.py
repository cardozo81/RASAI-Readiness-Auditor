from __future__ import annotations

from configparser import ConfigParser
from datetime import datetime, timezone
from pathlib import Path
import tomllib

import pytest

from rasai.ai_pricing_catalog import (
    load_factory_pricing_catalog,
    load_pricing_catalog,
    pricing_catalog_from_mapping,
    pricing_runtime_settings,
    resolve_catalog_rule,
    restore_factory_pricing_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def test_factory_catalog_is_versioned_and_referenced_to_2026_09_13() -> None:
    catalog = load_factory_pricing_catalog()
    assert catalog.metadata.schema_version == 1
    assert catalog.metadata.catalog_version == "RASAI-PRICING-2026-09-13"
    assert catalog.metadata.reference_date == "2026-09-13"
    assert catalog.metadata.verified_on == "2026-09-13"
    assert catalog.metadata.review_recommended_on == "2026-10-13"


def test_factory_catalog_declares_current_commercial_models() -> None:
    catalog = load_factory_pricing_catalog()
    by_key = {(item.provider, item.model): item for item in catalog.models}
    assert by_key[("OPENAI", "gpt-5.6-luna")].pricing_model == "TOKEN_CONTEXT_TIERED"
    assert by_key[("DEEPSEEK", "deepseek-v4-flash")].pricing_model == "TOKEN_TIME_WINDOW"
    assert by_key[("MIMO", "mimo-v2.5")].pricing_model == "TOKEN_STANDARD"
    assert by_key[("XAI", "grok-4.6")].pricing_model == "TOKEN_CONTEXT_TIERED"
    assert by_key[("QWEN", "qwen3.8-flash")].region == "US_VIRGINIA"
    assert by_key[("GEMINI", "gemini-3.8-flash")].reasoning_billing == "ADD_REASONING_TO_OUTPUT"
    assert by_key[("ANTHROPIC", "claude-sonnet-5")].pricing_model == "TOKEN_STANDARD"


def test_time_window_and_context_thresholds_are_catalog_data() -> None:
    catalog = load_factory_pricing_catalog()
    peak = resolve_catalog_rule(
        catalog,
        "DEEPSEEK",
        "deepseek-v4-pro",
        at=datetime(2026, 9, 14, 1, 30, tzinfo=UTC),
        input_tokens=10_000,
    )
    off_peak = resolve_catalog_rule(
        catalog,
        "DEEPSEEK",
        "deepseek-v4-pro",
        at=datetime(2026, 9, 12, 1, 30, tzinfo=UTC),
        input_tokens=10_000,
    )
    openai_long = resolve_catalog_rule(
        catalog,
        "OPENAI",
        "gpt-5.6-sol",
        at=datetime(2026, 9, 14, tzinfo=UTC),
        input_tokens=272_001,
    )
    xai_long = resolve_catalog_rule(
        catalog,
        "XAI",
        "grok-4.6",
        at=datetime(2026, 9, 14, tzinfo=UTC),
        input_tokens=200_000,
    )
    assert peak is not None and peak[1].context == "PEAK"
    assert off_peak is not None and off_peak[1].context == "OFF_PEAK"
    assert openai_long is not None and openai_long[1].context == "LONG_CONTEXT_GT_272K"
    assert xai_long is not None and xai_long[1].context == "LONG_CONTEXT"


def test_local_user_catalog_can_change_price_without_code_change(tmp_path: Path) -> None:
    source = ROOT / "src" / "rasai" / "config" / "ai-pricing-defaults.toml"
    document = tomllib.loads(source.read_text(encoding="utf-8"))
    target = next(item for item in document["models"] if item["provider"] == "MIMO" and item["model"] == "mimo-v2.5")
    target["rules"][0]["input_price_per_million"] = 9.99

    # tomllib has no writer; use a minimal complete SaaS-equivalent mapping to prove the
    # generic contract independently of serialization details.
    catalog = pricing_catalog_from_mapping(document, source="TEST_OVERRIDE")
    resolved = resolve_catalog_rule(
        catalog,
        "MIMO",
        "mimo-v2.5",
        at=datetime(2026, 9, 14, tzinfo=UTC),
        input_tokens=1_000,
    )
    assert resolved is not None
    assert resolved[1].input_price_per_million == pytest.approx(9.99)


def test_future_unpriced_provider_becomes_priced_only_by_catalog_mapping() -> None:
    document = {
        "metadata": {
            "schema_version": 1,
            "catalog_version": "TEST-1",
            "reference_date": "2026-09-13",
            "verified_on": "2026-09-13",
            "review_recommended_on": "2026-10-13",
        },
        "models": [{
            "provider": "FUTUREAI",
            "model": "future-1",
            "pricing_model": "TOKEN_STANDARD",
            "reasoning_billing": "IN_OUTPUT",
            "region": "GLOBAL",
            "source_reference": "https://example.invalid/pricing",
            "rules": [{
                "rule_id": "futureai-future-1-standard",
                "context": "STANDARD",
                "priority": 0,
                "effective_from": "2026-09-13T00:00:00Z",
                "input_price_per_million": 0.15,
                "cached_input_price_per_million": 0.03,
                "output_price_per_million": 0.60,
            }],
        }],
    }
    catalog = pricing_catalog_from_mapping(document)
    resolved = resolve_catalog_rule(
        catalog,
        "FUTUREAI",
        "future-1",
        at=datetime(2026, 9, 14, tzinfo=UTC),
        input_tokens=1_000,
    )
    assert resolved is not None
    assert resolved[1].output_price_per_million == pytest.approx(0.60)


def test_file_source_is_fail_closed_when_configured_file_does_not_exist(tmp_path: Path) -> None:
    env = {
        "RASAI_AI_PRICING_SOURCE": "file",
        "RASAI_AI_PRICING_FILE": "missing.toml",
    }
    source, selected = pricing_runtime_settings(env=env, cwd=tmp_path)
    assert source == "file"
    assert selected == (tmp_path / "missing.toml").resolve()
    with pytest.raises(ValueError, match="arquivo não existe"):
        load_pricing_catalog(env=env, cwd=tmp_path)


def test_restore_factory_helper_reconstructs_editable_catalog(tmp_path: Path) -> None:
    target = tmp_path / "ai-pricing.toml"
    target.write_text("invalid = true\n", encoding="utf-8")
    restored = restore_factory_pricing_catalog(target)
    catalog = load_pricing_catalog(path=restored)
    assert catalog.metadata.catalog_version == "RASAI-PRICING-2026-09-13"
    assert catalog.source == str(target.resolve())


def test_rasai_defaults_use_operator_pricing_catalog_with_factory_fallback() -> None:
    parser = ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(ROOT / "src" / "rasai" / "config" / "rasai-defaults.ini", encoding="utf-8")
    assert parser.get("environment", "RASAI_AI_PRICING_SOURCE") == "auto"
    assert parser.get("environment", "RASAI_AI_PRICING_FILE") == "config/ai-pricing.toml"
