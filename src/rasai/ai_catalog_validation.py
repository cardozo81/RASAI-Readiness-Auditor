"""Cross-catalog validation for AI models and pricing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from rasai.ai_model_catalog import AiModelCatalog, load_model_catalog
from rasai.ai_pricing_catalog import PricingCatalog, load_pricing_catalog, resolve_catalog_rule


@dataclass(frozen=True, slots=True)
class AiCatalogAlignment:
    model_catalog_version: str
    pricing_catalog_version: str
    enabled_models: int
    auto_eligible_models: int
    priced_models: int
    pricing_orphans: tuple[str, ...]
    auto_unpriced: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.pricing_orphans and not self.auto_unpriced


def validate_catalog_alignment(
    models: AiModelCatalog | None = None,
    pricing: PricingCatalog | None = None,
    *,
    at: datetime | None = None,
) -> AiCatalogAlignment:
    model_catalog = models or load_model_catalog()
    pricing_catalog = pricing or load_pricing_catalog()
    instant = at or datetime.now(timezone.utc)

    enabled = tuple(
        item
        for item in model_catalog.models
        if item.enabled and item.is_effective(instant)
    )
    model_keys = {(item.provider, item.model) for item in model_catalog.models}
    pricing_keys = pricing_catalog.catalog_models()
    pricing_orphans = tuple(
        sorted(f"{provider}/{model}" for provider, model in pricing_keys - model_keys)
    )
    auto_unpriced: list[str] = []
    for item in enabled:
        if not item.auto_eligible:
            continue
        if resolve_catalog_rule(
            pricing_catalog,
            item.provider,
            item.model,
            at=instant,
            input_tokens=0,
        ) is None:
            auto_unpriced.append(f"{item.provider}/{item.model}")

    return AiCatalogAlignment(
        model_catalog_version=model_catalog.metadata.catalog_version,
        pricing_catalog_version=pricing_catalog.metadata.catalog_version,
        enabled_models=len(enabled),
        auto_eligible_models=sum(1 for item in enabled if item.auto_eligible),
        priced_models=sum(1 for item in enabled if (item.provider, item.model) in pricing_keys),
        pricing_orphans=pricing_orphans,
        auto_unpriced=tuple(sorted(auto_unpriced)),
    )
