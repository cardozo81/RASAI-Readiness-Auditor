"""SERP provider contract. Core Search Intelligence depends on this abstraction only."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .models import SerpDataMode, SerpObservation, SerpQueryRequest


class SerpProviderError(RuntimeError):
    code = "SERP_PROVIDER_ERROR"


class SerpProviderUnavailable(SerpProviderError):
    code = "SERP_PROVIDER_UNAVAILABLE"


class SerpProviderTimeout(SerpProviderUnavailable):
    code = "SERP_PROVIDER_TIMEOUT"


class SerpMalformedResponse(SerpProviderError):
    code = "SERP_MALFORMED_RESPONSE"


class SerpUnsupportedEngine(SerpProviderError):
    code = "SERP_UNSUPPORTED_ENGINE"


class SerpConsumptionLimitError(SerpProviderError):
    code = "SERP_CONSUMPTION_LIMIT"


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    observation: SerpObservation
    raw_evidence: bytes | None = None
    content_type: str = "application/json"


class SerpProvider(ABC):
    provider_id: str
    data_mode: SerpDataMode
    supported_engines: tuple[str, ...] = ()

    def supports_engine(self, engine: str) -> bool:
        return not self.supported_engines or engine.casefold() in {
            item.casefold() for item in self.supported_engines
        }

    @abstractmethod
    def observe(self, request: SerpQueryRequest) -> ProviderObservation:
        """Return a normalized observation plus opaque raw evidence when available."""
