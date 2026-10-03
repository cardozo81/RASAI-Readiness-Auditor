"""Native non-token usage primitives for external AI/integration billing.

This module deliberately keeps provider-native commercial units separate from token
telemetry. It contains no provider transport and no deterministic-audit logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Iterable

PERPLEXITY_SEARCH_REQUEST = "PERPLEXITY_SEARCH_REQUEST"
MANUS_CREDIT = "MANUS_CREDIT"

PER_REQUEST = "PER_REQUEST"
PROVIDER_CREDITS = "PROVIDER_CREDITS"

NATIVE_USAGE_UNITS = frozenset({PERPLEXITY_SEARCH_REQUEST, MANUS_CREDIT})
NATIVE_PRICING_MODELS = frozenset({PER_REQUEST, PROVIDER_CREDITS})
COUNTED_COMPONENT_TYPES = frozenset({"REQUEST", "CONSUMPTION"})
ADJUSTMENT_COMPONENT_TYPES = frozenset({"REFUND", "GRANT"})
RECONCILIATION_COMPONENT_TYPE = "RECONCILIATION"
NATIVE_COMPONENT_TYPES = frozenset(
    set(COUNTED_COMPONENT_TYPES)
    | set(ADJUSTMENT_COMPONENT_TYPES)
    | {RECONCILIATION_COMPONENT_TYPE}
)


@dataclass(frozen=True, slots=True)
class NativeUsageComponent:
    """One provider-native usage observation.

    quantity is always a non-negative magnitude. Commercial sign/meaning is carried
    by component_type so a refund/grant is never confused with negative consumption.
    billable is tri-state: True/False only when the provider contract establishes it,
    otherwise None.
    """

    unit: str
    quantity: float
    source_metric: str
    component_type: str = "CONSUMPTION"
    billable: bool | None = None
    observed_at: datetime | None = None

    def __post_init__(self) -> None:
        unit = str(self.unit or "").strip().upper()
        source_metric = str(self.source_metric or "").strip()
        component_type = str(self.component_type or "").strip().upper()
        try:
            quantity = float(self.quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("native usage quantity must be numeric") from exc
        if not unit:
            raise ValueError("native usage unit cannot be empty")
        if not source_metric:
            raise ValueError("native usage source_metric cannot be empty")
        if component_type not in NATIVE_COMPONENT_TYPES:
            raise ValueError(f"unsupported native usage component_type: {component_type}")
        if not math.isfinite(quantity) or quantity < 0:
            raise ValueError("native usage quantity must be finite and non-negative")
        if self.billable is not None and not isinstance(self.billable, bool):
            raise ValueError("native usage billable must be bool or None")
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "source_metric", source_metric)
        object.__setattr__(self, "component_type", component_type)
        object.__setattr__(self, "quantity", quantity)


def counted_native_components(
    components: Iterable[NativeUsageComponent],
) -> tuple[NativeUsageComponent, ...]:
    """Return only primary consumption/request observations.

    Reconciliation rows and credit adjustments stay traceable but are intentionally not
    added to primary usage totals. This guards against double counting a Manus task's
    credit_usage with usage-list/team reconciliation observations.
    """

    return tuple(
        component
        for component in components
        if component.component_type in COUNTED_COMPONENT_TYPES
    )


def native_usage_totals(
    components: Iterable[NativeUsageComponent],
) -> dict[str, float]:
    totals: dict[str, float] = {}
    for component in counted_native_components(components):
        totals[component.unit] = totals.get(component.unit, 0.0) + component.quantity
    return totals


def humanize_native_usage_unit(unit: str, quantity: float | None = None) -> str:
    normalized = str(unit or "").strip().upper()
    singular = quantity is not None and math.isclose(float(quantity), 1.0)
    if normalized == PERPLEXITY_SEARCH_REQUEST:
        return "requisição de busca Perplexity" if singular else "requisições de busca Perplexity"
    if normalized == MANUS_CREDIT:
        return "crédito Manus" if singular else "créditos Manus"
    return normalized or "unidade nativa não identificada"
