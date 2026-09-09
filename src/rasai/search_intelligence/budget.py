"""Consumption guards shared by live SERP adapters."""
from __future__ import annotations

from threading import Lock

from .provider import SerpConsumptionLimitError


class RequestBudget:
    def __init__(self, max_requests: int) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be greater than zero")
        self._max = max_requests
        self._used = 0
        self._lock = Lock()

    @property
    def max_requests(self) -> int:
        return self._max

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return self._max - self._used

    def consume(self) -> None:
        with self._lock:
            if self._used >= self._max:
                raise SerpConsumptionLimitError(
                    f"SERP request budget exhausted ({self._used}/{self._max})"
                )
            self._used += 1
