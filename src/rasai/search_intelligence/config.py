"""SERP runtime configuration with conservative POC defaults."""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
from typing import Mapping

SERP_MODE_ENV = "RASAI_SERP_MODE"
SERP_PROVIDER_ENV = "RASAI_SERP_PROVIDER"
SERPAPI_KEY_ENV = "RASAI_SERPAPI_API_KEY"
SERP_FIXTURE_PATH_ENV = "RASAI_SERP_FIXTURE_PATH"
SERP_MAX_QUERIES_ENV = "RASAI_SERP_MAX_QUERIES"
SERP_MAX_REQUESTS_ENV = "RASAI_SERP_MAX_REQUESTS"
SERP_MAX_DEPTH_ENV = "RASAI_SERP_MAX_DEPTH"
SERP_MAX_COMPETITORS_ENV = "RASAI_SERP_MAX_COMPETITORS"
SERP_TIMEOUT_ENV = "RASAI_SERP_TIMEOUT_SECONDS"
SERP_RETRIES_ENV = "RASAI_SERP_RETRIES"
SERP_MIN_INTERVAL_ENV = "RASAI_SERP_MIN_INTERVAL_SECONDS"

SERP_ENV_NAMES = (
    SERP_MODE_ENV,
    SERP_PROVIDER_ENV,
    SERPAPI_KEY_ENV,
    SERP_FIXTURE_PATH_ENV,
    SERP_MAX_QUERIES_ENV,
    SERP_MAX_REQUESTS_ENV,
    SERP_MAX_DEPTH_ENV,
    SERP_MAX_COMPETITORS_ENV,
    SERP_TIMEOUT_ENV,
    SERP_RETRIES_ENV,
    SERP_MIN_INTERVAL_ENV,
)


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer > 0") from exc
    if value <= 0:
        raise ValueError(f"{name} must be an integer > 0")
    return value


def _nonnegative_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer >= 0") from exc
    if value < 0:
        raise ValueError(f"{name} must be an integer >= 0")
    return value


def _number(env: Mapping[str, str], name: str, default: float, *, allow_zero: bool) -> float:
    raw = (env.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        relation = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be a finite number {relation}")
    return value


@dataclass(frozen=True, slots=True)
class SerpRuntimeConfig:
    mode: str = "disabled"
    provider: str = "serpapi"
    fixture_path: Path | None = None
    max_queries: int = 10
    max_requests: int = 10
    max_depth: int = 20
    max_competitors: int = 10
    timeout_seconds: float = 20.0
    retries: int = 1
    min_interval_seconds: float = 1.0

    def validate(self) -> "SerpRuntimeConfig":
        mode = self.mode.strip().casefold()
        if mode not in {"disabled", "live", "fixture"}:
            raise ValueError("SERP mode must be one of: disabled, live, fixture")
        if not self.provider.strip():
            raise ValueError("SERP provider must not be empty")
        if self.max_queries <= 0 or self.max_requests <= 0 or self.max_depth <= 0:
            raise ValueError("SERP max_queries, max_requests and max_depth must be > 0")
        if self.max_competitors < 0:
            raise ValueError("SERP max_competitors must be >= 0")
        if self.timeout_seconds <= 0 or not math.isfinite(self.timeout_seconds):
            raise ValueError("SERP timeout_seconds must be a finite value > 0")
        if self.retries < 0:
            raise ValueError("SERP retries must be >= 0")
        if self.min_interval_seconds < 0 or not math.isfinite(self.min_interval_seconds):
            raise ValueError("SERP min_interval_seconds must be a finite value >= 0")
        if mode == "fixture" and self.fixture_path is None:
            raise ValueError("SERP fixture mode requires a fixture path")
        return replace(self, mode=mode, provider=self.provider.strip().casefold())

    @classmethod
    def from_environment(
        cls, env: Mapping[str, str] | None = None, *, validate: bool = True
    ) -> "SerpRuntimeConfig":
        values = os.environ if env is None else env
        fixture_raw = (values.get(SERP_FIXTURE_PATH_ENV) or "").strip()
        config = cls(
            mode=(values.get(SERP_MODE_ENV) or "disabled"),
            provider=(values.get(SERP_PROVIDER_ENV) or "serpapi"),
            fixture_path=Path(fixture_raw) if fixture_raw else None,
            max_queries=_positive_int(values, SERP_MAX_QUERIES_ENV, 10),
            max_requests=_positive_int(values, SERP_MAX_REQUESTS_ENV, 10),
            max_depth=_positive_int(values, SERP_MAX_DEPTH_ENV, 20),
            max_competitors=_nonnegative_int(values, SERP_MAX_COMPETITORS_ENV, 10),
            timeout_seconds=_number(values, SERP_TIMEOUT_ENV, 20.0, allow_zero=False),
            retries=_nonnegative_int(values, SERP_RETRIES_ENV, 1),
            min_interval_seconds=_number(values, SERP_MIN_INTERVAL_ENV, 1.0, allow_zero=True),
        )
        return config.validate() if validate else config

    def worst_case_http_requests(self, query_count: int) -> int:
        if query_count < 0:
            raise ValueError("query_count must be >= 0")
        if self.mode != "live":
            return 0
        return query_count * (self.retries + 1)
